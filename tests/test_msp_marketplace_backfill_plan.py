"""No network/credentials: synthetic six-cabinet 2026 backfill planning tests."""
import contextlib
import csv
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from apps.msp_marketplace_reports.archive import import_csv
from apps.msp_marketplace_reports.backfill_plan import build_backfill_plan
from apps.msp_marketplace_reports.ingest import run as ingest_run
from apps.msp_marketplace_reports.versioned_archive import import_csv_versioned


def inventory(cabinet, items):
    return {"cabinet": cabinet, "year": 2026, "status": "DISCOVERED_NOT_DOWNLOADED",
            "items": items}


def wb_report(report_id, report_type):
    return {"reportId": report_id, "reportType": report_type,
            "dateFrom": "2026-10-05", "dateTo": "2026-10-11"}


def csv_file(path, fields, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)
    return path


class BackfillPlanTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name) / "archive"
        self.source = Path(t.name) / "report.csv"
        self.asof = date(2026, 10, 30)

    def plan(self, discoveries=None):
        return build_backfill_plan(self.root, year=2026, as_of=self.asof,
                                   wb_discoveries=discoveries)

    def test_no_discovery_means_unknown_not_empty_and_no_fs_writes(self):
        data = self.plan()
        self.assertEqual(data["cabinet_count"], 6)
        self.assertEqual(data["network_calls"], 0)
        self.assertFalse(data["provider_coverage_proven"])
        self.assertEqual(data["action_counts"]["DISCOVER_REPORT_IDS"], 3)
        self.assertEqual(data["action_counts"]["DOWNLOAD_CLOSED_MONTH"], 27)
        self.assertEqual(data["action_counts"]["DOWNLOAD_CURRENT"], 9)
        self.assertEqual(len(data["tasks"]), 39)
        self.assertFalse(self.root.exists())

    def test_discovery_metadata_only_and_wb_verified_report_id_by_type(self):
        report_ids = [wb_report(11, 1), wb_report(12, 1), wb_report(13, 2)]
        details = inventory("wb_laser_master", report_ids)
        csv_file(self.source, ["reportId", "rrdId", "reportType", "dateTo"], [
            {"reportId": "11", "rrdId": "5", "reportType": "1", "dateTo": "2026-10-11"}])
        import_csv_versioned(self.root, "wb_weekly_finance_main",
                             "wb_laser_master", "2026", self.source)
        result = self.plan({"wb_laser_master": details})
        wb = [t for t in result["tasks"] if t["marketplace"] == "wb"
              and t["cabinet"] == "wb_laser_master"]
        self.assertEqual(len(wb), 3)
        states = {x["report_id"]: x["action"] for x in wb}
        self.assertEqual(states[11], "VERIFY_PROVIDER_COVERAGE")
        self.assertEqual(states[12], "DOWNLOAD_REPORT_DETAIL")
        self.assertEqual(states[13], "DOWNLOAD_REPORT_DETAIL")
        self.assertFalse(any("amount" in x for x in wb))

    def test_explicit_zero_wb_discovery_not_a_completeness_claim(self):
        result = self.plan({"wb_laser_master": inventory("wb_laser_master", [])})
        tasks = [t for t in result["tasks"]
                 if t.get("cabinet") == "wb_laser_master"]
        self.assertEqual(len(tasks), 2)
        self.assertTrue(all(t["status"] == "SOURCE_EMPTY_UNCONFIRMED" for t in tasks))

    def test_bad_discovery_rejected_no_archive_modifications(self):
        data = inventory("wb_laser_master", [wb_report(11, 1), wb_report(11, 2)])
        with self.assertRaisesRegex(ValueError, "duplicated reportId"):
            self.plan({"wb_laser_master": data})
        data = inventory("wb_laser_master", [wb_report(11, True)])
        with self.assertRaisesRegex(ValueError, "reportId/reportType malformed"):
            self.plan({"wb_laser_master": data})
        self.assertFalse(self.root.exists())

    def test_ozon_legacy_closed_month_verified_only_locally(self):
        csv_file(self.source, ["report_year", "report_month", "row_number", "qty"], [
            {"report_year": "2026", "report_month": "2026-01", "row_number": "1",
             "qty": "7"}])
        import_csv(self.root, "ozon_final_realization", "ozon_dmitrieva",
                   "2026-01", self.source)
        result = self.plan()
        jan = next(t for t in result["tasks"] if t.get("dataset") ==
                   "ozon_final_realization" and t["cabinet"] == "ozon_dmitrieva"
                   and t["period"] == "2026-01")
        self.assertEqual(jan["status"], "LOCAL_VERIFIED_NOT_PROVIDER_COMPLETE")
        self.assertEqual(jan["action"], "VERIFY_PROVIDER_COVERAGE")
        feb = next(t for t in result["tasks"] if t.get("dataset") ==
                   "ozon_final_realization" and t["cabinet"] == "ozon_dmitrieva"
                   and t["period"] == "2026-02")
        self.assertEqual(feb["action"], "DOWNLOAD_CLOSED_MONTH")

    def test_wb_list_fake_transport_outputs_planner_ready_no_financial_amount(self):
        reports = [{"reportId": 33, "reportType": 1, "dateFrom": "2026-01-01",
                    "dateTo": "2026-01-07", "retailAmountSum": "SENSITIVE_99001"}]
        def factory(**kwargs):
            return lambda req: (200, reports)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            data = ingest_run(["--root", str(self.root), "--creds-file", "/fake",
                               "wb-list", "--cabinet", "wb_laser_master",
                               "--year", "2026"], factory=factory)
        self.assertNotIn("SENSITIVE_99001", out.getvalue())
        self.assertEqual(data["items"], [wb_report(33, 1) | {
            "dateFrom": "2026-01-01", "dateTo": "2026-01-07"}])
        self.assertEqual(len(self.plan({"wb_laser_master": data})["tasks"]), 40)
        self.assertFalse(self.root.exists())

    def test_open_month_is_not_mislabeled_closed_final(self):
        data = self.plan()
        closed = [t for t in data["tasks"] if t.get("dataset") == "ozon_final_realization"]
        self.assertTrue(all(t["period"] < "2026-10" for t in closed))
        current = [t for t in data["tasks"] if t.get("dataset", "").startswith("ozon_current_")]
        self.assertTrue(all(t["period"] == "2026-10" for t in current))


if __name__ == "__main__":
    unittest.main()
