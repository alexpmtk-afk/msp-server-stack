import importlib.util
import json
from pathlib import Path
import sqlite3
import unittest

HERE=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("prod_etl",HERE/"apps/msp_production_sync/sync.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class ProductionCatalogTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:")
        self.db.executescript("""
        CREATE TABLE product_listing(marketplace TEXT);
        CREATE TABLE sync_run(run_id INTEGER PRIMARY KEY);
        CREATE TABLE product_cost_current(article_key TEXT);
        """)
    def tearDown(self):
        self.db.close()

    def sewing(self):
        return [list(m.SOURCES["sewing"]["headers"]),
            ["МП","AB-1","Sample item","12","3","21.10.2026","789","30.10.2026",
             "31.10.2026","batch ready","Sewing"],
            ["РП","AB-1","Same SKU second order","25",None,"23.10.2026","790",
             None,None,None,"Camouflage"],
            ["РП",None,"Without article","5","5","21.10.2026","791",None,None,None,"Sewing"]]

    def metal(self):
        return [list(m.SOURCES["metal"]["headers"]),
            ["МП","ЛМ","M-1","Metal bracket","9","2","7","20.10.2026","INV-1",
             "X-012","25.10.2026","first batch","27.10.2026"],
            ["МП","АНТ","M-1","Second order","3",None,"3","21.10.2026",
             None,"X-013",None,None,None],
            ["МП","ЛМ",None,"Without SKU","1",None,"1","22.10.2026",
             None,None,"30.10.2026",None,"02.11.2026"],
            [None,None,None,None,None,None,"0",None,None,None,None,None,None]]

    def test_sewing_different_orders_same_article_and_missing_article(self):
        rows=m.parse_source("sewing",self.sewing())
        self.assertEqual(len(rows),3)
        self.assertEqual(rows[0]["placed_at_iso"],"2026-10-21")
        self.assertEqual(rows[1]["internal_article"],"AB-1")
        self.assertEqual(rows[2]["data_quality"],"review")
        self.assertIn("missing_article",json.loads(rows[2]["issues_json"]))
        out=m.save(self.db,"sewing",rows,"2026-10-26T09:00:00Z")
        self.assertEqual(out["current_rows"],3)
        self.assertEqual(out["missing_article"],1)
        self.assertEqual(self.db.execute("select count(*) from v_production_sewing").fetchone()[0],3)
        self.assertEqual(self.db.execute("select count(*) from v_production_metal").fetchone()[0],0)

    def test_metal_two_factories_and_formula_only_ignored(self):
        rows=m.parse_source("metal",self.metal())
        self.assertEqual(len(rows),3)
        self.assertEqual(rows[0]["production_site"],"ЛМ")
        self.assertEqual(rows[1]["production_site"],"АНТ")
        self.assertEqual(rows[1]["internal_article"],"M-1")
        self.assertEqual(rows[0]["remainder_qty_decimal"],"7")
        self.assertEqual(rows[2]["data_quality"],"review")
        m.save(self.db,"metal",rows,"2026-10-26T09:00:00Z")
        self.assertEqual(self.db.execute("select count(*) from v_production_metal").fetchone()[0],3)
        self.assertEqual(self.db.execute("select count(*) from production_row_revision where source='metal'").fetchone()[0],3)

    def test_idempotence_and_changed_confirmed_date_is_revision(self):
        rows=m.parse_source("sewing",self.sewing())
        first=m.save(self.db,"sewing",rows,"2026-10-26T09:00:00Z")
        second=m.save(self.db,"sewing",rows,"2026-10-26T10:00:00Z")
        self.assertEqual((first["inserted"],second["unchanged"]),(3,3))
        self.assertEqual(self.db.execute("select count(*) from production_row_revision").fetchone()[0],3)
        edited=self.sewing()
        edited[1][8]="05.11.2026"
        changed=m.save(self.db,"sewing",m.parse_source("sewing",edited),"2026-10-27T09:00:00Z")
        self.assertEqual(changed["changed"],1)
        self.assertEqual(self.db.execute("select count(*) from production_row_revision").fetchone()[0],4)
        self.assertEqual(self.db.execute("select confirmed_at_iso from v_production_sewing where source_row=2").fetchone()[0],"2026-11-05")

    def test_removed_snapshot_row_retired_not_deleted(self):
        rows=m.parse_source("sewing",self.sewing())
        m.save(self.db,"sewing",rows,"2026-10-26T09:00:00Z")
        next_rows=self.sewing()
        del next_rows[3]
        out=m.save(self.db,"sewing",m.parse_source("sewing",next_rows),"2026-10-27T09:00:00Z")
        self.assertEqual(out["retired"],1)
        self.assertEqual(self.db.execute("select count(*) from v_production_sewing").fetchone()[0],2)
        self.assertEqual(self.db.execute("select count(*) from production_sewing_order").fetchone()[0],3)

    def test_no_year_guess_and_incorrect_year_kept_as_source(self):
        self.assertEqual(m.date("27.10"),(None,"date_not_unambiguously_parseable"))
        self.assertEqual(m.date("31.02.2026"),(None,"invalid_date"))
        self.assertEqual(m.date("27.10.2016"),("2016-10-27",None))
        self.assertEqual(m.number(" 1\u00a0230,5 "),("1230.5",None))
        self.assertEqual(m.number("#REF!"),(None,"invalid_quantity"))

    def test_header_failure_prevents_import(self):
        with self.assertRaises(ValueError):
            m.parse_source("sewing",[["Wrong"]*11,["МП","A"]])
        with self.assertRaises(ValueError):
            m.parse_source("metal",[["Wrong"]*13,["МП","ЛМ","B"]])

    def test_quality_issue_does_not_remove_valid_order(self):
        rows=m.parse_source("metal",self.metal())
        m.save(self.db,"metal",rows,"2026-10-26T09:00:00Z")
        self.assertGreater(self.db.execute("select count(*) from production_data_issue").fetchone()[0],0)
        self.assertEqual(self.db.execute("select count(*) from production_metal_order where is_current=1").fetchone()[0],3)

if __name__=="__main__":
    unittest.main()
