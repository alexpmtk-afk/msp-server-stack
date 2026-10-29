"""B7 opt-in generation experiments: synthetic fixtures, no network or VPS."""
import json
import tempfile
import unittest
from pathlib import Path

from apps.msp_marketplace_reports.archive import _encode, _metadata
from apps.msp_marketplace_reports.generation_store import (
    CommitUncertainError, GenerationError, publish_batch, read_active,
    read_generation, reconcile,
)


def wb_files(amount="10", *, dataset="wb_weekly_finance_main"):
    row = {"reportId": "11", "rrdId": "1", "reportType": "1"
           if dataset.endswith("_main") else "2", "amount": amount}
    raw = _encode(list(row), {("11", "1"): row})
    return {"data.csv": raw, "data.csv.meta.json": json.dumps(
        _metadata(raw, 1, dataset, "wb_laser_master", "2026")).encode()}


def ozon_final_files(january="5", february=None):
    year = "2026"
    cabinet = "ozon_laser_master"
    source = {}
    all_rows = {}
    for month, qty in [("2026-01", january), ("2026-02", february)]:
        if qty is None:
            continue
        row = {"report_year": year, "report_month": month, "row_number": month[-2:],
               "qty": qty}
        all_rows[(year, month, month[-2:])] = row
        raw = _encode(list(row), {(year, month, month[-2:]): row})
        name = "monthly/" + month + ".csv"
        source[name] = raw
        source[name + ".meta.json"] = json.dumps(
            _metadata(raw, 1, "ozon_final_realization", cabinet, month)).encode()
    annual_raw = _encode(["report_year", "report_month", "row_number", "qty"], all_rows)
    source["annual.csv"] = annual_raw
    source["annual.csv.meta.json"] = json.dumps(
        _metadata(annual_raw, len(all_rows), "ozon_final_realization", cabinet, year)
    ).encode()
    return source


class GenerationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "archive"
        self.args = (self.root, "wb_weekly_finance_main", "wb_laser_master", "2026")

    def test_first_publish_and_pinned_reader(self):
        first = publish_batch(*self.args, wb_files())
        self.assertEqual(first["status"], "COMMITTED")
        old = read_active(*self.args)
        self.assertEqual(old["generation"], first["generation"])
        self.assertEqual(old["files"], wb_files())
        second = publish_batch(*self.args, wb_files("20"),
                               expected_generation=first["generation"])
        self.assertNotEqual(first["generation"], second["generation"])
        self.assertEqual(read_generation(*self.args, first["generation"])["files"],
                         wb_files())
        self.assertEqual(read_active(*self.args)["files"], wb_files("20"))

    def test_commit_pointer_is_noop_for_identical_payload(self):
        first = publish_batch(*self.args, wb_files())
        second = publish_batch(*self.args, wb_files(), expected_generation=None)
        self.assertFalse(second["changed"])
        self.assertEqual(first["generation"], second["generation"])

    def test_precommit_crash_preserves_previous_committed_snapshot(self):
        prior = publish_batch(*self.args, wb_files())
        def fail(stage):
            if stage == "after_file:data.csv":
                raise OSError("SYNTHETIC_FAIL")
        with self.assertRaisesRegex(OSError, "SYNTHETIC_FAIL"):
            publish_batch(*self.args, wb_files("40"),
                          expected_generation=prior["generation"], fault=fail)
        self.assertEqual(read_active(*self.args)["files"], wb_files())
        result = reconcile(*self.args)
        self.assertEqual(result["status"], "ACTIVE_VERIFIED")
        self.assertEqual(result["generation"], prior["generation"])
        self.assertEqual(len(result["other_retained_generations"]), 1)

    def test_before_commit_crash_on_first_import_is_pending(self):
        def fail(stage):
            if stage == "before_commit":
                raise OSError("NO_COMMIT")
        with self.assertRaises(OSError):
            publish_batch(*self.args, wb_files(), fault=fail)
        self.assertIsNone(read_active(*self.args))
        self.assertEqual(reconcile(*self.args)["status"], "PENDING")

    def test_after_commit_lost_response_can_be_reconciled(self):
        first = publish_batch(*self.args, wb_files())
        def fail(stage):
            if stage == "after_commit":
                raise OSError("LOST_RECEIPT")
        with self.assertRaisesRegex(CommitUncertainError, "commit result uncertain"):
            publish_batch(*self.args, wb_files("99"),
                          expected_generation=first["generation"], fault=fail)
        active = read_active(*self.args)
        self.assertEqual(active["files"], wb_files("99"))
        self.assertEqual(reconcile(*self.args)["status"], "ACTIVE_VERIFIED")
        same = publish_batch(*self.args, wb_files("99"),
                             expected_generation=first["generation"])
        self.assertFalse(same["changed"])
        self.assertEqual(same["generation"], active["generation"])

    def test_stale_writer_rejected_without_switch(self):
        first = publish_batch(*self.args, wb_files())
        second = publish_batch(*self.args, wb_files("20"),
                               expected_generation=first["generation"])
        with self.assertRaisesRegex(GenerationError, "stale expected generation"):
            publish_batch(*self.args, wb_files("30"),
                          expected_generation=first["generation"])
        self.assertEqual(read_active(*self.args)["generation"], second["generation"])

    def test_ozon_monthly_and_annual_are_one_generation(self):
        args = (self.root, "ozon_final_realization", "ozon_laser_master", "2026")
        first = publish_batch(*args, ozon_final_files())
        second = publish_batch(*args, ozon_final_files(january="9", february="7"),
                               expected_generation=first["generation"])
        self.assertEqual(len(read_active(*args)["files"]), 6)
        self.assertEqual(read_generation(*args, first["generation"])["files"],
                         ozon_final_files())
        self.assertEqual(read_active(*args)["generation"], second["generation"])

    def test_ozon_parity_and_corrupt_month_manifest_rejected_before_stage(self):
        args = (self.root, "ozon_final_realization", "ozon_laser_master", "2026")
        ok = publish_batch(*args, ozon_final_files())
        files = ozon_final_files(january="8")
        files["annual.csv"] = ozon_final_files(january="5")["annual.csv"]
        with self.assertRaisesRegex(GenerationError, "manifest identity/hash mismatch"):
            publish_batch(*args, files, expected_generation=ok["generation"])
        files = ozon_final_files(january="8")
        meta = json.loads(files["monthly/2026-01.csv.meta.json"])
        meta["schema"] = True
        files["monthly/2026-01.csv.meta.json"] = json.dumps(meta).encode()
        with self.assertRaisesRegex(GenerationError, "integer field"):
            publish_batch(*args, files, expected_generation=ok["generation"])
        self.assertEqual(read_active(*args)["generation"], ok["generation"])

    def test_pointer_corruption_not_auto_repaired(self):
        first = publish_batch(*self.args, wb_files())
        ptr = (self.root / ".b7-generations" /
               "wb_weekly_finance_main" / "wb_laser_master" / "2026" /
               "CURRENT.json")
        ptr.write_bytes(b'{"schema":true,"generation":"bad"}')
        with self.assertRaises(GenerationError):
            read_active(*self.args)
        self.assertEqual(reconcile(*self.args)["status"], "RECOVERY_REQUIRED")
        with self.assertRaises(GenerationError):
            publish_batch(*self.args, wb_files("30"),
                          expected_generation=first["generation"])

    def test_snapshot_corruption_not_recertified(self):
        first = publish_batch(*self.args, wb_files())
        f = (self.root / ".b7-generations" / "wb_weekly_finance_main" /
             "wb_laser_master" / "2026" / "generations" /
             first["generation"] / "data.csv")
        f.write_bytes(f.read_bytes() + b"CORRUPT")
        with self.assertRaises(GenerationError):
            read_active(*self.args)
        self.assertEqual(reconcile(*self.args)["status"], "RECOVERY_REQUIRED")

    def test_duplicate_json_keys_rejected(self):
        files = wb_files()
        raw = files["data.csv.meta.json"].decode()
        self.assertIn('"schema": 1', raw)
        files["data.csv.meta.json"] = raw.replace('"schema": 1',
                                                    '"schema": true, "schema": 1').encode()
        with self.assertRaisesRegex(GenerationError, "invalid JSON control document"):
            publish_batch(*self.args, files)

    def test_untrusted_paths_and_mismatched_wb_type_rejected(self):
        files = wb_files()
        files["../escape.csv"] = b"bad"
        with self.assertRaisesRegex(GenerationError, "out-of-scope"):
            publish_batch(*self.args, files)
        files = wb_files(dataset="wb_weekly_finance_buyout")
        with self.assertRaises(GenerationError):
            publish_batch(*self.args, files)

    def test_failing_precommit_does_not_mutate_legacy_canonical_paths(self):
        before = list((self.root / "База данных").rglob("*.csv"))
        def fail(stage):
            if stage == "after_descriptor":
                raise OSError("crash")
        with self.assertRaises(OSError):
            publish_batch(*self.args, wb_files(), fault=fail)
        self.assertEqual(list((self.root / "База данных").rglob("*.csv")), before)
        self.assertIsNone(read_active(*self.args))


if __name__ == "__main__":
    unittest.main()
