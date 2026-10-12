import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest

PATH = Path(__file__).resolve().parents[1] / "apps/msp_product_costs/sync.py"
spec = importlib.util.spec_from_file_location("msp_cost_sync", PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class ProductCostTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.execute(
            "CREATE TABLE product_listing(marketplace TEXT,store TEXT,marketplace_sku TEXT,"
            "internal_article_normalized TEXT)")
    def tearDown(self):
        self.con.close()

    def rows(self, article="ТРН-01", price="123,40"):
        return [["Артикул", "Название товара", "Себестоимость", "Ссылка на спецификацию"],
                [article, "Тест товар", price, "https://example.org/specific"]]

    def test_decimal_exact_russian_format_and_bad_sheet_error(self):
        self.assertEqual(mod.decimal_cost("1\u00a0300,50"), "1300.50")
        for x in ("#REF!", "", " - ", "0", "-12", "1,2,3"):
            with self.subTest(x=x):
                with self.assertRaises(ValueError):
                    mod.decimal_cost(x)

    def test_idempotent_and_cost_revision(self):
        rows=self.rows()
        rec,issues=mod.parse_rows("ultra",rows)
        self.assertFalse(issues)
        one=mod.store_source(self.con,"ultra",rec,issues,"2026-10-12T00:00:00Z",1)
        self.assertEqual(one["inserted"],1)
        same=mod.store_source(self.con,"ultra",rec,issues,"2026-10-13T00:00:00Z",1)
        self.assertEqual((same["inserted"],same["changed"],same["unchanged"]),(0,0,1))
        rec2,issues2=mod.parse_rows("ultra",self.rows(price="125,70"))
        update=mod.store_source(self.con,"ultra",rec2,issues2,"2026-10-14T00:00:00Z",1)
        self.assertEqual(update["changed"],1)
        self.assertEqual(self.con.execute("SELECT count(*) FROM product_cost_revision").fetchone()[0],1)
        old,new=self.con.execute("SELECT prior_cost_decimal,updated_cost_decimal FROM product_cost_revision").fetchone()
        self.assertEqual((old,new),("123.40","125.70"))
        again=mod.store_source(self.con,"ultra",rec2,issues2,"2026-10-15T00:00:00Z",1)
        self.assertEqual(again["unchanged"],1)
        self.assertEqual(self.con.execute("SELECT count(*) FROM product_cost_revision").fetchone()[0],1)

    def test_different_productions_and_variants_do_not_collide(self):
        old_rows=[["Артикулы","Название товара","Себестоимость"],["ТРН-01","A","150,01"]]
        new_rows=[["Артикул","Наименование","Себестоимость без прибыли"],["ТРН-01","A","90,11"]]
        old,errs=mod.parse_rows("laser_old",old_rows)
        self.assertFalse(errs)
        new,errs=mod.parse_rows("laser_new",new_rows)
        self.assertFalse(errs)
        mod.store_source(self.con,"laser_old",old,[],"2026-10-12T00:00:00Z",1)
        mod.store_source(self.con,"laser_new",new,[],"2026-10-12T00:00:00Z",1)
        self.assertEqual(self.con.execute("SELECT count(*) FROM product_cost_current").fetchone()[0],2)
        costs=self.con.execute("SELECT variant,cost_decimal FROM product_cost_current ORDER BY variant").fetchall()
        self.assertEqual(costs,[("with_profit_legacy","150.01"),("without_profit_current","90.11")])

    def test_invalid_and_duplicate_do_not_overwrite_last_good_cost(self):
        records,errors=mod.parse_rows("more",self.rows(article="UW-01",price="220"))
        mod.store_source(self.con,"more",records,errors,"2026-10-12T00:00:00Z",1)
        bad,issues=mod.parse_rows("more",self.rows(article="UW-01",price="#REF!"))
        self.assertEqual(len(issues),1)
        result=mod.store_source(self.con,"more",bad,issues,"2026-10-13T00:00:00Z",1)
        self.assertEqual(result["status"],"partial")
        self.assertEqual(self.con.execute("SELECT cost_decimal FROM product_cost_current").fetchone()[0],"220")
        dup=self.rows(article="UW-01",price="300")
        dup.append(["uw-01","Other name","301"])
        parsed,issues=mod.parse_rows("more",dup)
        self.assertEqual((len(parsed),len(issues)),(0,2))
        mod.store_source(self.con,"more",parsed,issues,"2026-10-14T00:00:00Z",2)
        self.assertEqual(self.con.execute("SELECT cost_decimal FROM product_cost_current").fetchone()[0],"220")

    def test_history_never_deleted_when_snapshot_missing_row(self):
        rec,err=mod.parse_rows("zavoz",self.rows(article="DON-01",price="430"))
        mod.store_source(self.con,"zavoz",rec,err,"2026-10-12T00:00:00Z",1)
        missing=[self.rows()[0],["DON-02","New","350"]]
        rec2,err2=mod.parse_rows("zavoz",missing)
        mod.store_source(self.con,"zavoz",rec2,err2,"2026-10-13T00:00:00Z",1)
        self.assertEqual(self.con.execute("SELECT count(*) FROM product_cost_current").fetchone()[0],2)

    def test_listing_link_is_nonexclusive_and_source_traceable(self):
        self.con.execute("INSERT INTO product_listing VALUES('oz','laser','123456','трн-01')")
        rec,errors=mod.parse_rows("ultra",self.rows())
        mod.store_source(self.con,"ultra",rec,errors,"2026-10-12T00:00:00Z",1)
        result=self.con.execute("SELECT marketplace,store,marketplace_sku FROM v_product_cost_listing_matches").fetchone()
        self.assertEqual(result,("oz","laser","123456"))

    def test_preflight_does_not_open_or_create_sqlite(self):
        import contextlib
        import io
        import json
        example = {
            "ultra": self.rows(article="A1"),
            "zavoz": self.rows(article="B2"),
            "more": self.rows(article="C3"),
            "laser_old": [["Артикулы", "Название товара", "Себестоимость"], ["D4", "X", "19,40"]],
            "laser_new": [["Артикул", "Наименование", "Себестоимость без прибыли"], ["D4", "X", "9,20"]],
        }
        with tempfile.TemporaryDirectory() as d:
            fixture=Path(d)/"synthetic.json"
            db=Path(d)/"msp.sqlite3"
            fixture.write_text(json.dumps(example,ensure_ascii=False),encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()) as buf:
                code=mod.main(["--preflight","--db",str(db),"--fixture",str(fixture)])
            self.assertEqual(code,0)
            self.assertFalse(db.exists())
            self.assertTrue(all(x["read_only"] for x in json.loads(buf.getvalue())["product_cost_sync"]))

    def test_source_header_mismatch_is_fail_closed(self):
        with self.assertRaises(ValueError):
            mod.parse_rows("laser_new",[["Артикул","Название товара","Себестоимость"],["A","B","1"]])
        with self.assertRaises(ValueError):
            mod.parse_rows("unreviewed",[])

if __name__ == "__main__":
    unittest.main()
