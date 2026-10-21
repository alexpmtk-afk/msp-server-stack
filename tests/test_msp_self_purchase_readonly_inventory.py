import importlib.util
import json
import pathlib
import sqlite3
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/remote/msp_self_purchase_readonly_inventory.py"
spec = importlib.util.spec_from_file_location("msp_self_audit", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TestMspSelfAudit(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = pathlib.Path(self.temp.name) / "msp.sqlite3"
        con = sqlite3.connect(self.db)
        con.executescript("""
          CREATE TABLE product_listing(marketplace TEXT,store TEXT,marketplace_sku TEXT,first_seen_at TEXT);
          CREATE TABLE self_purchase(marketplace TEXT,store TEXT,marketplace_sku TEXT,quantity INTEGER,
                                     purchase_date TEXT,review_date TEXT,review_url TEXT);
          CREATE TABLE self_purchase_plan(marketplace TEXT,store TEXT,marketplace_sku TEXT,is_current INTEGER);
          CREATE TABLE self_purchase_revision(revision_id INTEGER);
          CREATE TABLE price_event(source_segment TEXT,event_date TEXT,marketplace_sku TEXT);
          CREATE TABLE sync_run(source TEXT,status TEXT,finished_at TEXT,run_id INTEGER);
          CREATE TABLE sync_error(error_id INTEGER);
          INSERT INTO product_listing VALUES('wb','laser','123456789','2026-09-01');
          INSERT INTO self_purchase VALUES('wb','laser','123456789',2,'2026-09-02',NULL,'');
          INSERT INTO self_purchase VALUES('wb','laser','123456789',1,'2026-09-04','2026-09-05','https://example.invalid/1');
          INSERT INTO self_purchase_plan VALUES('wb','laser','123456789',1);
          INSERT INTO price_event VALUES('current','2026-09-03','123456789');
          INSERT INTO sync_run VALUES('self_purchase','success','2026-10-21T08:00:00',1);
        """)
        con.commit()
        con.close()

    def test_readonly_aggregates_without_sku_leaks(self):
        before = self.db.read_bytes()
        r = module.audit(str(self.db))
        self.assertEqual(r["result"], "PASS_READONLY")
        self.assertEqual(r["completed"]["events"], 2)
        self.assertEqual(r["completed"]["units"], 3)
        self.assertEqual(r["completed"]["rows_with_review_url"], 1)
        self.assertEqual(r["completed"]["distinct_listings"], 1)
        self.assertEqual(r["planned"]["current_rows"], 1)
        self.assertEqual(r["catalog_mapping"]["completed_without_listing"], 0)
        self.assertNotIn("123456789", json.dumps(r))
        self.assertNotIn("example.invalid", json.dumps(r))
        self.assertEqual(before, self.db.read_bytes())

    def test_missing_table_fails_closed(self):
        con = sqlite3.connect(self.db)
        con.execute("DROP TABLE self_purchase_revision")
        con.commit()
        con.close()
        r = module.audit(str(self.db))
        self.assertEqual(r["result"], "SCHEMA_GAP")
        self.assertIn("self_purchase_revision", r["missing_tables"])


if __name__ == "__main__":
    unittest.main()
