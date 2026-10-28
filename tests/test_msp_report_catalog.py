import importlib.util
from pathlib import Path
import sqlite3
import unittest

P = Path(__file__).parents[1] / 'apps/msp_report_catalog/catalog.py'
s = importlib.util.spec_from_file_location('report_catalog_test', P)
m = importlib.util.module_from_spec(s)
s.loader.exec_module(m)

class CatalogTests(unittest.TestCase):
    def fixture(self):
        report=dict(report_id='test',spreadsheet_id='fixture_document_1234567890',sheets=[dict(sheet_id=7,title="Заказы O'Reilly",purpose='daily orders',fulfillment='ALL',grain='day',metrics='units')],rules=['Use approved source only'])
        meta=dict(properties=dict(title='Orders',timeZone='Europe/Moscow'),sheets=[dict(properties=dict(sheetId=7,title="Заказы O'Reilly",gridProperties=dict(rowCount=100,columnCount=5)))])
        return report,meta

    def test_sql_guide_reinstall_is_idempotent_not_business_data_import(self):
        report,meta=self.fixture()
        with sqlite3.connect(':memory:') as c:
            for _ in range(2):m.write_catalog(c,report,meta,[['SKU','Заказы (шт)','Заказы (сумма)']],'Approved instructions','timestamp')
            self.assertEqual(c.execute('select count(*) from report_column').fetchone()[0],3)
            self.assertEqual(c.execute('select data_materialized from report_source').fetchone()[0],0)
            self.assertEqual(c.execute('select markdown from report_guide').fetchone()[0],'Approved instructions')
            self.assertEqual(c.execute('pragma integrity_check').fetchone()[0],'ok')

    def test_bounded_ranges_and_unknown_tabs_fail_before_network(self):
        for value in ('A:A','A1:ZZ99999','B9:A1','A0:B2','Other!A1:B2'):
            with self.assertRaises(ValueError):m.validate_range(value)
        report,meta=self.fixture()
        with self.assertRaises(ValueError):m.read_range(None,report,'unknown','A1:B2')
        self.assertEqual(m.validate_range('A1:E1000'),'A1:E1000')

    def test_exact_gid_and_readonly_quoted_sheet_request(self):
        report,meta=self.fixture()
        class Reader:
            def metadata(self,r):return meta
            def get(self,fid,suffix,params):self.request=(fid,suffix,params);return dict(values=[['verified']])
        reader=Reader();result=m.read_range(reader,report,"Заказы O'Reilly",'A1:B2')
        self.assertEqual(result['data']['values'],[['verified']])
        self.assertIn('FORMATTED_VALUE',reader.request[2].values())
        meta['sheets'][0]['properties']['sheetId']=8
        with self.assertRaises(ValueError):m.read_range(reader,report,"Заказы O'Reilly",'A1:B2')

if __name__=='__main__':unittest.main()
