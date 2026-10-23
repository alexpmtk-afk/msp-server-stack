"""Read-only on-demand arbitrary SKU selection regression tests."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from apps.msp_self_analytics.sku_request import (
    SkuRequestError, load_existing_series, plan_requested_sku, resolve_catalog_listing,
)


class SkuRequestTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.db = Path(self.dir.name) / "self.sqlite"
        con = sqlite3.connect(self.db)
        con.execute("""CREATE TABLE self_purchase
            (marketplace TEXT, store TEXT, marketplace_sku TEXT,
             purchase_date TEXT, review_date TEXT,
             quantity INTEGER, source_ordinal INTEGER)""")
        con.execute("""CREATE TABLE product_listing
            (marketplace TEXT, store TEXT, marketplace_sku TEXT,
             internal_article TEXT, product_name TEXT,
             PRIMARY KEY(marketplace,store,marketplace_sku))""")
        con.executemany("INSERT INTO product_listing VALUES (?,?,?,?,?)", [
            ("wb", "laser", "123456789", "INT-1", "Товар 1"),
            ("wb", "ultra", "123456789", "INT-2", "Товар 2"),
            ("wb", "laser", "456", "INT-3", "Товар 3"),
            ("wb", "laser", "666", "INT-4", "Товар 4"),
            ("wb", "ultra", "666", "INT-4", "Товар 4"),
            ("wb", "laser", "777", "INT-5", "Товар без выкупов"),
            ("wb", "laser", "888", "INT-6", "Одинаковый SKU 6"),
            ("oz", "novok", "888", "INT-6", "Одинаковый SKU 6"),
        ])
        events = [
            ("wb", "laser", "123456789", "2026-07-24", "2026-08-05", 5, 1),
            ("wb", "laser", "123456789", "2026-07-30", "2026-08-07", 5, 2),
            ("wb", "laser", "123456789", "2026-08-07", "2026-08-18", 5, 3),
            ("wb", "ultra", "123456789", "2026-08-03", "2026-08-08", 1, 4),
            ("wb", "laser", "456", "2026-08-03", "2026-08-08", 1, 5),
            ("oz", "laser", "OZ.12-34", "2026-08-03", None, 1, 6),
            ("wb", "laser", "123456789", None, None, 5, 7),
            ("wb", "laser", "666", "2026-08-03", "2026-08-08", 1, 8),
            ("wb", "laser", "888", "2026-08-03", "2026-08-08", 1, 9),
            ("oz", "novok", "888", "2026-08-03", "2026-08-08", 1, 10),
        ]
        con.executemany("INSERT INTO self_purchase VALUES (?,?,?,?,?,?,?)", events)
        con.commit()
        con.close()

    def tearDown(self):
        self.dir.cleanup()

    def test_catalog_selects_unique_listing_without_marketplace_or_store(self):
        match = resolve_catalog_listing(self.db, sku="456")
        self.assertEqual((match["marketplace"], match["store"], match["source"]),
                         ("wb", "laser", "product_listing"))
        self.assertEqual(match["resolution"], "UNIQUE_CATALOG_LISTING")

    def test_catalog_selects_unique_purchase_series_among_multiple_stores(self):
        match = resolve_catalog_listing(self.db, sku="666")
        self.assertEqual((match["marketplace"], match["store"]), ("wb", "laser"))
        self.assertEqual(match["resolution"], "UNIQUE_LISTING_WITH_RECORDED_PURCHASES")

    def test_catalog_does_not_guess_between_two_stores_with_events(self):
        with self.assertRaisesRegex(SkuRequestError, "STORE_DISAMBIGUATION_REQUIRED"):
            resolve_catalog_listing(self.db, sku="123456789", marketplace="wb")
        unique = resolve_catalog_listing(self.db, sku="123456789",
                                         marketplace="wb", store="laser")
        self.assertEqual(unique["recorded_purchase_rows"], 3)

    def test_catalog_does_not_guess_between_marketplaces(self):
        with self.assertRaisesRegex(SkuRequestError, "MARKETPLACE_DISAMBIGUATION_REQUIRED"):
            resolve_catalog_listing(self.db, sku="888")
        match = resolve_catalog_listing(self.db, sku="888", marketplace="oz")
        self.assertEqual(match["store"], "novok")

    def test_catalog_not_inferred_from_nonexistent_or_internal_article(self):
        for item, reason in [
            ("9999999", "SKU_NOT_IN_PRODUCT_CATALOG"),
            ("INT-1", "INVALID_MARKETPLACE_SKU"),
            ("456' OR 1=1 --", "INVALID_MARKETPLACE_SKU"),
        ]:
            with self.assertRaisesRegex(SkuRequestError, reason):
                resolve_catalog_listing(self.db, sku=item)

    def test_catalog_listing_with_no_purchases_is_not_false_zero(self):
        match = resolve_catalog_listing(self.db, sku="777")
        self.assertEqual(match["recorded_purchase_rows"], 0)

    def test_one_sku_and_store_not_other_rows(self):
        rows = load_existing_series(self.db, marketplace="wb",
                                    store="laser", sku="123456789")
        self.assertEqual(len(rows), 3)
        self.assertEqual({r["quantity"] for r in rows}, {5})
        self.assertEqual([r["review_date"] for r in rows],
                         ["2026-08-05", "2026-08-07", "2026-08-18"])

    def test_all_review_checkpoints_preserved(self):
        plan = plan_requested_sku(self.db, marketplace="wb",
                                  store="laser", sku="123456789",
                                  as_of="2026-10-23",requested_days=30)
        self.assertEqual(plan["recorded_purchase_rows"], 3)
        self.assertEqual(plan["analysis_plan"]["series"]["planned_total_per_card"], 5)
        self.assertEqual([x["effective_days_each"]
                          for x in plan["analysis_plan"]["series"]["checkpoints"]],
                         [1, 10, 30])
        self.assertEqual(plan["analysis_plan"]["provider_read_count"], 6)
        self.assertEqual(plan["source_writes"], 0)

    def test_unknown_sku_and_query_injection_rejected(self):
        with self.assertRaisesRegex(SkuRequestError, "INVALID_WB_SKU"):
            load_existing_series(self.db, marketplace="wb", store="laser",
                                 sku="123456789' OR 1=1 --")
        with self.assertRaisesRegex(SkuRequestError, "SKU_HAS_NO_RECORDED_PURCHASES"):
            load_existing_series(self.db, marketplace="wb", store="laser",
                                 sku="9999999")
        with self.assertRaisesRegex(SkuRequestError, "SERIES_ROW_LIMIT_EXCEEDED"):
            load_existing_series(self.db, marketplace="wb", store="laser",
                                 sku="123456789", max_rows=2)

    def test_ozon_request_does_not_claim_wb_provider(self):
        report = plan_requested_sku(self.db, marketplace="oz", store="laser",
                                    sku="OZ.12-34", as_of="2026-10-23")
        self.assertEqual(report["status"], "OZON_PROVIDER_MAPPING_NOT_YET_VERIFIED")
        self.assertEqual(report["requests"], [])
        self.assertFalse(report["marketplace_actions_allowed"])

    def test_source_database_not_mutated(self):
        con = sqlite3.connect(self.db)
        before = con.execute("SELECT COUNT(*) FROM self_purchase").fetchone()[0]
        con.close()
        load_existing_series(self.db, marketplace="wb", store="laser",
                             sku="123456789")
        con = sqlite3.connect(self.db)
        after = con.execute("SELECT COUNT(*) FROM self_purchase").fetchone()[0]
        con.close()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
