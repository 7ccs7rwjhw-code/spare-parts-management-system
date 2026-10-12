import io, threading, zipfile
from decimal import Decimal
from django.test import TestCase, TransactionTestCase, Client
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import close_old_connections
from django.contrib.auth import get_user_model
from .tests import Base, sample
from .models import *
from .excel import *
from .services import *


class BoundaryTests(Base, TestCase):
    def setUp(self):
        self.init_users()

    def test_reviewer_cannot_approve_self(self):
        Profile.objects.filter(user=self.owner).update(role="reviewer")
        b = self.line(self.batch())
        b = transition(self.owner, b.pk, b.lock_version, "submit")
        with self.assertRaises(PermissionDenied):
            transition(self.owner, b.pk, b.lock_version, "approve")
        b.refresh_from_db()
        self.assertEqual(b.status, "submitted")

    def test_reviewer_other_department_cannot_approve(self):
        Profile.objects.filter(user=self.reviewer).update(department="B")
        b = self.line(self.batch())
        b = transition(self.owner, b.pk, b.lock_version, "submit")
        with self.assertRaises(PermissionDenied):
            transition(self.reviewer, b.pk, b.lock_version, "approve")

    def test_blank_department_reviewer_restricted(self):
        Profile.objects.filter(user=self.reviewer).update(department="")
        b = self.line(self.batch())
        b = transition(self.owner, b.pk, b.lock_version, "submit")
        self.assertFalse(visible(self.reviewer).filter(pk=b.pk).exists())
        with self.assertRaises(PermissionDenied):
            transition(self.reviewer, b.pk, b.lock_version, "approve")

    def test_private_endpoints_are_denied(self):
        f, _ = ingest(sample(), "private.xlsx", self.admin)
        self.client.force_login(self.owner)
        for path in [
            "/imports/",
            f"/imports/{f.pk}/",
            f"/imports/{f.pk}/original/",
            f"/imports/{f.pk}/csv/",
            "/queue/",
            "/audit/",
            "/items/new/",
        ]:
            self.assertEqual(self.client.get(path).status_code, 403, path)

    def test_export_and_line_mutation_foreign_batch(self):
        b = self.line(self.batch())
        lid = b.lines.get().pk
        self.client.force_login(self.other)
        self.assertEqual(
            self.client.get(f"/export/?year=2026&month=10&batch={b.pk}").status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                f"/batches/{b.pk}/line/{lid}/delete/", {"lock_version": b.lock_version}
            ).status_code,
            403,
        )
        self.assertEqual(self.client.get(f"/batches/{b.pk}/copy/").status_code, 404)
        self.assertEqual(b.lines.count(), 1)

    def test_forged_requester_status_and_effective_ignored(self):
        self.client.force_login(self.owner)
        r = self.client.post(
            "/batches/new/",
            {
                "year": 2026,
                "month": 10,
                "kind": "spare_purchase",
                "requester": self.admin.pk,
                "department": "B",
                "status": "approved",
                "effective": "true",
            },
        )
        self.assertEqual(r.status_code, 302)
        b = Batch.objects.get()
        self.assertEqual(b.requester, self.owner)
        self.assertEqual(b.department, "A")
        self.assertEqual(b.status, "draft")
        self.assertFalse(b.effective)

    def test_effective_change_invalidates_previous_page(self):
        old = self.approve(self.line(self.batch()))
        old_version = old.lock_version
        new = clone(self.owner, old.pk, old.lock_version, 2026, 10, True)
        l = new.lines.get()
        new = save_line(
            self.owner, new.pk, new.lock_version, l.values, "个", l.pk, confirmed=True
        )
        self.approve(new)
        with self.assertRaises(Conflict):
            select_effective(self.admin, old.pk, old_version, reason="旧页不应覆盖")

    def test_invalid_filter_returns400(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get("/?year=bad").status_code, 400)

    def test_missing_lock_parameter_returns400(self):
        b = self.batch()
        self.client.force_login(self.owner)
        self.assertEqual(
            self.client.post(f"/batches/{b.pk}/action/submit/", {}).status_code, 400
        )

    def test_zip_traversal_rejected(self):
        for name in ["../evil.xml", "..\\evil.xml", "/evil.xml", "C:/evil.xml"]:
            b = io.BytesIO()
            with zipfile.ZipFile(b, "w") as z:
                z.writestr(name, "x")
            with self.assertRaises(ValueError):
                checked_workbook(b.getvalue())

    def test_malformed_xml_rejected(self):
        src = zipfile.ZipFile(io.BytesIO(sample()))
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as z:
            for n in src.namelist():
                z.writestr(n, "<broken" if n == "xl/workbook.xml" else src.read(n))
        with self.assertRaises(ValueError):
            checked_workbook(out.getvalue())

    def test_extreme_precision_and_negative_rejected(self):
        for raw in ["-1", "100000000000000", "0.1234567", "1e100", "NaN"]:
            self.assertIsNone(number(raw)[0], raw)
        self.assertEqual(number("0.000001")[0], Decimal("0.000001"))

    def test_audit_records_item_and_quantity_before_after(self):
        b = self.line(self.batch(), "20")
        l = b.lines.get()
        v = dict(l.values)
        v["forecast_qty"] = "30"
        save_line(self.owner, b.pk, b.lock_version, v, "个", l.pk, confirmed=True)
        ev = b.events.last()
        self.assertEqual(ev.before["lines"][0]["quantity"], "20.000000")
        self.assertEqual(ev.after["lines"][0]["quantity"], "30.000000")
        self.assertEqual(ev.after["lines"][0]["id"], l.pk)

    def test_reimport_after_revision_uses_next_family_version(self):
        f1, _ = ingest(sample(qty="20"), "same.xlsx", self.admin)
        b = confirm_sheet(
            self.admin, f1.pk, "备件购买", 2026, 10, self.owner, "A", "测试确认"
        )
        l = b.lines.get()
        b = save_line(
            self.owner, b.pk, b.lock_version, l.values, "个", l.pk, confirmed=True
        )
        b = self.approve(b)
        revision = clone(self.owner, b.pk, b.lock_version, 2026, 10, True)
        f2, _ = ingest(sample(qty="30"), "same.xlsx", self.admin)
        imported = confirm_sheet(
            self.admin, f2.pk, "备件购买", 2026, 10, self.owner, "A", "测试确认"
        )
        self.assertEqual(imported.family, b.family)
        self.assertEqual([revision.version, imported.version], [2, 3])


