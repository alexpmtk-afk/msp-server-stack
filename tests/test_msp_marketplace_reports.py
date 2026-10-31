"""No network, no production paths, no credentials required."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

from apps.msp_marketplace_reports.archive import import_csv, verify


def sample(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


class LocalArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "archive"
        self.source = Path(self.temp.name) / "source.csv"

    def test_wb_import_idempotent_and_merge(self):
        sample(self.source, ["reportId", "rrdId", "dateTo", "amount"], [
            {"reportId": "11", "rrdId": "1", "dateTo": "2026-09-13", "amount": "42"}])
        r1 = import_csv(self.root, "wb_weekly_finance_main", "wb_laser_master", "2026", self.source)
        self.assertTrue(r1["changed"])
        r2 = import_csv(self.root, "wb_weekly_finance_main", "wb_laser_master", "2026", self.source)
        self.assertFalse(r2["changed"])
        sample(self.source, ["reportId", "rrdId", "dateTo", "amount"], [
            {"reportId": "11", "rrdId": "1", "dateTo": "2026-09-13", "amount": "42"},
            {"reportId": "12", "rrdId": "2", "dateTo": "2026-09-20", "amount": "30"}])
        r3 = import_csv(self.root, "wb_weekly_finance_main", "wb_laser_master", "2026", self.source)
        self.assertEqual(r3["new_rows"], 1)
        self.assertTrue(verify(self.root)["ok"])

    def test_wb_main_and_buyout_have_independent_annual_ledgers(self):
        sample(self.source, ["reportId", "rrdId", "reportType", "dateTo"], [
            {"reportId": "101", "rrdId": "20", "reportType": "1", "dateTo": "2026-10-11"}])
        main = import_csv(self.root, "wb_weekly_finance_main", "wb_laser_master", "2026", self.source)
        sample(self.source, ["reportId", "rrdId", "reportType", "dateTo"], [
            {"reportId": "102", "rrdId": "21", "reportType": "2", "dateTo": "2026-10-11"}])
        buyout = import_csv(self.root, "wb_weekly_finance_buyout", "wb_laser_master", "2026", self.source)
        self.assertNotEqual(main["path"], buyout["path"])
        self.assertIn("/buyout/", buyout["path"])
        self.assertIn("/main/", main["path"])
        self.assertEqual(main["rows"], 1)
        self.assertEqual(buyout["rows"], 1)
        self.assertTrue(verify(self.root)["ok"])

    def test_wb_conflict_rejected(self):
        sample(self.source, ["reportId", "rrdId", "amount"], [{"reportId": "11", "rrdId": "1", "amount": "42"}])
        first = import_csv(self.root, "wb_weekly_finance_main", "wb_dmitrieva", "2026", self.source)
        old = Path(first["path"]).read_bytes()
        sample(self.source, ["reportId", "rrdId", "amount"], [{"reportId": "11", "rrdId": "1", "amount": "43"}])
        with self.assertRaises(ValueError):
            import_csv(self.root, "wb_weekly_finance_main", "wb_dmitrieva", "2026", self.source)
        self.assertEqual(Path(first["path"]).read_bytes(), old)

    def test_ozon_final_rebuild_annual(self):
        for period, number in [("2026-01", "1"), ("2026-02", "2")]:
            sample(self.source, ["report_year", "report_month", "row_number", "qty"], [
                {"report_year": "2026", "report_month": period, "row_number": number, "qty": "5"}])
            r = import_csv(self.root, "ozon_final_realization", "ozon_novokshenov", period, self.source)
        self.assertEqual(r["annual_rows"], 2)
        self.assertTrue(verify(self.root)["ok"])
        sample(self.source, ["report_year", "report_month", "row_number", "qty"], [
            {"report_year": "2026", "report_month": "2026-02", "row_number": "2", "qty": "8"}])
        r = import_csv(self.root, "ozon_final_realization", "ozon_novokshenov", "2026-02", self.source)
        self.assertTrue(r["annual_changed"])
        self.assertEqual(r["annual_rows"], 2)

    def test_ozon_annual_missing_detected(self):
        sample(self.source, ["report_year", "report_month", "row_number"], [
            {"report_year": "2026", "report_month": "2026-01", "row_number": "1"}])
        r = import_csv(self.root, "ozon_final_realization", "ozon_laser_master", "2026-01", self.source)
        Path(r["annual_path"]).unlink()
        self.assertFalse(verify(self.root)["ok"])

    def test_current_replaces_month(self):
        sample(self.source, ["posting_number", "status"], [{"posting_number": "A", "status": "awaiting"}])
        r1 = import_csv(self.root, "ozon_current_orders_fbo", "ozon_dmitrieva", "2026-10", self.source)
        sample(self.source, ["posting_number", "status"], [{"posting_number": "A", "status": "delivered"}])
        r2 = import_csv(self.root, "ozon_current_orders_fbo", "ozon_dmitrieva", "2026-10", self.source)
        self.assertTrue(r2["changed"])
        self.assertIn(b"delivered", Path(r2["path"]).read_bytes())
        self.assertTrue(verify(self.root)["ok"])

    def test_invalid_keys_cannot_write(self):
        sample(self.source, ["reportId", "rrdId"], [{"reportId": "11", "rrdId": ""},
                                                       {"reportId": "11", "rrdId": ""}])
        with self.assertRaises(ValueError):
            import_csv(self.root, "wb_weekly_finance_main", "wb_laser_master", "2026", self.source)
        self.assertEqual(verify(self.root)["files"], 0)

    def test_corrupt_csv_detected(self):
        sample(self.source, ["accrual_id", "value"], [{"accrual_id": "1", "value": "5"}])
        r = import_csv(self.root, "ozon_current_accruals", "ozon_laser_master", "2026-10", self.source)
        with Path(r["path"]).open("ab") as f:
            f.write(b"CORRUPTION")
        self.assertFalse(verify(self.root)["ok"])


if __name__ == "__main__":
    unittest.main()
