import hashlib
from pathlib import Path
from django.db import transaction
from django.core.files.base import ContentFile
from apps.accounts.models import Audit
from apps.accounts.policies import admin_only
from .models import SourceFile, SourceRow, SourceLocation, Item, Alias
from .excel import scan, INVALID_CODES
import re


def ingest(data, path, actor, catalog=False):
    # Authorization sits outside the write transaction so denial audits survive rollback.
    admin_only(actor)
    return _ingest(data, path, actor, catalog)


@transaction.atomic
def _ingest(data, path, actor, catalog=False):
    if not str(path).lower().endswith(".xlsx"):
        raise ValueError("只支持XLSX文件")
    if len(Path(path).name) > 255:
        raise ValueError("文件名超过255字符限制")
    digest = hashlib.sha256(data).hexdigest()
    from django.db import connection

    with connection.cursor() as c:
        c.execute("SELECT pg_advisory_xact_lock(%s)", [int(digest[:15], 16)])
    f = SourceFile.objects.filter(sha256=digest).first()
    if f:
        if f.catalog != catalog:
            raise ValueError("相同文件已以另一种导入类型保存")
        SourceLocation.objects.get_or_create(source=f, path=path)
        return (f, False)
    rows, sheets = scan(data, path, catalog)
    f = SourceFile.objects.create(
        sha256=digest, file_name=Path(path).name, actor=actor, catalog=catalog
    )
    try:
        f.original.save(digest + ".xlsx", ContentFile(data))
        SourceLocation.objects.create(source=f, path=path)
        for record in rows:
            row = SourceRow.objects.create(source=f, **record)
        Audit.objects.create(
            actor=actor,
            target=f"source:{f.pk}",
            action="preview_import",
            after={"rows": len(rows), "sheets": sheets},
        )
    except Exception:
        # File storage is outside the SQL transaction; avoid orphan originals on rollback.
        f.original.delete(save=False)
        raise
    return (f, True)


@transaction.atomic
def apply_catalog(source_id, actor):
    from apps.accounts.policies import admin_only

    admin_only(actor)
    f = SourceFile.objects.select_for_update().get(pk=source_id, catalog=True)
    created = 0
    for row in f.rows.filter(
        template="catalog",
        status__in=["candidate", "needs_confirmation"],
        item__isnull=True,
    ):
        record = {
            "mapped": row.mapped,
            "headers": row.headers,
            "original_values": row.original_values,
        }
        m = record["mapped"]
        h = record["headers"]
        rv = record["original_values"]

        def by(*names):
            for name in names:
                if name in h:
                    return rv[h.index(name)]
            return ""

        item = Item.objects.create(
            new_code=m.get("new_material_code", ""),
            old_code=m.get("old_material_code", ""),
            description=m.get("material_description", ""),
            category=row.sheet,
            equipment=by("设备", "设备名称", "设备型号"),
            brand=by("备件品牌", "品牌"),
            location=by("使用位置"),
        )
        row.item = item
        row.save(update_fields=["item"])
        for key, kind in [("new_material_code", "new"), ("old_material_code", "old")]:
            if m.get(key):
                Alias.objects.create(item=item, code=m[key], kind=kind, source_row=row)
        if row.sheet == "ASM" and re.match(
            "5321\\.", m.get("material_description", "")
        ):
            Alias.objects.create(
                item=item,
                code=m["material_description"],
                kind="candidate",
                source_row=row,
            )
        created += 1
    Audit.objects.create(
        actor=actor,
        target=f"source:{f.pk}",
        action="apply_catalog",
        after={"created": created},
    )
    return created
