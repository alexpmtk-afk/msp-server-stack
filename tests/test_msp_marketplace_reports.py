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

    def _archive_file_snapshot(self):
        return {
            str(path.relative_to(self.root)): path.read_bytes()
            for path in self.root.rglob("*") if path.is_file()
        }

    def test_r1_ozon_rejects_corrupt_other_month_manifest_before_february(self):
        sample(self.source, ["report_year", "report_month", "row_number", "qty"], [
            {"report_year": "2026", "report_month": "2026-01", "row_number": "1", "qty": "5"}])
        first = import_csv(self.root, "ozon_final_realization", "ozon_laser_master", "2026-01", self.source)
        month = Path(first["annual_path"]).parent.parent / "monthly_source" / "ozon_laser_master__realization__2026-01.csv"
        manifest = month.with_name(month.name + ".meta.json")
        original = manifest.read_bytes()
        sample(self.source, ["report_year", "report_month", "row_number", "qty"], [
            {"report_year": "2026", "report_month": "2026-02", "row_number": "2", "qty": "8"}])
        for key, changed_value in [
            ("schema", 2), ("dataset", "ozon_current_orders_fbo"),
            ("cabinet", "ozon_novokshenov"), ("period", "2026-02"),
            ("bytes", 1234567), ("rows", 99), ("sha256", "0" * 64),
            ("status", "UNVERIFIED"),
        ]:
            with self.subTest(key=key):
                changed = json.loads(original.decode("utf-8"))
                changed[key] = changed_value
                manifest.write_text(json.dumps(changed), encoding="utf-8")
                baseline = self._archive_file_snapshot()
                self.assertFalse(verify(self.root)["ok"])
                with self.assertRaisesRegex(ValueError, "integrity/identity mismatch"):
                    import_csv(self.root, "ozon_final_realization", "ozon_laser_master",
                               "2026-02", self.source)
                self.assertEqual(self._archive_file_snapshot(), baseline)
                manifest.write_bytes(original)
        self.assertTrue(verify(self.root)["ok"])

    def test_r2_corrupt_annual_rejected_before_changing_month_or_backups(self):
        sample(self.source, ["report_year", "report_month", "row_number", "qty"], [
            {"report_year": "2026", "report_month": "2026-01", "row_number": "1", "qty": "5"}])
        first = import_csv(self.root, "ozon_final_realization", "ozon_laser_master", "2026-01", self.source)
        annual = Path(first["annual_path"])
        annual.write_bytes(annual.read_bytes().replace(b";5", b";9"))
        baseline = self._archive_file_snapshot()
        sample(self.source, ["report_year", "report_month", "row_number", "qty"], [
            {"report_year": "2026", "report_month": "2026-01", "row_number": "1", "qty": "6"}])
        with self.assertRaisesRegex(ValueError, "integrity/identity mismatch"):
            import_csv(self.root, "ozon_final_realization", "ozon_laser_master", "2026-01", self.source)
        self.assertEqual(self._archive_file_snapshot(), baseline)
        self.assertFalse(verify(self.root)["ok"])

    def test_ozon_preflight_compares_union_of_monthly_columns(self):
        monthly = [
            ("2026-01", "1", ["report_year", "report_month", "row_number", "qty"], "5"),
            ("2026-02", "2", ["report_year", "report_month", "row_number", "qty", "extra"], "8"),
            ("2026-03", "3", ["report_year", "report_month", "row_number", "qty"], "9"),
        ]
        for period, number, fields, qty in monthly:
            row = {"report_year": "2026", "report_month": period, "row_number": number, "qty": qty}
            if "extra" in fields:
                row["extra"] = "value"
            sample(self.source, fields, [row])
            result = import_csv(self.root, "ozon_final_realization", "ozon_laser_master",
                                period, self.source)
        self.assertEqual(result["annual_rows"], 3)
        self.assertTrue(verify(self.root)["ok"])

    def test_ozon_orphan_other_month_manifest_blocks_new_month(self):
        sample(self.source, ["report_year", "report_month", "row_number"], [
            {"report_year": "2026", "report_month": "2026-01", "row_number": "1"}])
        first = import_csv(self.root, "ozon_final_realization", "ozon_laser_master", "2026-01", self.source)
        month = Path(first["annual_path"]).parent.parent / "monthly_source" / "ozon_laser_master__realization__2026-01.csv"
        month.unlink()
        baseline = self._archive_file_snapshot()
        sample(self.source, ["report_year", "report_month", "row_number"], [
            {"report_year": "2026", "report_month": "2026-02", "row_number": "2"}])
        with self.assertRaisesRegex(ValueError, "pair required"):
            import_csv(self.root, "ozon_final_realization", "ozon_laser_master",
                       "2026-02", self.source)
        self.assertEqual(self._archive_file_snapshot(), baseline)

    def test_b5_corrupt_wb_cannot_be_recertified_on_merge(self):
        sample(self.source, ["reportId", "rrdId", "dateTo", "amount"], [
            {"reportId": "11", "rrdId": "1", "dateTo": "2026-10-11", "amount": "10"}])
        old = import_csv(self.root, "wb_weekly_finance_main", "wb_laser_master", "2026", self.source)
        csv_path = Path(old["path"])
        manifest_path = csv_path.with_name(csv_path.name + ".meta.json")
        csv_path.write_bytes(csv_path.read_bytes().replace(b";10", b";99"))
        damaged = csv_path.read_bytes()
        manifest = manifest_path.read_bytes()
        self.assertFalse(verify(self.root)["ok"])
        sample(self.source, ["reportId", "rrdId", "dateTo", "amount"], [
            {"reportId": "12", "rrdId": "2", "dateTo": "2026-10-18", "amount": "30"}])
        with self.assertRaisesRegex(ValueError, "integrity/identity mismatch"):
            import_csv(self.root, "wb_weekly_finance_main", "wb_laser_master", "2026", self.source)
        self.assertEqual(csv_path.read_bytes(), damaged)
        self.assertEqual(manifest_path.read_bytes(), manifest)
        self.assertFalse(verify(self.root)["ok"])

    def test_b5_orphan_manifest_or_csv_blocks_replacement(self):
        sample(self.source, ["posting_number", "status"], [
            {"posting_number": "X", "status": "open"}])
        old = import_csv(self.root, "ozon_current_orders_fbo", "ozon_dmitrieva", "2026-10", self.source)
        csv_path = Path(old["path"])
        manifest_path = csv_path.with_name(csv_path.name + ".meta.json")
        csv_path.unlink()
        sample(self.source, ["posting_number", "status"], [
            {"posting_number": "X", "status": "closed"}])
        with self.assertRaisesRegex(ValueError, "pair required"):
            import_csv(self.root, "ozon_current_orders_fbo", "ozon_dmitrieva", "2026-10", self.source)
        self.assertTrue(manifest_path.exists())
        self.assertFalse(csv_path.exists())

    def test_b5_corrupt_ozon_annual_blocks_month_update(self):
        sample(self.source, ["report_year", "report_month", "row_number", "qty"], [
            {"report_year": "2026", "report_month": "2026-01", "row_number": "1", "qty": "5"}])
        r = import_csv(self.root, "ozon_final_realization", "ozon_laser_master", "2026-01", self.source)
        annual = Path(r["annual_path"])
        annual.write_bytes(annual.read_bytes().replace(b";5", b";9"))
        sample(self.source, ["report_year", "report_month", "row_number", "qty"], [
            {"report_year": "2026", "report_month": "2026-01", "row_number": "1", "qty": "6"}])
        with self.assertRaisesRegex(ValueError, "integrity/identity mismatch"):
            import_csv(self.root, "ozon_final_realization", "ozon_laser_master", "2026-01", self.source)
        self.assertFalse(verify(self.root)["ok"])

    def test_corrupt_csv_detected(self):
        sample(self.source, ["accrual_id", "value"], [{"accrual_id": "1", "value": "5"}])
        r = import_csv(self.root, "ozon_current_accruals", "ozon_laser_master", "2026-10", self.source)
        with Path(r["path"]).open("ab") as f:
            f.write(b"CORRUPTION")
        self.assertFalse(verify(self.root)["ok"])


if __name__ == "__main__":
    unittest.main()
