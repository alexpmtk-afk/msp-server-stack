"""New campaign scope only; no provider or Redis calls."""
import importlib.util,json
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('campaign_scope',ROOT/'scripts/finance_campaign/scope.py')
scope=importlib.util.module_from_spec(spec);spec.loader.exec_module(scope)
class Scope(unittest.TestCase):
 def setUp(self):self.receipt=json.loads((ROOT/'docs/marketplace-reports/next-20261105/WB_EXECUTION_RECEIPT.json').read_text())
 def test_real_discovery_excludes_completed_and_selects_earliest(self):
  p=scope.next_plan(self.receipt);self.assertEqual(len(p['remaining_discovered']),8)
  self.assertEqual(p['next']['report_id'],865431404);self.assertEqual(p['next']['report_type'],1)
  self.assertNotIn(883801632,[r['report_id'] for r in p['remaining_discovered']]);self.assertNotIn(883801636,[r['report_id'] for r in p['remaining_discovered']])
 def test_incomplete_receipt_cannot_mark_report_complete(self):
  self.receipt['outcome']['receipt']['terminal_http_status']=200
  with self.assertRaises(ValueError):scope.next_plan(self.receipt)
 def test_changed_discovery_id_type_is_rejected(self):
  self.receipt['outcome']['discovery']['items'][0]['reportType']=True
  with self.assertRaises(ValueError):scope.next_plan(self.receipt)
 def test_rootless_request_can_only_select_root_approved_campaign(self):
  p={'campaign_ids':['history2026'],'max_wake_entries':3,'schedule_enabled':False}
  self.assertEqual(scope.admit_wake({'campaign_id':'history2026','max_entries':2},p),{'campaign_id':'history2026','max_entries':2})
  for req in [{'campaign_id':'unknown','max_entries':1},{'campaign_id':'history2026','max_entries':4},{'campaign_id':'history2026','max_entries':True},{'campaign_id':'history2026','max_entries':1,'command':'curl'}]:
   with self.assertRaises(ValueError):scope.admit_wake(req,p)
 def test_per_cabinet_year_plan_does_not_fabricate_ids(self):
  p=scope.next_plan(self.receipt)
  self.assertEqual(p['other_cabinets'],{'wb_novokshenov':'DISCOVERY_REQUIRED','wb_dmitrieva':'DISCOVERY_REQUIRED'})
 def test_ozon_version_notice_does_not_enable_pilot(self):
  with self.assertRaises(ValueError):scope.admit_ozon_method({'method':'/v1/finance/realization/posting','version_confirmed':True},'/v1/finance/realization/posting')
