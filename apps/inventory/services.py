import uuid
from django.db import transaction
from django.core.exceptions import ValidationError
from apps.accounts.policies import admin_only
from apps.requests.models import Batch, Line
from apps.requests.services import group_lock
from apps.approvals.audit import event
from .models import SourceFile, Item
from .excel import INVALID_CODES, FIELDS, NUMERIC, number


@transaction.atomic
def confirm_sheet(
    user,
    source_id,
    sheet,
    year,
    month,
    requester,
    department_name,
    reason,
    mapping=None,
):
    admin_only(user)
    f = SourceFile.objects.select_for_update().get(pk=source_id)
    if f.catalog:
        raise ValidationError("主资料不产生月度申请")
    exists = Batch.objects.filter(source=f, source_sheet=sheet, parent=None).first()
    if exists:
        return exists
    rows = (
        f.rows.filter(sheet=sheet, template__in=["21", "17", "18"])
        .exclude(status="non_business_row")
        .order_by("row")
    )
    if not rows.exists():
        raise ValidationError("不是支持的申请工作表或没有物料行")
    if not reason.strip():
        raise ValidationError("确认年月及异常的说明必填")
    mapping = mapping or {}
    if rows.first().template != "18" and mapping:
        raise ValidationError("仅18列表允许指定双库存/未交映射")
    if rows.first().template == "18" and (
        not (
            mapping.get("factory_stock") in [12, 14]
            and mapping.get("outstanding_qty") in [11, 13]
        )
    ):
        raise ValidationError("18列表须明确选择库存和未交列（索引12/14和11/13）")
    kind = "department_purchase" if "部门自购" in sheet else "spare_purchase"
    group_lock(requester.pk, year, month, kind)
    prior = (
        Batch.objects.filter(
            year=year,
            month=month,
            kind=kind,
            requester=requester,
            source__file_name=f.file_name,
            source_sheet=sheet,
        )
        .order_by("-version")
        .first()
    )
    latest = (
        Batch.objects.filter(family=prior.family).order_by("-version").first()
        if prior
        else None
    )
    b = Batch(
        year=year,
        month=month,
        kind=kind,
        requester=requester,
        department=department_name,
        source=f,
        source_sheet=sheet,
        family=prior.family if prior else uuid.uuid4(),
        version=latest.version + 1 if latest else 1,
    )
    b.full_clean()
    b.save()
    for r in rows:
        values = {k: r.mapped.get(k, "") for k in FIELDS}
        for key, idx in mapping.items():
            if key not in ["factory_stock", "outstanding_qty"]:
                raise ValidationError("无效映射")
            values[key] = r.original_values[idx] if idx < len(r.original_values) else ""
        codes = [values.get("new_material_code"), values.get("old_material_code")]
        codes = [c for c in codes if c and c not in INVALID_CODES]
        found = Item.objects.filter(
            active=True, aliases__code__in=codes, aliases__verified=True
        ).distinct()
        item = found.first() if found.count() == 1 else None
        d, u, e = number(values.get("forecast_qty", ""))
        Line.objects.create(
            batch=b,
            item=item,
            source_row=r,
            values=values,
            raw_quantity=values.get("forecast_qty", ""),
            quantity=d,
            unit=u,
            confirmed=False,
            **{
                k: number(
                    r.mapped.get(k + "_cached")
                    if values.get(k, "").startswith("=")
                    else values.get(k, "")
                )[0]
                for k in NUMERIC - {"forecast_qty"}
            },
        )
        if not item:
            r.issues = list(r.issues) + ["待关联主资料"]
            r.save(update_fields=["issues"])
    event(
        user,
        b,
        "confirmed_import",
        {"source": f.pk, "sheet": sheet, "mapping": mapping},
        reason,
    )
    return b
