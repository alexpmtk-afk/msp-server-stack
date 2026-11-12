import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from apps.msp_defects_catalog.sync import HEADERS,parse_rows,link_rows,store_snapshot

def row(kind,**kw):
    values=['']*len(HEADERS[kind])
    fields={'article':4,'date':6,'complaint':8,'production':2,'status':11,'comment':13} if kind=='main' else {'article':1,'date':3,'complaint':4,'status':5,'comment':6}
    for k,v in kw.items():values[fields[k]]=v
    return values

class CatalogTests(unittest.TestCase):
    def test_formula_zero_article_placeholder_is_not_a_complaint(self):
        self.assertEqual(parse_rows('main',[HEADERS['main'],row('main',article='0')]),[])

    def test_source_short_year_and_datetime_formats(self):
        r=parse_rows('main',[HEADERS['main'],row('main',article='A',date='08.08.25',complaint='x'),row('main',article='B',date='25.05.2026 17:45',complaint='y')])
        self.assertEqual([x['received_date'] for x in r],['2025-08-08','2026-05-25'])

    def test_physical_rows_raw_identifiers_and_bad_dates_preserved(self):
        r=parse_rows('main',[HEADERS['main'],[],row('main',article='A/01\t',date='bad',complaint='x')])
        self.assertEqual(r[0]['source_row'],3)
        self.assertEqual(r[0]['internal_article_raw'],'A/01\t')
        self.assertIsNone(r[0]['received_date'])
        self.assertIn('INVALID_DATE',r[0]['issues'])

    def test_laser_copy_does_not_add_complaints(self):
        m=parse_rows('main',[HEADERS['main'],row('main',article='A',date='01.11.2026',complaint='x',production='Лазер')])
        l=parse_rows('laser',[HEADERS['laser'],row('laser',article='A',date='01.11.2026',complaint='x',status='Решено',comment='Новая упаковка')])
        links=link_rows(m,l)
        self.assertEqual(len(m),1);self.assertEqual(links[0]['state'],'EXACT_MATCH')
        self.assertEqual(links[0]['laser_row'],2)

    def test_duplicate_key_is_ambiguous_not_first_match(self):
        a=row('main',article='A',date='01.11.2026',complaint='same',production='АНТ')
        m=parse_rows('main',[HEADERS['main'],a,a]);l=parse_rows('laser',[HEADERS['laser'],row('laser',article='A',date='01.11.2026',complaint='same',status='Решено')])
        self.assertEqual([r['state'] for r in link_rows(m,l)],['AMBIGUOUS','AMBIGUOUS'])

    def test_header_mismatch_rejected_before_write(self):
        with self.assertRaises(ValueError):parse_rows('main',[['wrong']])

    def test_idempotency_revision_and_retirement(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/'test.sqlite3'
            m=parse_rows('main',[HEADERS['main'],row('main',article='A',date='01.11.2026',complaint='x')])
            first=store_snapshot(db,{'main':m,'laser':[]},'hash-one')
            again=store_snapshot(db,{'main':m,'laser':[]},'hash-one')
            self.assertEqual(first['inserted'],1);self.assertEqual(again['changed'],0)
            self.assertEqual(again['inserted'],0)
            m[0]['status_raw']='Решено'
            changed=store_snapshot(db,{'main':m,'laser':[]},'hash-two')
            self.assertEqual(changed['changed'],1)
            store_snapshot(db,{'main':[],'laser':[]},'hash-three')
            with sqlite3.connect(db) as c:
                self.assertEqual(c.execute('select count(*) from defects_current').fetchone()[0],0)
                self.assertEqual(c.execute('select count(*) from defects_row_revision').fetchone()[0],3)
