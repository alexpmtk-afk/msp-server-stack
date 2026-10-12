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

    def test_csv_mode_five_sources_without_google_auth_or_sqlite(self):
        import contextlib
        import csv
        import io
        import json
        import os
        from unittest.mock import patch

        def csvdata(source):
            buf = io.StringIO(newline="")
            writer = csv.writer(buf)
            if source == "laser_new":
                head = [""] * 38
                head[4], head[5], head[37] = ("Артикул", "Наименование", "Себестоимость без прибыли")
                row = [""] * 38
                row[4], row[5], row[37] = ("ТРН-1", "Лазер товар", "150,20")
                writer.writerows([head, row])
            else:
                headers = ("Артикулы" if source == "laser_old" else "Артикул",
                           "Название товара", "Себестоимость", "Ссылка на спецификацию")
                writer.writerows([headers, ["A-1", "Товар", "100,40", ""]])
            return buf.getvalue().encode("utf-8")

        gids = {gid: name for name, gid in mod.CSV_SOURCE_GIDS.items()}
        calls = []
        class FakeResponse:
            headers = {"Content-Type":"text/csv; charset=utf-8"}
            def __init__(self, raw):
                self.raw = raw
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self, limit):
                return self.raw[:limit]
        def fake_open(request, timeout):
            from urllib.parse import parse_qs, urlsplit
            gid = parse_qs(urlsplit(request.full_url).query)["gid"][0]
            source = gids[gid]
            calls.append(source)
            return FakeResponse(csvdata(source))

        with tempfile.TemporaryDirectory() as d:
            db = Path(d)/"should-not-be-created.sqlite3"
            with patch.dict(os.environ,{
                "MSP_COST_TRANSPORT":"csv",
                "MSP_COST_MAIN_SHEET_ID":"abcDEFGHIJKLMNOP1234567",
                "MSP_COST_LASER_SHEET_ID":"abcDEFGHIJKLMNOP1234567"
            }),patch.object(mod.urllib.request,"urlopen",fake_open):
                with contextlib.redirect_stdout(io.StringIO()) as capture:
                    rc = mod.main(["--preflight","--db",str(db)])
            self.assertEqual(rc,0)
            self.assertFalse(db.exists())
            self.assertEqual(len(calls),5)
            self.assertTrue(all(x["read_only"] for x in json.loads(capture.getvalue())["product_cost_sync"]))

    def test_csv_mode_rejects_login_html_and_overlarge_content(self):
        with self.assertRaises(ValueError):
            mod.transform_csv("ultra",b"<!doctype html><html>Login</html>")
        with self.assertRaises(ValueError):
            mod.transform_csv("ultra",b"x" * 20_000_001)

    def test_missing_cost_has_explicit_null_not_zero_or_error(self):
        rows=self.rows(article="MISS-01",price="")
        records,issues=mod.parse_rows("ultra",rows)
        self.assertEqual((len(records),len(issues)),(0,1))
        statuses=mod.classify_source_rows("ultra",rows)
        self.assertEqual(statuses[0]["cost_status"],"no_data")
        mod.store_source(self.con,"ultra",records,issues,"2026-10-12T12:00:00Z",1,
                         status_rows=statuses)
        status=self.con.execute(
            "SELECT cost_status,cost_decimal,cost_display_status,last_confirmed_cost_decimal "
            "FROM v_product_cost_source_status").fetchone()
        self.assertEqual(status,("no_data",None,"Нет данных",None))

    def test_last_confirmed_cost_kept_separate_from_current_invalid(self):
        good=self.rows(article="TEST-01",price="115")
        records,issues=mod.parse_rows("more",good)
        mod.store_source(self.con,"more",records,issues,"2026-10-12T12:00:00Z",1,
                         status_rows=mod.classify_source_rows("more",good))
        broken=self.rows(article="TEST-01",price="#REF!")
        records,issues=mod.parse_rows("more",broken)
        mod.store_source(self.con,"more",records,issues,"2026-10-13T12:00:00Z",1,
                         status_rows=mod.classify_source_rows("more",broken))
        row=self.con.execute(
            "SELECT cost_status,cost_decimal,last_confirmed_cost_decimal "
            "FROM v_product_cost_source_status").fetchone()
        self.assertEqual(row,("invalid_value",None,"115"))
        self.assertEqual(self.con.execute("SELECT cost_decimal FROM product_cost_current").fetchone()[0],"115")

    def test_duplicate_articles_report_both_rows_without_invented_price(self):
        rows=self.rows(article="DUP-01",price="100")
        rows.append(["dup-01","Another","150"])
        rec,issues=mod.parse_rows("zavoz",rows)
        statuses=mod.classify_source_rows("zavoz",rows)
        self.assertEqual((len(rec),len(issues)),(0,2))
        self.assertEqual([s["cost_status"] for s in statuses],["duplicate_article"]*2)
        mod.store_source(self.con,"zavoz",rec,issues,"2026-10-12T12:00:00Z",2,status_rows=statuses)
        self.assertEqual(
            self.con.execute("SELECT count(*) FROM v_product_cost_source_status "
                             "WHERE cost_decimal IS NULL").fetchone()[0],2)

    def test_repaired_price_becomes_available_and_updates_revision(self):
        bad=self.rows(article="A-01",price="")
        rec,issues=mod.parse_rows("ultra",bad)
        mod.store_source(self.con,"ultra",rec,issues,"2026-10-12T12:00:00Z",1,
                         status_rows=mod.classify_source_rows("ultra",bad))
        repaired=self.rows(article="A-01",price="17,20")
        rec,issues=mod.parse_rows("ultra",repaired)
        mod.store_source(self.con,"ultra",rec,issues,"2026-10-13T12:00:00Z",1,
                         status_rows=mod.classify_source_rows("ultra",repaired))
        row=self.con.execute(
            "SELECT cost_status,cost_decimal,last_confirmed_cost_decimal "
            "FROM v_product_cost_source_status").fetchone()
        self.assertEqual(row,("available","17.20","17.20"))
        self.assertEqual(self.con.execute("SELECT count(*) FROM product_cost_current").fetchone()[0],1)

    def test_source_missing_row_never_shows_as_current(self):
        first=self.rows(article="A-01",price="")
        rec,issues=mod.parse_rows("ultra",first)
        mod.store_source(self.con,"ultra",rec,issues,"2026-10-12T12:00:00Z",1,
                         status_rows=mod.classify_source_rows("ultra",first))
        second=self.rows(article="A-02",price="9")
        rec,issues=mod.parse_rows("ultra",second)
        mod.store_source(self.con,"ultra",rec,issues,"2026-10-13T12:00:00Z",1,
                         status_rows=mod.classify_source_rows("ultra",second))
        current=self.con.execute("SELECT internal_article,cost_status "
                                 "FROM v_product_cost_source_status").fetchall()
        self.assertEqual(current,[("A-02","available")])

    def test_google_auth_accepts_only_two_explicit_credential_types(self):
        self.assertEqual(mod.google_auth_mode({"type": "authorized_user"}), "authorized_user")
        self.assertEqual(mod.google_auth_mode({"type": "service_account"}), "service_account")
        for forbidden in ("external_account", "impersonated_service_account", "", None):
            with self.subTest(forbidden=forbidden):
                with self.assertRaises(ValueError):
                    mod.google_auth_mode({"type": forbidden})
        with self.assertRaises(ValueError):
            mod.google_auth_mode(None)

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
