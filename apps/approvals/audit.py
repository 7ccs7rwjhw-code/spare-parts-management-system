from apps.accounts.models import Audit
from apps.approvals.models import Event


def line_snapshot(b):
    rows = list(
        b.lines.order_by("id").values(
            "id", "item_id", "quantity", "values", "raw_quantity", "unit", "confirmed"
        )
    )
    for row in rows:
        row["item_id"] = str(row["item_id"]) if row["item_id"] else None
        row["quantity"] = str(row["quantity"]) if row["quantity"] is not None else None
    return rows


def event(user, b, action, before, comment=""):
    after = {
        "status": b.status,
        "lock_version": b.lock_version,
        "version": b.version,
        "family": str(b.family),
        "lines": line_snapshot(b),
    }
    if "versions" in before:
        after["versions"] = [
            {
                "id": row.pk,
                "family": str(row.family),
                "version": row.version,
                "lock_version": row.lock_version,
                "effective": row.effective,
            }
            for row in type(b)
            .objects.filter(
                requester=b.requester, year=b.year, month=b.month, kind=b.kind
            )
            .order_by("pk")
        ]
    record = Event.objects.create(
        batch=b,
        actor=user,
        action=action,
        comment=comment,
        before=before,
        after=after,
    )
    Audit.objects.create(
        actor=user,
        target=f"batch:{b.pk}",
        action=action,
        before=record.before,
        after=record.after,
    )
