"""B7 opt-in adapter and evidence recovery: all fixtures offline/synthetic."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apps.msp_marketplace_reports.archive import _rows
from apps.msp_marketplace_reports.generation_store import (
    CommitUncertainError, GenerationError, publish_batch, read_active, reconcile,
)
from apps.msp_marketplace_reports.generation_recovery import (
    RecoveryUncertainError, quarantine_uncommitted,
)
from apps.msp_marketplace_reports.versioned_archive import (
    import_csv_versioned, read_csv_versioned, verify_versioned_scope,
)
from test_msp_marketplace_generations import wb_files


def source(path, fields, rows):
    import csv
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter=";")
        w.writeheader()
        w.writerows(rows)


class VersionedImportTests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name) / "archive"
        self.source = Path(d.name) / "incoming.csv"

    def _wb(self, report="11", amount="10", report_type="1"):
        source(self.source, ["reportId", "rrdId", "reportType", "amount", "dateTo"],
               [{"reportId": report, "rrdId": report, "reportType": report_type,
                 "amount": amount, "dateTo": "2026-10-11"}])
        return self.source

    def test_wb_versioned_merges_without_legacy_writes(self):
        args = (self.root, "wb_weekly_finance_main", "wb_laser_master", "2026")
        r1 = import_csv_versioned(*args, self._wb())
        self.assertTrue(r1["changed"])
        one, pin = read_csv_versioned(*args)
        self.assertEqual(pin["generation"], r1["generation"])
        self.assertEqual(pin["manifest_sha256"], r1["manifest_sha256"])
        self.assertEqual(len(_rows(one, ("reportId", "rrdId"))[1]), 1)
        same = import_csv_versioned(*args, self._wb())
        self.assertFalse(same["changed"])
        self.assertEqual(same["generation"], r1["generation"])
        r2 = import_csv_versioned(*args, self._wb("12", "25"))
        self.assertTrue(r2["changed"])
        self.assertEqual(r2["new_rows"], 1)
        updated, _ = read_csv_versioned(*args)
        self.assertEqual(len(_rows(updated, ("reportId", "rrdId"))[1]), 2)
        old, old_pin = read_csv_versioned(*args, pinned_generation=pin["generation"],
                                          expected_digest=pin["manifest_sha256"])
        self.assertEqual(old, one)
        self.assertEqual(old_pin["sha256"], pin["sha256"])
        self.assertTrue(verify_versioned_scope(*args)["ok"])
        self.assertFalse((self.root / "База данных").exists())

    def test_wb_conflict_and_wrong_type_no_publish(self):
        args = (self.root, "wb_weekly_finance_main", "wb_laser_master", "2026")
        first = import_csv_versioned(*args, self._wb())
        with self.assertRaisesRegex(ValueError, "conflicting WB"):
            import_csv_versioned(*args, self._wb("11", "99"))
        with self.assertRaisesRegex(ValueError, "reportType mismatch"):
            import_csv_versioned(*args, self._wb("12", "20", "2"))
        self.assertEqual(read_csv_versioned(*args)[1]["generation"], first["generation"])

    def test_two_wb_types_are_isolated(self):
        main = (self.root, "wb_weekly_finance_main", "wb_laser_master", "2026")
        buyout = (self.root, "wb_weekly_finance_buyout", "wb_laser_master", "2026")
        a = import_csv_versioned(*main, self._wb())
        b = import_csv_versioned(*buyout, self._wb("13", "20", "2"))
        self.assertNotEqual(a["generation"], b["generation"])
        self.assertEqual(read_csv_versioned(*main)[1]["generation"], a["generation"])
        self.assertEqual(read_csv_versioned(*buyout)[1]["generation"], b["generation"])

    def test_ozon_monthly_annual_one_snapshot_preserves_old_month(self):
        args_jan = (self.root, "ozon_final_realization", "ozon_laser_master", "2026-01")
        source(self.source, ["report_year", "report_month", "row_number", "qty"], [
            {"report_year": "2026", "report_month": "2026-01", "row_number": "1", "qty": "5"}])
        one = import_csv_versioned(*args_jan, self.source)
        january, pin = read_csv_versioned(*args_jan)
        args_feb = (self.root, "ozon_final_realization", "ozon_laser_master", "2026-02")
        source(self.source, ["report_year", "report_month", "row_number", "qty"], [
            {"report_year": "2026", "report_month": "2026-02", "row_number": "2", "qty": "7"}])
        feb = import_csv_versioned(*args_feb, self.source)
        self.assertNotEqual(one["generation"], feb["generation"])
        self.assertEqual(read_csv_versioned(*args_jan)[0], january)
        self.assertEqual(len(read_active(self.root, "ozon_final_realization",
                                         "ozon_laser_master", "2026")["files"]), 6)
        older = read_csv_versioned(*args_jan, pinned_generation=pin["generation"],
                                   expected_digest=pin["manifest_sha256"])
        self.assertEqual(older[0], january)
        self.assertFalse(verify_versioned_scope(*args_feb)["provider_coverage_proven"])
        self.assertTrue(verify_versioned_scope(*args_feb)["ok"])
        self.assertFalse((self.root / "База данных").exists())

    def test_ozon_bad_month_rejected_before_any_publishing(self):
        args = (self.root, "ozon_final_realization", "ozon_laser_master", "2026-02")
        source(self.source, ["report_year", "report_month", "row_number"], [
            {"report_year": "2026", "report_month": "2026-01", "row_number": "2"}])
        with self.assertRaisesRegex(ValueError, "must match selected month"):
            import_csv_versioned(*args, self.source)
        self.assertFalse(self.root.exists())

    def test_legacy_files_block_opt_in_first_import_without_migration(self):
        args = (self.root, "wb_weekly_finance_main", "wb_laser_master", "2026")
        target = (self.root / "База данных" / "WB" / "wb_laser_master" / "2026"
                  / "finance" / "weekly" / "main" /
                  "wb_laser_master__weekly_main__2026.csv")
        target.parent.mkdir(parents=True)
        target.write_bytes(b"old")
        with self.assertRaisesRegex(GenerationError, "legacy CSV scope"):
            import_csv_versioned(*args, self._wb())
        self.assertEqual(target.read_bytes(), b"old")
        self.assertFalse((self.root / ".b7-generations").exists())

    def test_versioned_optimistic_cas_rejects_concurrent_change(self):
        import apps.msp_marketplace_reports.versioned_archive as va
        args = (self.root, "wb_weekly_finance_main", "wb_laser_master", "2026")
        first = import_csv_versioned(*args, self._wb())
        original = va.publish_batch
        def concurrent_commit(root, dataset, cabinet, period, files,
                              *, expected_generation):
            active = read_active(root, dataset, cabinet, period)
            assert active["generation"] == first["generation"]
            # Publish a distinct full valid candidate before the stale
            # adapter attempts its optimistic commit.
            newer = wb_files("888")
            original(root, dataset, cabinet, period, newer,
                     expected_generation=first["generation"])
            return original(root, dataset, cabinet, period, files,
                            expected_generation=expected_generation)
        with mock.patch.object(va, "publish_batch", side_effect=concurrent_commit):
            with self.assertRaisesRegex(GenerationError, "stale expected generation"):
                import_csv_versioned(*args, self._wb("12", "20"))
        self.assertEqual(read_active(*args)["files"], wb_files("888"))

    def test_readonly_verify_does_not_create_empty_root(self):
        args = (self.root, "ozon_current_orders_fbo", "ozon_dmitrieva", "2026-10")
        self.assertFalse(verify_versioned_scope(*args)["ok"])
        self.assertFalse(self.root.exists())


class EvidenceQuarantineTests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name) / "archive"
        self.args = (self.root, "wb_weekly_finance_main", "wb_laser_master", "2026")
        self.committed = publish_batch(*self.args, wb_files())
        self.scope = (self.root / ".b7-generations" /
                      "wb_weekly_finance_main" / "wb_laser_master" / "2026")

    def _orphan(self, value="40"):
        current = self.committed
        def fail(where):
            if where == "before_commit":
                raise OSError("synthetic precommit")
        with self.assertRaisesRegex(OSError, "synthetic precommit"):
            publish_batch(*self.args, wb_files(value),
                          expected_generation=current["generation"], fault=fail)
        folder = self.scope / "generations"
        return next(x.name for x in folder.iterdir()
                    if x.name != self.committed["generation"])

    def _quarantine(self, ids, *, fault=None, expected=None, digest=None, ack=True):
        return quarantine_uncommitted(
            *self.args, expected_generation=expected or self.committed["generation"],
            expected_digest=digest or self.committed["manifest_sha256"],
            candidates=ids, acknowledged=ack, fault=fault)

    def test_retains_uncommitted_bytes_and_clears_pending_without_changing_current(self):
        candidate = self._orphan()
        source = self.scope / "generations" / candidate
        before = {x.relative_to(source).as_posix(): x.read_bytes()
                  for x in source.rglob("*") if x.is_file()}
        self.assertEqual(reconcile(*self.args)["status"], "RECOVERY_REQUIRED")
        report = self._quarantine([candidate])
        self.assertEqual(report["status"], "EVIDENCE_RETAINED")
        self.assertTrue(report["current_unchanged"])
        evidence = self.scope / "evidence" / candidate
        self.assertFalse(source.exists())
        self.assertEqual({x.relative_to(evidence).as_posix(): x.read_bytes()
                          for x in evidence.rglob("*") if x.is_file()}, before)
        self.assertEqual(reconcile(*self.args)["status"], "ACTIVE_VERIFIED")
        self.assertEqual(read_active(*self.args)["generation"],
                         self.committed["generation"])
        repeat = self._quarantine([candidate])
        self.assertEqual(repeat["moved_in_this_attempt"], [])
        fresh = publish_batch(*self.args, wb_files("60"),
                              expected_generation=self.committed["generation"])
        self.assertEqual(fresh["status"], "COMMITTED")

    def test_requires_ack_and_exact_commit_pin(self):
        candidate = self._orphan()
        with self.assertRaisesRegex(GenerationError, "acknowledgment"):
            self._quarantine([candidate], ack=False)
        with self.assertRaisesRegex(GenerationError, "stale recovery pin"):
            self._quarantine([candidate], digest="0" * 64)
        self.assertTrue((self.scope / "generations" / candidate).exists())

    def test_uncertain_evidence_rename_is_retryable(self):
        candidate = self._orphan()
        def fault(where):
            if where.startswith("after_evidence_fsync"):
                raise OSError("response lost after evidence")
        with self.assertRaisesRegex(RecoveryUncertainError, "uncertain"):
            self._quarantine([candidate], fault=fault)
        self.assertTrue((self.scope / "evidence" / candidate).exists())
        result = self._quarantine([candidate])
        self.assertEqual(result["status"], "EVIDENCE_RETAINED")
        self.assertEqual(result["moved_in_this_attempt"], [])
        self.assertEqual(reconcile(*self.args)["status"], "ACTIVE_VERIFIED")

    def test_missing_current_is_unknown_and_never_quarantined(self):
        candidate = self._orphan()
        (self.scope / "CURRENT.json").unlink()
        with self.assertRaisesRegex(GenerationError, "UNKNOWN_COMMIT_STATE"):
            self._quarantine([candidate])
        self.assertTrue((self.scope / "generations" / candidate).exists())

    def test_committed_generation_and_unlisted_candidates_refused(self):
        candidate = self._orphan()
        with self.assertRaisesRegex(GenerationError, "cannot quarantine committed"):
            self._quarantine([self.committed["generation"]])
        with self.assertRaisesRegex(GenerationError, "unlisted uncommitted"):
            self._quarantine(["0" * 32])
        self.assertTrue((self.scope / "generations" / candidate).exists())

    def test_quarantine_isolation_from_other_cabinet(self):
        candidate = self._orphan()
        other_args = (self.root, "wb_weekly_finance_main", "wb_novokshenov", "2026")
        # Fixture must identify the second cabinet correctly.
        from apps.msp_marketplace_reports.archive import _metadata
        files = wb_files()
        meta = json.loads(files["data.csv.meta.json"])
        meta["cabinet"] = "wb_novokshenov"
        files["data.csv.meta.json"] = json.dumps(meta).encode()
        other = publish_batch(*other_args, files)
        self._quarantine([candidate])
        self.assertEqual(read_active(*other_args)["generation"], other["generation"])


if __name__ == "__main__":
    unittest.main()
