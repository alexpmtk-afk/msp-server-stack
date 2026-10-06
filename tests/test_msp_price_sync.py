import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('price_sync', ROOT/'apps/msp_data_sync/sync.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class PriceSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.c = m.dbopen(Path(self.tmp.name)/'db.sqlite')
        self.cfg = json.loads((ROOT/'config/msp-data/sync.json').read_text())
        self.header = ['дата','Артикул наш','Артикул мп','новая цена (зачеркнутая)','Скидка','Новая цена со скидкой','новая МИН цена','старая цена','направление действия','маркетплейс','магазин','примечание']
        self.row = ['06.10.26','Не внутренний артикул','123','1000','20','800','790','900','ниже','oz','laser','проверка']
    def tearDown(self):
        self.c.close()
        self.tmp.cleanup()
    def ingest(self, rows, source='price_journal_current'):
        n=m.prices(self.c,rows,m.begin_run(self.c,source),source,self.cfg)
        self.c.commit()
        return n
    def test_header_order_does_not_shift_sku_and_price(self):
        order=list(reversed(range(len(self.header))))
        self.ingest([[self.header[i] for i in order],[self.row[i] for i in order]])
        row=self.c.execute('select marketplace_sku,new_price,source_product_label from price_event').fetchone()
        self.assertEqual(tuple(row),('123','800','Не внутренний артикул'))
    def test_both_segments_retained_and_second_ingestion_no_growth(self):
        for source in ('price_journal_current','price_journal_archive'):
            self.ingest([self.header,self.row,self.row],source)
            self.assertEqual(self.ingest([self.header,self.row,self.row],source)['unchanged'],2)
        self.assertEqual(self.c.execute('select count(*) from v_price_history').fetchone()[0],4)
        self.assertEqual(self.c.execute('select count(distinct source_segment) from v_price_history').fetchone()[0],2)
    def test_modified_event_updates_instead_of_appending(self):
        self.ingest([self.header,self.row])
        changed=self.row.copy();changed[5]='850'
        self.assertEqual(self.ingest([self.header,changed])['updated'],1)
        self.assertEqual(self.c.execute('select count(*) from price_event').fetchone()[0],1)
    def test_invalid_row_logged_without_losing_valid_row(self):
        bad=self.row.copy();bad[2]='ABC'
        result=self.ingest([self.header,bad,self.row])
        self.assertEqual((result['rejected'],result['inserted']),(1,1))
        error=self.c.execute("select raw_json from sync_error where error like '%digits%' ").fetchone()
        self.assertEqual(json.loads(error[0]),bad)
    def test_sync_partial_commits_errors_and_continues_business_rows(self):
        import io
        out=io.StringIO();w=csv.writer(out);bad=self.row.copy();bad[2]='';w.writerows([self.header,bad,self.row])
        with patch.object(m,'fetch',return_value=(200,out.getvalue().encode(),None,None)):
            result=m.sync(self.c,self.cfg,'price_journal_current')
        self.assertEqual(result['status'],'partial')
        self.assertEqual(self.c.execute('select count(*) from price_event').fetchone()[0],1)
        self.assertGreater(self.c.execute('select count(*) from sync_error').fetchone()[0],0)
    def test_clean_same_snapshot_does_not_rewrite_business_rows(self):
        import io
        out=io.StringIO();csv.writer(out).writerows([self.header,self.row]);payload=out.getvalue().encode()
        with patch.object(m,'fetch',return_value=(200,payload,None,None)):
            m.sync(self.c,self.cfg,'price_journal_current')
            self.c.execute('create table mutations(n integer)')
            self.c.execute('create trigger watch_prices after update on price_event begin insert into mutations values(1); end')
            self.c.commit()
            result=m.sync(self.c,self.cfg,'price_journal_current')
        self.assertEqual(result['status'],'unchanged_snapshot')
        self.assertEqual(self.c.execute('select count(*) from mutations').fetchone()[0],0)
    def test_ascii_sku_and_quantity_validation(self):
        for value in ['١٢٣','123.0','1e3','']:
            with self.assertRaises(ValueError):m.sku(value)
        for value in ['1.5','0','-2','NaN']:
            with self.assertRaises(ValueError):m.qty(value)
        self.assertEqual(m.qty('2,0'),2)

if __name__=='__main__':unittest.main()
