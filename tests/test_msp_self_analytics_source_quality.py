"""No-network source quality tests with no real SKU, tokens or order data."""
import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("msp_self_source_quality", ROOT / "apps/msp_self_analytics/source_quality.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TestSourceQuality(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def csv(self, name, headers, records):
        path = self.root / name
        with path.open("w", encoding="utf-8", newline="") as stream:
            w = csv.DictWriter(stream, fieldnames=headers)
            w.writeheader()
            w.writerows(records)
        return path

    def sample(self, duplicate=False, invalid=False):
        core = ["мп", "магазин", "market_article"]
        catalog = self.csv("catalog.csv", core, [
            dict(zip(core, ("wb", "laser", "123456789"))),
            dict(zip(core, ("oz", "novok", "987654321"))),
            dict(zip(core, ("wb", "laser", "111222333"))),
        ])
        sale_cols = core + ["остаток ФБС", "остаток ФБО", "Продажи (шт) окт.26", "Продажи (шт) сент.26"]
        rows = [
            dict(zip(sale_cols, ("wb", "laser", "123456789", "0", "2", "4", "0"))),
            dict(zip(sale_cols, ("oz", "novok", "987654321", "null", "5", "3", "2"))),
        ]
        if duplicate:
            rows.append(rows[0].copy())
        if invalid:
            rows.append(dict(zip(sale_cols, ("wb", "laser", "", "3", "0", "2", "2"))))
        sales = self.csv("sales.csv", sale_cols, rows)
        order_cols = core + ["Заказы (шт) окт.26"]
        orders = self.csv("orders.csv", order_cols, [
            dict(zip(order_cols, ("wb", "laser", "123456789", "5"))),
            dict(zip(order_cols, ("oz", "novok", "987654321", "0"))),
        ])
        return catalog, sales, orders

    def test_own_wb_oz_data_join_and_no_sku_leak(self):
        result = module.audit(*self.sample(), period="окт.26", previous_period="сент.26")
        self.assertEqual(result["result"], "PASS_SOURCE_JOIN")
        self.assertEqual(result["per_marketplace"]["WB"]["catalog_listings"], 2)
        self.assertEqual(result["per_marketplace"]["WB"]["catalog_missing_sales"], 1)
        self.assertEqual(result["per_marketplace"]["WB"]["current_sales_and_positive_orders_and_stock"], 1)
        self.assertEqual(result["per_marketplace"]["OZ"]["positive_current_sales"], 1)
        self.assertEqual(result["per_marketplace"]["OZ"]["positive_fbo_stock"], 1)
        self.assertEqual(result["per_marketplace"]["OZ"]["current_sales_and_positive_orders_and_stock"], 0)
        payload = json.dumps(result)
        for hidden in ("123456789", "987654321", "111222333", "laser", "novok"):
            self.assertNotIn(hidden, payload)

    def test_reject_duplicate_business_keys_for_downstream_metrics(self):
        result = module.audit(*self.sample(duplicate=True), period="окт.26")
        self.assertEqual(result["result"], "KEY_QUALITY_GAP")
        self.assertEqual(result["row_issues"]["sales"]["duplicate_key_rows"], 1)

    def test_reject_missing_sku_without_leaking_content(self):
        result = module.audit(*self.sample(invalid=True), period="окт.26")
        self.assertEqual(result["result"], "KEY_QUALITY_GAP")
        self.assertEqual(result["row_issues"]["sales"]["invalid_key_rows"], 1)

    def test_unsupported_period_does_not_invent_values(self):
        with self.assertRaisesRegex(ValueError, "REQUIRED_SOURCE_HEADER_NOT_FOUND"):
            module.audit(*self.sample(), period="ноя.26")

    def test_null_not_equal_zero(self):
        self.assertIsNone(module.amount("null"))
        self.assertIsNone(module.amount(""))
        self.assertEqual(module.amount("0"), 0)
        self.assertEqual(module.amount("1,50"), module.amount("1.50"))


if __name__ == "__main__":
    unittest.main()
