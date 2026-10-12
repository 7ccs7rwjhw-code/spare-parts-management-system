import uuid
from django.db import transaction
from django.db.models import Q, F
from django.core.exceptions import PermissionDenied, ValidationError
from apps.accounts.policies import admin_only, role, department, visible, may_edit
from apps.inventory.models import Item
from apps.requests.models import Batch, Line
from apps.approvals.audit import event, line_snapshot
from apps.inventory.excel import number, FIELDS, NUMERIC


class Conflict(Exception):
    pass


def group_lock(requester_id, year, month, kind):
    import hashlib
    from django.db import connection

    key = f"{requester_id}:{year}:{month}:{kind}"
    with connection.cursor() as c:
        c.execute(
            "SELECT pg_advisory_xact_lock(%s)",
            [int(hashlib.sha256(key.encode()).hexdigest()[:15], 16)],
        )


def checked(b, version):
    if b.lock_version != int(version):
        raise Conflict("申请已被其他操作更新，请刷新后重试")


def validate_values(values, existing=None):
    if not values.get("material_description", "").strip():
        raise ValidationError("物料描述必填")
    for key in NUMERIC - {"forecast_qty"}:
        if values.get(key, "").strip() not in ["", "-"]:
            d, u, e = number(values[key])
            if d is None or u:
                if existing is None or values[key] != existing.values.get(key):
                    raise ValidationError(
                        f"{key}须为非负数字或空值（历史原值可保留，不自动修正）"
                    )


@transaction.atomic
def save_line(
    user, bid, version, values, unit="", line_id=None, item_id=None, confirmed=False
):
    b = Batch.objects.select_for_update().get(pk=bid)
    may_edit(user, b)
    checked(b, version)
    line = b.lines.get(pk=line_id) if line_id else Line(batch=b)
    validate_values(values, line if line_id else None)
    before = {"lines": line_snapshot(b), "lock_version": b.lock_version}
    d, u, err = number(values.get("forecast_qty", ""))
    if d is None and err not in ["数量缺失", "数量占位"]:
        raise ValidationError(err)
    if u and unit and (u != unit):
        raise ValidationError("数量中的单位与单位栏不一致")
    item = Item.objects.get(pk=item_id, active=True) if item_id else None
    line.item = item
    line.values = {k: values.get(k, "") for k in FIELDS}
    line.raw_quantity = values.get("forecast_qty", "")
    line.quantity = d
    line.unit = u or unit
    line.confirmed = bool(confirmed and d is not None and (u or unit))
    for key in NUMERIC - {"forecast_qty"}:
        parsed = number(values.get(key, ""))[0]
        if parsed is not None or not values.get(key, "").startswith("="):
            setattr(line, key, parsed)
    line.save()
    b.lock_version += 1
    b.save(update_fields=["lock_version"])
    event(user, b, "save_line", before)
    return b


@transaction.atomic
def delete_line(user, bid, version, lid):
    b = Batch.objects.select_for_update().get(pk=bid)
    may_edit(user, b)
    checked(b, version)
    before = {"lines": line_snapshot(b)}
    b.lines.get(pk=lid).delete()
    b.lock_version += 1
    b.save()
    event(user, b, "delete_line", before)
    return b


@transaction.atomic
def clone(user, bid, version, year, month, revision=False):
    hint = Batch.objects.get(pk=bid)
    group_lock(hint.requester_id, hint.year, hint.month, hint.kind)
    old = Batch.objects.select_for_update().get(pk=bid)
    if not visible(user).filter(pk=bid).exists():
        raise PermissionDenied
    if role(user) != "admin" and old.requester_id != user.pk:
        raise PermissionDenied
    checked(old, version)
    if revision and old.status != "approved":
        raise ValidationError("仅批准单可修订")
    if revision and (year != old.year or month != old.month):
        raise ValidationError("修订不可改变月份")
    new = Batch(
        year=year,
        month=month,
        kind=old.kind,
        requester=old.requester if revision else user,
        department=old.department if revision else department(user),
        parent=old if revision else None,
        family=old.family if revision else uuid.uuid4(),
        version=Batch.objects.filter(family=old.family)
        .order_by("-version")
        .first()
        .version
        + 1
        if revision
        else 1,
    )
    new.full_clean()
    new.save()
    for l in old.lines.order_by("id"):
        values = dict(l.values)
        if not revision:
            for k in [
                "factory_stock",
                "outstanding_qty",
                "nvb2",
                "previous_month_actual_qty",
                "required_purchase_qty",
                "order_number",
            ]:
                values[k] = ""
        Line.objects.create(
            batch=new,
            item=l.item,
            source_row=l.source_row if revision else None,
            values=values,
            quantity=l.quantity,
            unit=l.unit,
            raw_quantity=l.raw_quantity,
            confirmed=False,
            **{
                k: getattr(l, k)
                if revision
                or k
                not in [
                    "factory_stock",
                    "outstanding_qty",
                    "nvb2",
                    "previous_month_actual_qty",
                    "required_purchase_qty",
                ]
                else None
                for k in NUMERIC - {"forecast_qty"}
            },
        )
    event(
        user,
        new,
        "revision" if revision else "copy",
        {"parent": old.pk, "lines": line_snapshot(old)},
    )
    return new


@transaction.atomic
def select_effective(user, bid, version, other_ids=(), reason=""):
    admin_only(user)
    b = Batch.objects.get(pk=bid)
    group_lock(b.requester_id, b.year, b.month, b.kind)
    locked = list(
        Batch.objects.select_for_update()
        .filter(requester=b.requester, year=b.year, month=b.month, kind=b.kind)
        .order_by("pk")
    )
    b = next((x for x in locked if x.pk == bid))
    checked(b, version)
    if b.status != "approved":
        raise ValidationError("只可选择已批准版本")
    if not reason.strip():
        raise ValidationError("选择生效版本需说明原因")
    siblings = {x.pk for x in locked}
    if any((int(i) not in siblings for i in other_ids)):
        raise ValidationError("其他候选不属于同年月/申请人/类型")
    before = {
        "effective_ids": [x.pk for x in locked if x.effective],
        "versions": [
            {
                "id": x.pk,
                "family": str(x.family),
                "lock_version": x.lock_version,
                "effective": x.effective,
                "version": x.version,
            }
            for x in locked
        ],
    }
    selected_families = {
        x.family for x in locked if x.pk in {int(i) for i in other_ids}
    } | {b.family}
    ids = {x.pk for x in locked if x.family in selected_families}
    Batch.objects.filter(pk__in=ids).update(effective=False)
    # Explicitly joining two historical families must also allocate unique versions.
    next_version = max(x.version for x in locked if x.family == b.family)
    for candidate in sorted(locked, key=lambda x: (str(x.family), x.version, x.pk)):
        if candidate.pk not in ids:
            continue
        updates = {"lock_version": F("lock_version") + 1}
        if candidate.family != b.family:
            next_version += 1
            updates.update(family=b.family, version=next_version)
        Batch.objects.filter(pk=candidate.pk).update(**updates)
    b.effective = True
    b.lock_version += 1
    b.save()
    event(user, b, "select_effective", before, reason)
