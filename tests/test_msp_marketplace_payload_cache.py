import json,unittest
from unittest.mock import patch
from apps.msp_marketplace_reports import generation_store as g
from apps.msp_marketplace_reports.archive import _encode,_metadata

def files():
 row={'reportId':'11','rrdId':'1','reportType':'1','amount':'10'}
 raw=_encode(list(row),{('11','1'):row})
 return {'data.csv':raw,'data.csv.meta.json':json.dumps(_metadata(raw,1,'wb_weekly_finance_main','wb_laser_master','2026')).encode()}

class PayloadCacheTests(unittest.TestCase):
 def test_identical_bytes_parsed_once_per_context_and_result_not_mutable(self):
  f=files();args=('wb_weekly_finance_main','wb_laser_master','2026',f)
  with patch.object(g,'_rows',wraps=g._rows) as rows:
   with g.verified_payload_cache():
    result=g._payload_pairs(*args);result['data.csv']=999
    self.assertEqual(g._payload_pairs(*args)['data.csv'],1)
    self.assertEqual(rows.call_count,1)
   g._payload_pairs(*args);self.assertEqual(rows.call_count,2)
 def test_changed_bytes_revalidated_and_rejected(self):
  f=files();args=('wb_weekly_finance_main','wb_laser_master','2026')
  with g.verified_payload_cache():
   g._payload_pairs(*args,f)
   f['data.csv']=f['data.csv'].replace(b';10',b';99')
   with self.assertRaises(g.GenerationError):g._payload_pairs(*args,f)
 def test_changed_identity_rejected_even_when_bytes_match(self):
  f=files()
  with g.verified_payload_cache():
   g._payload_pairs('wb_weekly_finance_main','wb_laser_master','2026',f)
   with self.assertRaises(g.GenerationError):g._payload_pairs('wb_weekly_finance_main','wb_novokshenov','2026',f)
 def test_scope_exits_after_exception(self):
  try:
   with g.verified_payload_cache():raise RuntimeError('fixture')
  except RuntimeError:pass
  self.assertIsNone(g._PAYLOAD_CACHE.get())