class MoreConcurrentTests(Base, TransactionTestCase):
    def setUp(self):
        self.init_users()

    def parallel(self, functions):
        gate = threading.Barrier(len(functions))
        results = []

        def run(fn):
            close_old_connections()
            try:
                gate.wait(timeout=10)
                fn()
                results.append("saved")
            except Conflict:
                results.append("conflict")
            except Exception as e:
                results.append(type(e).__name__ + ": " + str(e))
            finally:
                close_old_connections()

        ts = [threading.Thread(target=run, args=(f,)) for f in functions]
        for t in ts:
            t.start()
        for t in ts:
            t.join(timeout=20)
        self.assertTrue(all(not t.is_alive() for t in ts))
        return results

    def test_concurrent_approval_single_event(self):
        b = self.line(self.batch())
        b = transition(self.owner, b.pk, b.lock_version, "submit")
        fn = lambda: transition(
            get_user_model().objects.get(pk=self.reviewer.pk),
            b.pk,
            b.lock_version,
            "approve",
        )
        self.assertCountEqual(self.parallel([fn, fn]), ["saved", "conflict"])
        self.assertEqual(b.events.filter(action="approve").count(), 1)

    def test_concurrent_effective_selection_single_winner(self):
        old = self.approve(self.line(self.batch()))
        new = clone(self.owner, old.pk, old.lock_version, 2026, 10, True)
        l = new.lines.get()
        new = save_line(
            self.owner, new.pk, new.lock_version, l.values, "个", l.pk, confirmed=True
        )
        new = transition(self.owner, new.pk, new.lock_version, "submit")
        new = transition(self.reviewer, new.pk, new.lock_version, "approve")

        def choose(b):
            return lambda: select_effective(
                get_user_model().objects.get(pk=self.admin.pk),
                b.pk,
                b.lock_version,
                reason="并发测试",
            )

        self.assertCountEqual(
            self.parallel([choose(old), choose(new)]), ["saved", "conflict"]
        )
        self.assertEqual(
            Batch.objects.filter(family=old.family, effective=True).count(), 1
        )

    def test_concurrent_different_files_one_family(self):
        f1, _ = ingest(sample(qty="20"), "same.xlsx", self.admin)
        f2, _ = ingest(sample(qty="30"), "same.xlsx", self.admin)

        def confirm(f):
            return lambda: confirm_sheet(
                get_user_model().objects.get(pk=self.admin.pk),
                f.pk,
                "备件购买",
                2026,
                10,
                get_user_model().objects.get(pk=self.owner.pk),
                "A",
                "测试确认",
            )

        self.assertEqual(self.parallel([confirm(f1), confirm(f2)]), ["saved", "saved"])
        bs = list(Batch.objects.order_by("version"))
        self.assertEqual(len(bs), 2)
        self.assertEqual(bs[0].family, bs[1].family)
        self.assertEqual([b.version for b in bs], [1, 2])

    def test_concurrent_revision_versions_distinct(self):
        b = self.approve(self.line(self.batch()))
        fn = lambda: clone(
            get_user_model().objects.get(pk=self.owner.pk),
            b.pk,
            b.lock_version,
            2026,
            10,
            True,
        )
        self.assertEqual(self.parallel([fn, fn]), ["saved", "saved"])
        self.assertEqual(
            list(
                Batch.objects.filter(parent=b)
                .order_by("version")
                .values_list("version", flat=True)
            ),
            [2, 3],
        )


class DiffTests(TestCase):
    def test_change_labels_and_values(self):
        from .diffs import line_changes

        a = {
            "id": 1,
            "values": {"forecast_qty": "20"},
            "quantity": "20.000000",
            "unit": "个",
        }
        b = {
            "id": 1,
            "values": {"forecast_qty": "30"},
            "quantity": "30.000000",
            "unit": "m",
        }
        changes = line_changes([a], [b])
        self.assertIn(
            {"line": 1, "field": "单位", "before": "个", "after": "m"}, changes
        )
        self.assertTrue(any(c["field"] == "解析数量" for c in changes))

    def test_added_removed_rows_visible(self):
        from .diffs import line_changes

        r = {"id": 2, "values": {"material_description": "测试行"}}
        self.assertEqual(line_changes([], [r])[0]["field"], "新增行")
        self.assertEqual(line_changes([r], [])[0]["field"], "删除行")
