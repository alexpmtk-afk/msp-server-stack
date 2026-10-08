import csv
import io
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
    def test_unmatched_price_event_is_history_not_sync_error(self):
        self.ingest([self.header,self.row])
        self.assertEqual(self.c.execute("select count(*) from price_event").fetchone()[0],1)
        self.assertEqual(self.c.execute("select count(*) from sync_error").fetchone()[0],0)
        self.assertEqual(self.c.execute("select count(*) from v_price_history where catalog_match_status='unmatched'").fetchone()[0],1)
    def test_identical_invalid_row_is_logged_once_across_runs(self):
        bad=self.row.copy();bad[2]='ABC'
        self.ingest([self.header,bad])
        self.ingest([self.header,bad])
        self.assertEqual(self.c.execute("select count(*) from sync_error").fetchone()[0],1)

    def test_ascii_sku_and_quantity_validation(self):
        for value in ['١٢٣','123.0','1e3','']:
            with self.assertRaises(ValueError):m.sku(value)
        for value in ['1.5','0','-2','NaN']:
            with self.assertRaises(ValueError):m.qty(value)
        self.assertEqual(m.qty('2,0'),2)


    def test_price_current_technical_marker_skipped_without_partial_or_error(self):
        marker=['СТРОКА ФОРМУЛ НЕ УДАЛЯТЬ']+['']*(len(self.header)-1)
        buf=io.StringIO()
        csv.writer(buf).writerows([self.header,marker,self.row])
        raw=buf.getvalue().encode()
        with patch.object(m,'fetch',return_value=(200,raw,None,None)):
            result=m.sync(self.c,self.cfg,'price_journal_current')
            again=m.sync(self.c,self.cfg,'price_journal_current')
        self.assertEqual((result['status'],result['source_rows'],result['inserted'],result['rejected'],result['skipped_technical']),
                         ('success',2,1,0,1))
        self.assertEqual((again['status'],again['unchanged'],again['skipped_technical']),
                         ('unchanged_snapshot',1,1))
        self.assertEqual(self.c.execute("select count(*) from price_event").fetchone()[0],1)
        self.assertEqual(self.c.execute("select count(*) from sync_error").fetchone()[0],0)
        run=self.c.execute("select skipped_technical,rejected from sync_run where source='price_journal_current' order by run_id desc limit 1").fetchone()
        self.assertEqual(tuple(run),(1,0))

    def test_real_business_error_remains_partial_even_with_technical_marker(self):
        marker=['СТРОКА ФОРМУЛ НЕ УДАЛЯТЬ']+['']*(len(self.header)-1)
        bad=self.row.copy();bad[2]='ABC'
        buf=io.StringIO();csv.writer(buf).writerows([self.header,marker,bad,self.row])
        with patch.object(m,'fetch',return_value=(200,buf.getvalue().encode(),None,None)):
            result=m.sync(self.c,self.cfg,'price_journal_current')
        self.assertEqual((result['status'],result['skipped_technical'],result['rejected'],result['inserted']),
                         ('partial',1,1,1))
        self.assertEqual(self.c.execute("select count(*) from sync_error").fetchone()[0],1)
        self.assertEqual(self.c.execute("select source_row from sync_error").fetchone()[0],3)

    def test_sentinel_in_business_row_must_not_hide_data_error(self):
        bad=self.row.copy()
        bad[0]='СТРОКА ФОРМУЛ НЕ УДАЛЯТЬ'
        n=self.ingest([self.header,bad])
        self.assertEqual((n['skipped_technical'],n['rejected']), (0,1))
        self.assertEqual(self.c.execute("select count(*) from sync_error").fetchone()[0],1)

    def test_invalid_rows_not_treated_as_technical_by_incomplete_fields(self):
        empty=self.row.copy();empty[2]=''
        n=self.ingest([self.header,empty])
        self.assertEqual((n['skipped_technical'],n['rejected']), (0,1))

    def test_304_retains_technical_counter_without_new_errors(self):
        marker=['СТРОКА ФОРМУЛ НЕ УДАЛЯТЬ']+['']*(len(self.header)-1)
        buf=io.StringIO();csv.writer(buf).writerows([self.header,marker,self.row])
        raw=buf.getvalue().encode()
        with patch.object(m,'fetch',side_effect=[(200,raw,None,None),(304,None,None,None)]):
            first=m.sync(self.c,self.cfg,'price_journal_current')
            second=m.sync(self.c,self.cfg,'price_journal_current')
        self.assertEqual(first['status'],'success')
        self.assertEqual((second['status'],second['skipped_technical'],second['source_rows']),('not_modified',1,2))
        self.assertEqual(self.c.execute("select count(*) from sync_error").fetchone()[0],0)

    def test_additive_migration_creates_skipped_technical_counter(self):
        cols=[x[1] for x in self.c.execute('pragma table_info(sync_run)')]
        self.assertIn('skipped_technical',cols)
        self.assertEqual(self.c.execute('select skipped_technical from sync_run order by run_id desc limit 1').fetchone(),None)

    def test_cleared_archive_with_orphan_technical_columns_is_success(self):
        import io
        rows=[['']*26 for _ in range(3)]
        rows[1][22]='распродажа'
        rows[2][24]='Артикул мп'
        rows[2][25]='1049'
        buf=io.StringIO()
        csv.writer(buf).writerows(rows)
        with patch.object(m,'fetch',return_value=(200,buf.getvalue().encode(),None,None)):
            first=m.sync(self.c,self.cfg,'price_journal_archive')
            second=m.sync(self.c,self.cfg,'price_journal_archive')
        self.assertEqual((first['status'],first['source_rows'],first['rejected']),('success',0,0))
        self.assertEqual(second['status'],'unchanged_snapshot')
        self.assertEqual(self.c.execute("select count(*) from price_event where source_segment='archive'").fetchone()[0],0)
        self.assertEqual(self.c.execute("select count(*) from sync_error").fetchone()[0],0)

    def test_archived_rows_can_be_added_after_intentional_empty_snapshot(self):
        with patch.object(m,'fetch',return_value=(200,b'',None,None)):
            empty=m.sync(self.c,self.cfg,'price_journal_archive')
        self.assertEqual(empty['status'],'success')
        buf=io.StringIO()
        csv.writer(buf).writerows([self.header,self.row])
        with patch.object(m,'fetch',return_value=(200,buf.getvalue().encode(),None,None)):
            inserted=m.sync(self.c,self.cfg,'price_journal_archive')
            unchanged=m.sync(self.c,self.cfg,'price_journal_archive')
        self.assertEqual((inserted['inserted'],inserted['status']),(1,'success'))
        self.assertEqual(unchanged['status'],'unchanged_snapshot')
        self.assertEqual(self.c.execute("select count(*) from price_event where source_segment='archive'").fetchone()[0],1)

    def test_empty_archive_snapshot_never_deletes_existing_price_history(self):
        self.ingest([self.header,self.row],source='price_journal_archive')
        self.ingest([self.header,self.row],source='price_journal_current')
        with patch.object(m,'fetch',return_value=(200,b'',None,None)):
            result=m.sync(self.c,self.cfg,'price_journal_archive')
        self.assertEqual((result['status'],result['source_rows']),('success',0))
        segments=self.c.execute("select source_segment,count(*) from price_event group by source_segment order by source_segment").fetchall()
        self.assertEqual([tuple(x) for x in segments],[('archive',1),('current',1)])

    def test_cleared_current_journal_is_still_invalid(self):
        with patch.object(m,'fetch',return_value=(200,b'',None,None)):
            with self.assertRaises(ValueError):
                m.sync(self.c,self.cfg,'price_journal_current')

if __name__=='__main__':unittest.main()
