import unittest,json
from unittest.mock import patch
from apps.msp_marketplace_reports import archive as a,generation_store as g
class StreamingTests(unittest.TestCase):
 def fixture(self):
  rows={('1','1'):{'reportId':'1','rrdId':'1','reportType':'1','value':'quote; newline\n\"x\"'},('2','2'):{'reportId':'2','rrdId':'2','reportType':'1','value':'other'}}
  return a._encode(list(next(iter(rows.values()))),rows)
 def test_scanner_equivalent_to_full_parser(self):
  data=self.fixture();fields,rows=a._rows(data,('reportId','rrdId'));sf,records=a._scan_rows(data,('reportId','rrdId'));self.assertEqual(sf,fields);self.assertEqual({k:dict(zip(sf,v)) for k,v in records},rows)
 def test_malformed_and_duplicate_rows_are_rejected(self):
  for raw in [b'reportId;rrdId\n1;1\n1;1\n',b'reportId;rrdId\n1\n',b'reportId;rrdId\n1;\n',b'reportId;reportId;rrdId\n1;1;2\n']:
   with self.subTest(raw=raw),self.assertRaises(ValueError):
    fields,rows=a._scan_rows(raw,('reportId','rrdId'));list(rows)
 def test_generation_check_does_not_materialize_annual_row_dictionaries(self):
  raw=self.fixture();files={'data.csv':raw,'data.csv.meta.json':json.dumps(a._metadata(raw,2,'wb_weekly_finance_main','wb_laser_master','2026')).encode()}
  with patch.object(g,'_rows',side_effect=AssertionError('annual materialization forbidden')):
   self.assertEqual(g._payload_pairs('wb_weekly_finance_main','wb_laser_master','2026',files),{'data.csv':2})

class PartitionTests(unittest.TestCase):
 def test_partition_preserves_quoted_cells_and_selected_rows(self):
  import importlib.util,zlib
  from pathlib import Path
  p=Path(__file__).resolve().parents[1]/'scripts/finance_control/overlays/finance_receipts.py'
  # Overlay relative imports use the real application package, not a fake parser.
  spec=importlib.util.spec_from_file_location('apps.msp_marketplace_reports.partition_receipts_test',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  raw=StreamingTests().fixture();header,index=m._compressed_report_index(raw,('reportId','rrdId'))
  self.assertEqual(set(index),{'1','2'})
  full=a._rows(raw,('reportId','rrdId'))[1]
  for rid,packed in index.items():
   self.assertEqual(a._rows(header+zlib.decompress(packed),('reportId','rrdId'))[1],{k:v for k,v in full.items() if k[0]==rid})
   self.assertEqual(m._selected_rows(raw,('reportId','rrdId'),rid),{k:v for k,v in full.items() if k[0]==rid})

class MergeTests(unittest.TestCase):
 def test_annual_merge_no_materialization_and_conflict_refused(self):
  from apps.msp_marketplace_reports import versioned_archive as v
  raw=StreamingTests().fixture();fields,rows=a._rows(raw,('reportId','rrdId'))
  incoming={('3','3'):{'reportId':'3','rrdId':'3','reportType':'1','value':'new'}}
  with patch.object(v,'_rows',side_effect=AssertionError('annual materialization forbidden')):
   merged,count,added=v._merge_wb_csv(raw,fields,incoming,('reportId','rrdId'))
  self.assertEqual((count,added),(3,1));self.assertEqual(a._rows(merged,('reportId','rrdId'))[1],dict(rows,**{})|incoming)
  same,count,added=v._merge_wb_csv(merged,fields,incoming,('reportId','rrdId'));self.assertEqual(same,merged);self.assertEqual(added,0)
  bad={('1','1'):{**rows[('1','1')],'value':'changed'}}
  with self.assertRaises(ValueError):v._merge_wb_csv(raw,fields,bad,('reportId','rrdId'))
