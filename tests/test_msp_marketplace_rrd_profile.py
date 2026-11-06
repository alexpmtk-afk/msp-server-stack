import importlib.util,json,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('rrd_profile',Path(__file__).resolve().parents[1]/'scripts/finance_control/rrd_profile.py');p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
def row(i,amount='PRIVATE_AMOUNT'):return {'rrdId':i,'reportId':601780521,'reportType':1,'amount':amount}
class Profile(unittest.TestCase):
 def test_distinguishes_order_only_duplicate_and_conflicting_previous_rows(self):
  out=p.analyze({'rows':[row(5),row(8),row(7),row(8),row(5,'DIFFERENT')]},[[row(5)]],5)
  self.assertEqual(out['verified_previous_identical_ids'],[5]);self.assertEqual(out['previous_or_unknown_conflicting_ids'],[5])
  self.assertTrue(out['within_response_duplicates'][0]['same_payload']);self.assertFalse(out['within_response_duplicates'][1]['same_payload'])
  self.assertEqual(len(out['adjacent_order_violations']),3);self.assertFalse(out['last_is_maximum'])
  self.assertNotIn('PRIVATE_AMOUNT',json.dumps(out));self.assertNotIn('DIFFERENT',json.dumps(out))
 def test_source_unchanged_and_foreign_row_rejected(self):
  page={'rows':[row(9),row(7),row(10)]};before=json.dumps(page);out=p.analyze(page,[],5)
  self.assertEqual(json.dumps(page),before);self.assertTrue(out['last_is_maximum']);self.assertEqual(out['unique_ids'],3)
  with self.assertRaises(ValueError):p.analyze({'rows':[{**row(9),'reportId':1}]},[],5)

 def test_analyzer_is_bound_to_selected_report_and_supports_other_report_ids(self):
  page={'rows':[{**row(8),'reportId':99}]}
  out=p.analyze(page,[],0,report_id=99,report_type=1)
  self.assertEqual(out['rows_received'],1)
  with self.assertRaises(ValueError):p.analyze(page,[],0,report_id=98,report_type=1)

 def test_root_command_snapshot_is_frozen_to_its_actual_bytes(self):
  import hashlib
  root=Path(__file__).resolve().parents[1]
  artifact=root/'docs/marketplace-reports/autonomous-control-20261105/forensics/rrd-profile.py'
  self.assertTrue(artifact.is_file())
  self.assertEqual(hashlib.sha256(artifact.read_bytes()).hexdigest(),'9e1cdc70f6cae42ba298b356f55acac63e43de3d60eb7477e6be14d65f51d583')

class DiagnosticIntegration(unittest.TestCase):
 def test_pending_sequence_failure_exports_identifiers_without_financial_amounts(self):
  import tempfile,sys
  from unittest.mock import patch
  import apps.msp_marketplace_reports as package
  from apps.msp_marketplace_reports import wb_page_resume as pages, standalone_wb
  root_code=Path(__file__).resolve().parents[1]
  spec=importlib.util.spec_from_file_location('apps.msp_marketplace_reports.profile_overlay',root_code/'scripts/finance_control/overlays/standalone_wb.py');s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
  spec=importlib.util.spec_from_file_location('profile_diagnostic',root_code/'scripts/finance_control/diagnostics.py');d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
  plan={'schema':1,'cabinet':'wb_laser_master','year':2026,'report_id':601780521,'report_type':1,'max_send_entries':3}
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);pages.step_wb_detail(root,plan['cabinet'],2026,601780521,1,lambda req:(200,[row(10)]))
   folder=root/'.wb-executor';folder.mkdir();value={'schema':1,'plan_sha256':s._digest(plan),'send_entries':2,'status':'HOLD_ERROR','error_type':'GenerationError'}
   (folder/(s._digest(plan)+'.json')).write_bytes(s._encode({**value,'state_sha256':s._digest(value)}))
   stage=pages._dir(root,plan['cabinet'],2026,601780521,1)
   pending={'schema':1,'report_id':601780521,'report_type':1,'cursor':10,'next_rrd_id':15,'rows':[row(12),row(11),row(15)]};pending['payload_sha256']=s._digest(pending)
   (stage/'response-10.json').write_bytes(s._encode(pending));before={str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}
   with patch.object(package,'standalone_wb',s),patch.dict(sys.modules,{'rrd_profile':p}):out=d.report_evidence(root,plan)
   self.assertEqual(out['pending_response_validation'],'HOLD');self.assertEqual(out['identifier_profile']['adjacent_order_violations'],[{'index':1,'previous':12,'current':11}])
   self.assertNotIn('PRIVATE_AMOUNT',json.dumps(out));self.assertEqual(before,{str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()})
