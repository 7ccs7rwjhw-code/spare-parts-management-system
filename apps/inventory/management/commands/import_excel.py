"""Import one workbook without requiring the private historical archive."""

import hashlib
import json
from collections import Counter
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.policies import admin_only
from apps.inventory.excel import scan
from apps.inventory.importers import ingest, apply_catalog


class Command(BaseCommand):
    help = "Preview/import XLSX with provenance; historical sheets remain unconfirmed."

    def add_arguments(self, parser):
        parser.add_argument("file")
        parser.add_argument("--actor", required=True)
        parser.add_argument("--catalog", action="store_true")
        parser.add_argument("--apply-catalog", action="store_true")
        parser.add_argument("--preview", action="store_true")
        parser.add_argument("--source-path")
        parser.add_argument("--report")

    def handle(self, *args, **options):
        if options["apply_catalog"] and (not options["catalog"] or options["preview"]):
            raise CommandError(
                "--apply-catalog requires --catalog and cannot be used with --preview"
            )
        try:
            actor = get_user_model().objects.get(
                username=options["actor"], is_active=True
            )
        except get_user_model().DoesNotExist as exc:
            raise CommandError("导入账号不存在或未启用") from exc
        admin_only(actor)
        path = Path(options["file"])
        if not path.is_file() or path.suffix.lower() != ".xlsx":
            raise CommandError("请指定存在的XLSX文件")
        if path.stat().st_size > 25 * 1024 * 1024:
            raise CommandError("文件超过25MB")
        data = path.read_bytes()
        location = options["source_path"] or path.name
        try:
            rows, sheets = scan(data, location, options["catalog"])
            report = {
                "sha256": hashlib.sha256(data).hexdigest(),
                "rows": len(rows),
                "status_counts": dict(Counter(row["status"] for row in rows)),
                "warning_rows": sum(bool(row["issues"]) for row in rows),
                "sheets": sheets,
                "preview_only": options["preview"],
            }
            if not options["preview"]:
                source, created = ingest(data, location, actor, options["catalog"])
                report.update(source_id=source.pk, created=created)
                if options["apply_catalog"]:
                    report["items_created"] = apply_catalog(source.pk, actor)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        output = json.dumps(report, ensure_ascii=False, indent=2)
        if options["report"]:
            destination = Path(options["report"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(output, encoding="utf-8")
        self.stdout.write(output)
