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
