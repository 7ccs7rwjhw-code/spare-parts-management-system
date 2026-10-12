from pathlib import Path, PurePosixPath
import json, hashlib
import py7zr
from tempfile import TemporaryDirectory
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from django.db.models import Count
from apps.inventory.importers import ingest, apply_catalog
from apps.inventory.models import SourceRow, SourceFile, Item


class Command(BaseCommand):
    help = "Import originals into evidence preview; NEVER infer or confirm application months."

    def add_arguments(self, p):
        p.add_argument("--source-dir", required=True)
        p.add_argument("--actor", required=True)
        p.add_argument("--report", default="evidence/import_stats.json")

    def handle(self, *args, **o):
        user = get_user_model().objects.get(username=o["actor"])
        from apps.accounts.policies import admin_only

        admin_only(user)
        p = Path(o["source_dir"])
        stats = {"source_hashes": {}, "files": []}
        for name in ["设备备件清单-z.xlsx", "26年.7z"]:
            if not (p / name).is_file():
                raise CommandError(f"缺少{name}")
            stats["source_hashes"][name] = hashlib.sha256(
                (p / name).read_bytes()
            ).hexdigest()
        f, new = ingest(
            (p / "设备备件清单-z.xlsx").read_bytes(),
            "source/设备备件清单-z.xlsx",
            user,
            True,
        )
        apply_catalog(f.pk, user)
        stats["catalog_sheets"] = list(
            f.rows.values("sheet", "template", "status")
            .annotate(count=Count("id"))
            .order_by("sheet", "status")
        )
        stats["catalog_candidate_items"] = Item.objects.filter(
            sourcerow__source=f
        ).count()
        stats["catalog_missing_new_code"] = Item.objects.filter(
            sourcerow__source=f, new_code=""
        ).count()
        stats["duplicate_new_code_groups"] = list(
            Item.objects.filter(sourcerow__source=f)
            .exclude(new_code="")
            .values("new_code")
            .annotate(count=Count("id"))
            .filter(count__gt=1)
        )
        stats["usage_rows"] = f.rows.filter(template="usage").count()
        with TemporaryDirectory() as dest:
            with py7zr.SevenZipFile(p / "26年.7z") as z:
                infos = z.list()
                if (
                    len(infos) > 1000
                    or sum(i.uncompressed or 0 for i in infos) > 150 * 1024 * 1024
                ):
                    raise CommandError("归档规模超过限制")
                for name in z.getnames():
                    q = PurePosixPath(name.replace("\\", "/"))
                    if q.is_absolute() or ".." in q.parts or ":" in name:
                        raise CommandError("不安全归档路径")
                z.extractall(dest)
            for path in sorted(Path(dest).rglob("*.xlsx")):
                rel = path.relative_to(dest).as_posix()
                sf, created = ingest(path.read_bytes(), rel, user)
                stats["files"].append(
                    {
                        "path": rel,
                        "sha256": sf.sha256,
                        "created": created,
                        "rows": sf.rows.count(),
                        "candidate_rows": sf.rows.filter(
                            template__in=["21", "17", "18"]
                        )
                        .exclude(status="non_business_row")
                        .count(),
                        "status_counts": list(
                            sf.rows.values("template", "status")
                            .annotate(count=Count("id"))
                            .order_by("template", "status")
                        ),
                    }
                )
        stats["archive_paths"] = len(stats["files"])
        stats["archive_distinct_files"] = len({x["sha256"] for x in stats["files"]})
        stats["historical_candidates_unique"] = (
            SourceRow.objects.filter(
                source__catalog=False, template__in=["21", "17", "18"]
            )
            .exclude(status="non_business_row")
            .count()
        )
        stats["warning_rows_unique"] = SourceRow.objects.exclude(issues=[]).count()
        out = Path(o["report"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(stats, ensure_ascii=False, indent=2))
        self.stdout.write(
            json.dumps(
                {
                    k: stats[k]
                    for k in [
                        "catalog_candidate_items",
                        "catalog_missing_new_code",
                        "usage_rows",
                        "archive_paths",
                        "archive_distinct_files",
                        "historical_candidates_unique",
                        "warning_rows_unique",
                    ]
                },
                ensure_ascii=False,
            )
        )
