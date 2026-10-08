import importlib.util
import tempfile
import unittest
import sys
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "apps" / "msp_data_sync" / "sync.py"
spec = importlib.util.spec_from_file_location("msp_data_sync", MODULE_PATH)
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "msp.sqlite3"
        self.con = m.dbopen(self.db)
        self.cfg = {"legal_entity_store_mapping": {"ЛМ": "laser", "НМБ": "novok"}}

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def test_product_and_self_purchase_idempotent(self):
        product_rows = [
            ["мп", "магазин", "market_article", "артикул_мп", "артикул_наш", "артикул_наш_▼", "наименование 1С"],
            ["wb", "laser", "1110110146", "ABC-1", "INT-1", "int-1", "Товар 1"],
            ["oz", "novok", "1402015741", "UW-2808", "UW-2808", "uw-2808", "Будка микро"],
        ]
        run = m.begin_run(self.con, "product_catalog")
        c1 = m.product(self.con, product_rows, run)
        self.con.commit()
        self.assertEqual(c1["inserted"], 2)
        self.assertEqual(c1["rejected"], 0)

        run2 = m.begin_run(self.con, "product_catalog")
        c2 = m.product(self.con, product_rows, run2)
        self.con.commit()
        self.assertEqual(c2["unchanged"], 2)
        self.assertEqual(self.con.execute("select count(*) from product_listing").fetchone()[0], 2)

        self_rows = [
            ["МП", "ЮЛ", "Артикул МП", "Артикул наш", "Название товара", "Кол-во выкупов", "Дата выкупа", "Дата отзыва", "Ссылка на отзыв", "Черновик отзывов"],
            ["WB", "ЛМ", "1110110146", "INT-1", "Товар 1", "2", "10.06.2026", "17.06.2026", "https://example.test/review", ""],
        ]
        run3 = m.begin_run(self.con, "self_purchase")
        c3 = m.selfbuy(self.con, self_rows, run3, self.cfg)
        self.con.commit()
        self.assertEqual(c3["inserted"], 1)
        self.assertEqual(c3["rejected"], 0)
        row = self.con.execute("select marketplace,store,marketplace_sku,quantity,purchase_date from self_purchase").fetchone()
        self.assertEqual(tuple(row), ("wb", "laser", "1110110146", 2, "2026-06-10"))

    def test_current_store_header_accepts_novok_with_no_legal_entity(self):
        product_rows = [
            ["мп", "магазин", "market_article", "артикул_мп", "артикул_наш", "артикул_наш_▼", "наименование 1С"],
            ["wb", "novok", "985606445", "MR.17", "MR.17", "mr.17", "Товар"],
        ]
        m.product(self.con, product_rows, m.begin_run(self.con, "product_catalog"))
        self.con.commit()
        header = ["мп", "магазин", "Артикул МП", "Артикул наш", "Название товара", "Кол-во выкупов",
                  "Дата выкупа", "Дата отзыва", "Ссылка на отзыв", "Черновик отзывов"]
        rows = [header,
                ["wb", "novok", "985606445", "MR.17", "Товар", "1", "12.05.2026", "", "", ""],
                ["wb", "novok", "985606445", "MR.17", "Товар", "1", "10.05.2026", "", "", ""]]
        first = m.selfbuy(self.con, rows, m.begin_run(self.con, "self_purchase"), self.cfg)
        self.con.commit()
        self.assertEqual((first["inserted"], first["rejected"]), (2, 0))
        entries = self.con.execute("select store, legal_entity from self_purchase order by purchase_date").fetchall()
        self.assertEqual([tuple(x) for x in entries], [("novok", ""), ("novok", "")])
        second = m.selfbuy(self.con, rows, m.begin_run(self.con, "self_purchase"), self.cfg)
        self.con.commit()
        self.assertEqual((second["unchanged"], second["rejected"]), (2, 0))
        self.assertEqual(self.con.execute("select count(*) from self_purchase").fetchone()[0], 2)

    def test_current_store_header_never_uses_legacy_legal_mapping(self):
        product_rows = [
            ["мп", "магазин", "market_article", "артикул_мп", "артикул_наш", "артикул_наш_▼", "наименование 1С"],
            ["wb", "novok", "985606445", "MR.17", "MR.17", "mr.17", "Товар"],
        ]
        m.product(self.con, product_rows, m.begin_run(self.con, "product_catalog"))
        self.con.commit()
        header = ["мп", "магазин", "Артикул МП", "Артикул наш", "Название товара",
                  "Кол-во выкупов", "Дата выкупа", "Дата отзыва", "Ссылка на отзыв", "Черновик отзывов"]
        rows = [header, ["wb", "laser", "985606445", "MR.17", "Товар", "1", "12.05.2026", "", "", ""]]
        result = m.selfbuy(self.con, rows, m.begin_run(self.con, "self_purchase"), self.cfg)
        self.con.commit()
        self.assertEqual((result["inserted"], result["rejected"]), (0, 1))
        self.assertEqual(self.con.execute("select count(*) from self_purchase").fetchone()[0], 0)

    def test_current_store_header_rejects_unrecognized_store(self):
        header = ["мп", "магазин", "Артикул МП", "Артикул наш", "Название товара",
                  "Кол-во выкупов", "Дата выкупа", "Дата отзыва", "Ссылка на отзыв", "Черновик отзывов"]
        rows = [header, ["wb", "ЛМ", "1110110146", "INT", "Товар", "1", "12.05.2026", "", "", ""]]
        result = m.selfbuy(self.con, rows, m.begin_run(self.con, "self_purchase"), self.cfg)
        self.con.commit()
        self.assertEqual(result["rejected"], 1)

    def self_purchase_header(self):
        return ["мп", "магазин", "Артикул МП", "Артикул наш", "Название товара",
                "Кол-во выкупов", "Дата выкупа", "Дата отзыва", "Ссылка на отзыв", "Черновик отзывов"]

    def seed_listing(self):
        catalog = [
            ["мп", "магазин", "market_article", "артикул_мп", "артикул_наш", "артикул_наш_▼", "наименование 1С"],
            ["wb", "laser", "1535826937", "A", "INT", "int", "Товар"]
        ]
        m.product(self.con, catalog, m.begin_run(self.con, "product_catalog"))
        self.con.commit()

    def test_planned_rows_keep_optional_nulls_without_sync_error(self):
        rows = [self.self_purchase_header(),
                ["wb","laser","1535826937","INT","Товар","2","","","",""],
                ["oz","laser","","OTHER","Другой товар","","","","",""]]
        run = m.begin_run(self.con, "self_purchase")
        n = m.selfbuy(self.con,rows,run,self.cfg)
        self.con.commit()
        self.assertEqual((n['source_rows'],n['planned'],n['planned_inserted'],n['skipped_missing_sku'],n['rejected']), (2,1,1,1,0))
        self.assertEqual(self.con.execute("select count(*) from self_purchase").fetchone()[0],0)
        plans=self.con.execute("select source_row,marketplace_sku,quantity,purchase_date from v_self_purchase_plan order by source_row").fetchall()
        self.assertEqual([tuple(p) for p in plans], [(2,"1535826937",2,None)])
        self.assertEqual(self.con.execute("select count(*) from sync_error").fetchone()[0],0)
        rerun=m.selfbuy(self.con,rows,m.begin_run(self.con,"self_purchase"),self.cfg)
        self.con.commit()
        self.assertEqual((rerun['planned_unchanged'],rerun['planned_updated'],rerun['skipped_missing_sku'],rerun['rejected']),(1,0,1,0))

    def test_planned_date_completion_is_promoted_without_duplicates(self):
        self.seed_listing()
        planned=[self.self_purchase_header(),["wb","laser","1535826937","INT","Товар","2","","","",""]]
        n=m.selfbuy(self.con,planned,m.begin_run(self.con,"self_purchase"),self.cfg)
        self.con.commit()
        self.assertEqual(n['planned'],1)
        completed=[self.self_purchase_header(),["wb","laser","1535826937","INT","Товар","2","07.10.2026","","",""]]
        first=m.selfbuy(self.con,completed,m.begin_run(self.con,"self_purchase"),self.cfg)
        self.con.commit()
        self.assertEqual((first['inserted'],first['promoted'],first['rejected']), (1,1,0))
        self.assertEqual(self.con.execute("select count(*) from v_self_purchase_plan").fetchone()[0],0)
        self.assertEqual(self.con.execute("select quantity,purchase_date from self_purchase").fetchone()[:],(2,"2026-10-07"))
        again=m.selfbuy(self.con,completed,m.begin_run(self.con,"self_purchase"),self.cfg)
        self.con.commit()
        self.assertEqual((again['inserted'],again['updated'],again['unchanged'],again['rejected']),(0,0,1,0))

    def test_old_plan_updates_quantity_and_completed_row_requires_valid_quantity(self):
        self.seed_listing()
        base=[self.self_purchase_header(),["wb","laser","1535826937","INT","Товар","","","","",""]]
        m.selfbuy(self.con,base,m.begin_run(self.con,"self_purchase"),self.cfg)
        self.con.commit()
        base[1][5]="3"
        p=m.selfbuy(self.con,base,m.begin_run(self.con,"self_purchase"),self.cfg)
        self.con.commit()
        self.assertEqual((p['planned_updated'],p['rejected']), (1,0))
        self.assertEqual(self.con.execute("select quantity from v_self_purchase_plan").fetchone()[0],3)
        base[1][6]="07.10.2026";base[1][5]=""
        partial=m.selfbuy(self.con,base,m.begin_run(self.con,"self_purchase"),self.cfg)
        self.con.commit()
        self.assertEqual((partial['rejected'],partial['inserted']), (1,0))
        self.assertEqual(self.con.execute("select count(*) from v_self_purchase_plan").fetchone()[0],0)
        base[1][5]="3"
        final=m.selfbuy(self.con,base,m.begin_run(self.con,"self_purchase"),self.cfg)
        self.con.commit()
        self.assertEqual((final['inserted'],final['rejected']), (1,0))
        self.assertEqual(self.con.execute("select count(*) from self_purchase").fetchone()[0],1)

    def test_planned_removed_from_snapshot_is_not_active(self):
        rows=[self.self_purchase_header(),["wb","novok","123","ABC","Plan","","","","",""]]
        m.selfbuy(self.con,rows,m.begin_run(self.con,"self_purchase"),self.cfg)
        self.con.commit()
        self.assertEqual(self.con.execute("select count(*) from v_self_purchase_plan").fetchone()[0],1)
        m.selfbuy(self.con,[self.self_purchase_header()],m.begin_run(self.con,"self_purchase"),self.cfg)
        self.con.commit()
        self.assertEqual(self.con.execute("select count(*) from v_self_purchase_plan").fetchone()[0],0)
        self.assertEqual(self.con.execute("select count(*) from self_purchase_plan").fetchone()[0],1)

    def test_old_sync_run_schema_is_migrated_additively(self):
        self.con.execute("drop view if exists v_self_purchase_plan")
        self.con.execute("drop table if exists self_purchase_plan")
        self.con.execute("alter table sync_run rename to old_sync_run")
        self.con.execute("create table sync_run(run_id integer primary key autoincrement,source text,started_at text,finished_at text,status text,http_status integer,source_rows integer default 0,inserted integer default 0,updated integer default 0,unchanged integer default 0,rejected integer default 0,message text)")
        self.con.execute("drop table old_sync_run")
        self.con.commit()
        self.con.close()
        self.con=m.dbopen(self.db)
        cols=[x[1] for x in self.con.execute("pragma table_info(sync_run)")]
        self.assertIn("planned",cols)
        self.assertIn("skipped_missing_sku",cols)
        self.assertEqual(self.con.execute("select count(*) from v_self_purchase_plan").fetchone()[0],0)

    def test_snapshot_skip_still_reports_plan_count(self):
        import csv
        import io
        from unittest.mock import patch
        self.seed_listing()
        rows=[self.self_purchase_header(),
              ["wb","laser","1535826937","INT","Товар","2","","","",""],
              ["wb","laser","1535826937","INT","Товар","2","07.10.2026","","",""]]
        buf=io.StringIO();csv.writer(buf).writerows(rows)
        payload=buf.getvalue().encode('utf-8')
        cfg={"sources":{"self_purchase":{"gid":1108533081}},"spreadsheet_id":"not-used"}
        with patch.object(m,'fetch',return_value=(200,payload,None,None)):
            first=m.sync(self.con,cfg,'self_purchase')
            second=m.sync(self.con,cfg,'self_purchase')
        self.assertEqual((first['planned'],first['inserted'],first['rejected']), (1,1,0))
        self.assertEqual(second['status'],'unchanged_snapshot')
        self.assertEqual((second['planned'],second['unchanged']),(1,1))
        last=self.con.execute("select planned,source_rows,rejected from sync_run order by run_id desc limit 1").fetchone()
        self.assertEqual(tuple(last),(1,2,0))

    def test_blank_sku_excluded_with_or_without_date_without_errors(self):
        rows=[self.self_purchase_header(),
              ["wb","laser","","INT","Planned","","","","",""],
              ["oz","laser","   ","INT2","Completed?","1","07.10.2026","","",""]]
        result=m.selfbuy(self.con,rows,m.begin_run(self.con,"self_purchase"),self.cfg)
        self.con.commit()
        self.assertEqual((result['source_rows'],result['skipped_missing_sku'],result['planned'],result['rejected']), (2,2,0,0))
        self.assertEqual(self.con.execute("select count(*) from v_self_purchase_plan").fetchone()[0],0)
        self.assertEqual(self.con.execute("select count(*) from self_purchase").fetchone()[0],0)
        self.assertEqual(self.con.execute("select count(*) from sync_error").fetchone()[0],0)

    def test_legacy_active_blank_sku_plan_inactivated_on_new_policy(self):
        import csv
        import io
        from unittest.mock import patch
        stamp=m.now()
        self.con.execute(
            "insert into self_purchase_plan(source_row,marketplace,store,marketplace_sku,internal_article,product_name,quantity,purchase_date,review_date,review_url,review_draft,row_hash,first_seen_at,updated_at,is_current,last_change_run) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (84,"oz","laser",None,"OLD","Old plan",None,None,None,"","","legacy",stamp,stamp,1,0))
        self.con.commit()
        rows=[self.self_purchase_header(),
              ["oz","laser","","OLD","Old plan","","","","",""]]
        buf=io.StringIO();csv.writer(buf).writerows(rows);payload=buf.getvalue().encode()
        cfg={"sources":{"self_purchase":{"gid":1}},"spreadsheet_id":"not-used"}
        with patch.object(m,"fetch",return_value=(200,payload,None,None)):
            first=m.sync(self.con,cfg,"self_purchase")
            second=m.sync(self.con,cfg,"self_purchase")
        self.assertEqual(first["status"],"success")
        self.assertEqual((first["skipped_missing_sku"],first["planned"],first["rejected"]),(1,0,0))
        self.assertEqual(second["status"],"unchanged_snapshot")
        self.assertEqual((second["skipped_missing_sku"],second["planned"],second["unchanged"]),(1,0,0))
        self.assertEqual(self.con.execute("select count(*) from v_self_purchase_plan").fetchone()[0],0)
        self.assertEqual(self.con.execute("select is_current from self_purchase_plan where source_row=84").fetchone()[0],0)

    def test_empty_sku_plan_becomes_valid_when_source_filled(self):
        first=[self.self_purchase_header(),
               ["wb","laser","","INT","Plan","2","","","",""]]
        n=m.selfbuy(self.con,first,m.begin_run(self.con,"self_purchase"),self.cfg)
        self.con.commit()
        self.assertEqual((n["skipped_missing_sku"],n["planned"]),(1,0))
        first[1][2]="1535826937"
        result=m.selfbuy(self.con,first,m.begin_run(self.con,"self_purchase"),self.cfg)
        self.con.commit()
        self.assertEqual((result["planned_inserted"],result["skipped_missing_sku"],result["rejected"]),(1,0,0))
        self.assertEqual(self.con.execute("select marketplace_sku from v_self_purchase_plan").fetchone()[0],"1535826937")

    def test_sku_must_be_digits_only(self):
        with self.assertRaises(ValueError):
            m.sku("WB-123")

    def test_self_purchase_requires_catalog_match(self):
        rows = [
            ["МП", "ЮЛ", "Артикул МП", "Артикул наш", "Название товара", "Кол-во выкупов", "Дата выкупа", "Дата отзыва", "Ссылка на отзыв", "Черновик отзывов"],
            ["WB", "ЛМ", "999", "INT", "Нет в каталоге", "1", "10.06.2026", "", "", ""],
        ]
        run = m.begin_run(self.con, "self_purchase")
        counts = m.selfbuy(self.con, rows, run, self.cfg)
        self.con.commit()
        self.assertEqual(counts["rejected"], 1)
        self.assertEqual(self.con.execute("select count(*) from self_purchase").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
