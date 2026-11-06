import importlib.util,json,tempfile,unittest
from pathlib import Path
from datetime import date
ROOT=Path(__file__).resolve().parents[1]
class FailureEvidence(unittest.TestCase):
 def diagnostic(self):
  spec=importlib.util.spec_from_file_location('diag_evidence',ROOT/'scripts/finance_control/diagnostics.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
 def test_exact_hold_state_and_saved_page_summary_without_financial_rows(self):
  from apps.msp_marketplace_reports import standalone_wb as s
  from apps.msp_marketplace_reports.wb_page_resume import step_wb_detail
  plan={'schema':1,'cabinet':'wb_laser_master','year':2026,'report_id':601780521,'report_type':1,'max_send_entries':3}
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   step_wb_detail(root,plan['cabinet'],2026,plan['report_id'],1,lambda req:(200,[{'reportId':601780521,'reportType':1,'rrdId':10,'private_amount':'SECRET_AMOUNT'}]))
   v={'schema':1,'plan_sha256':s._digest(plan),'send_entries':2,'status':'HOLD_ERROR','error_type':'GenerationError'}
   folder=root/'.wb-executor';folder.mkdir();(folder/(s._digest(plan)+'.json')).write_bytes(s._encode({**v,'state_sha256':s._digest(v)}))
   (folder/('control-'+32*'a'+'-events.jsonl')).write_text(''.join(json.dumps({'event':event,'plan':plan,**extra})+'\n' for event,extra in [('HTTP_DISPATCH_ATTEMPT',{}),('HTTP_RESPONSE',{'status':200}),('HTTP_DISPATCH_ATTEMPT',{}),('HTTP_RESPONSE',{'status':200})]))
   before={str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}
   import apps.msp_marketplace_reports as package
   from unittest.mock import patch
   spec=importlib.util.spec_from_file_location('apps.msp_marketplace_reports.standalone_wb',ROOT/'scripts/finance_control/overlays/standalone_wb.py');overlay=importlib.util.module_from_spec(spec);spec.loader.exec_module(overlay)
   with patch.object(package,'standalone_wb',overlay):out=self.diagnostic().report_evidence(root,plan)
   self.assertEqual(out['executor_status'],'HOLD_ERROR');self.assertEqual(out['budget_entries'],2)
   self.assertEqual(out['pages'],1);self.assertEqual(out['rows_staged'],1);self.assertEqual(out['cursor'],10)
   self.assertEqual(out['http_statuses'],[200,200]);self.assertEqual(out['http_attempts'],2)
   self.assertNotIn('SECRET_AMOUNT',json.dumps(out));self.assertEqual(before,{str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()})
 def test_year_boundary_added_without_changing_previous_monthly_plan_identity(self):
  from apps.msp_marketplace_reports.finance_refresh_plan import discovery_windows
  from apps.msp_marketplace_reports.wb_discovery_resume import validate
  windows=discovery_windows(2026,date(2026,11,6))
  boundary=[x for x in windows if x['dateFrom']=='2025-12-29']
  self.assertEqual(len(boundary),1);self.assertEqual(boundary[0]['dateTo'],'2026-01-04')
  self.assertTrue(any(x['dateFrom']=='2026-01-01' and x['dateTo']=='2026-01-31' for x in windows))
  validate({'schema':1,'kind':'wb-discovery','cabinet':'wb_laser_master','year':2026,'date_from':boundary[0]['dateFrom'],'date_to':boundary[0]['dateTo'],'limit':1000,'max_send_entries':2})


 def test_full_official_week_keeps_december_rows_in_2026_archive(self):
  from apps.msp_marketplace_reports.wb_page_resume import step_wb_detail,read_completed_wb_pages
  from apps.msp_marketplace_reports.backfill_plan import _inventory
  cabinet='wb_laser_master'
  inventory={'cabinet':cabinet,'year':2026,'status':'DISCOVERED_NOT_DOWNLOADED','items':[{'reportId':77,'reportType':1,'dateFrom':'2025-12-29','dateTo':'2026-01-04'}]}
  self.assertEqual(_inventory(inventory,cabinet,2026)[0][1][1].isoformat(),'2025-12-29')
  with tempfile.TemporaryDirectory() as tmp:
   rows=[{'reportId':77,'reportType':1,'rrdId':1,'saleDt':'2025-12-30'}, {'reportId':77,'reportType':1,'rrdId':2,'saleDt':'2026-01-02'}]
   step_wb_detail(Path(tmp),cabinet,2026,77,1,lambda req:(200,rows))
   step_wb_detail(Path(tmp),cabinet,2026,77,1,lambda req:(204,None))
   self.assertEqual([r for page in read_completed_wb_pages(Path(tmp),cabinet,2026,77,1) for r in page],rows)


class ResponseRetention(unittest.TestCase):
 def test_invalid_received_page_is_preserved_and_replay_does_not_issue_http(self):
  from apps.msp_marketplace_reports.wb_page_resume import step_wb_detail,_dir
  from apps.msp_marketplace_reports.generation_store import GenerationError
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);calls=[]
   def send(req):
    calls.append(req.body['rrdId'])
    return 200,[{'reportId':601780521,'reportType':1,'rrdId':9}, {'reportId':601780521,'reportType':1,'rrdId':9}]
   with self.assertRaises(GenerationError):step_wb_detail(root,'wb_laser_master',2026,601780521,1,send)
   folder=_dir(root,'wb_laser_master',2026,601780521,1)
   saved=folder/'response-0.json'
   self.assertTrue(saved.exists(),'successful HTTP body was discarded on processing error')
   self.assertEqual(json.loads(saved.read_text())['rows'][1]['rrdId'],9)
   before={str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}
   with self.assertRaises(GenerationError):step_wb_detail(root,'wb_laser_master',2026,601780521,1,send)
   self.assertEqual(calls,[0]);self.assertEqual(before,{str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()})
 def test_valid_received_page_after_local_validation_crash_replays_without_http(self):
  from apps.msp_marketplace_reports import wb_page_resume as p
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);calls=[]
   def send(req):calls.append(1);return 200,[{'reportId':601780521,'reportType':1,'rrdId':9}]
   with patch.object(p,'_validate_page',side_effect=OSError('local failure after response persistence')):
    with self.assertRaises(OSError):p.step_wb_detail(root,'wb_laser_master',2026,601780521,1,send)
   out=p.step_wb_detail(root,'wb_laser_master',2026,601780521,1,send)
   self.assertEqual(out['cursor'],9);self.assertEqual(out['provider_calls'],0);self.assertEqual(calls,[1])
 def test_tampered_received_page_cannot_be_resealed_by_replay(self):
  from apps.msp_marketplace_reports import wb_page_resume as p
  from unittest.mock import patch
  from apps.msp_marketplace_reports.generation_store import GenerationError
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   with patch.object(p,'_validate_page',side_effect=OSError('local crash')):
    with self.assertRaises(OSError):p.step_wb_detail(root,'wb_laser_master',2026,601780521,1,lambda req:(200,[{'reportId':601780521,'reportType':1,'rrdId':9}]))
   path=p._dir(root,'wb_laser_master',2026,601780521,1)/'response-0.json';data=json.loads(path.read_text());data['rows'][0]['rrdId']=99;path.write_text(json.dumps(data))
   with self.assertRaisesRegex(GenerationError,'checksum mismatch'):p.step_wb_detail(root,'wb_laser_master',2026,601780521,1,lambda req:self.fail('no HTTP'))

class StructuredErrors(unittest.TestCase):
 def test_executor_retains_location_without_secret_exception_text(self):
  from unittest.mock import patch
  spec=importlib.util.spec_from_file_location('apps.msp_marketplace_reports.repair_overlay',ROOT/'scripts/finance_control/overlays/standalone_wb.py');s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
  from apps.msp_marketplace_reports.generation_store import GenerationError
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);plan={'schema':1,'cabinet':'wb_laser_master','year':2026,'report_id':601780521,'report_type':1,'max_send_entries':3}
   auth={'schema':1,'plan_sha256':s._digest(plan),'code_sha256':s.code_digest(),'archive_root':str(root),'expires_epoch':9999999999,'owner_api_pilot_authorized':True,'shared_quota_verified':True,'conflicting_clients_excluded':True,'evidence_reference':'OFFLINE_ERROR_TEST'}
   def broken(*args,**kwargs):raise GenerationError('SECRET_EXCEPTION_VALUE')
   with patch.object(s,'run_one_step',broken):out=s.run_step(root,plan,auth,lambda:self.fail('no sender'),now=1000.)
   self.assertEqual(out['status'],'HOLD_ERROR');self.assertTrue(out['failure']['frames']);self.assertNotIn('SECRET_EXCEPTION_VALUE',json.dumps(out))

class KnownHoldRecovery(unittest.TestCase):
 def test_exact_old_hold_can_retry_once_without_resetting_counter_or_saved_page(self):
  from unittest.mock import patch
  from apps.msp_marketplace_reports import wb_page_resume as pages
  spec=importlib.util.spec_from_file_location('apps.msp_marketplace_reports.recovery_overlay',ROOT/'scripts/finance_control/overlays/standalone_wb.py');s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
  plan={'schema':1,'cabinet':'wb_laser_master','year':2026,'report_id':601780521,'report_type':1,'max_send_entries':3}
  old={'admission_extension':{'from':3,'policy_sha256':'0582e3fdbeec5d87dda75709928a44e7fc3f3a3682b0b442bf45561db0e9e978','prior_state_sha256':'85c7084c6eb6eb2c0f62a36897b50b98718bd48fac1f4966d617b843e390aa5c','to':1000},'approved_total_entries':1000,'error_type':'GenerationError','plan_sha256':s._digest(plan),'schema':1,'send_entries':2,'status':'HOLD_ERROR'}
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);folder=root/'.wb-executor';folder.mkdir();bp=folder/(s._digest(plan)+'.json');bp.write_bytes(s._encode({**old,'state_sha256':s._digest(old)}))
   pages.step_wb_detail(root,plan['cabinet'],2026,601780521,1,lambda req:(200,[{'reportId':601780521,'reportType':1,'rrdId':10}]))
   stage=pages._dir(root,plan['cabinet'],2026,601780521,1);prior=(stage/'page-0.json').read_bytes()
   events=[{'event':e,'plan':plan,**v} for e,v in [('HTTP_DISPATCH_ATTEMPT',{}),('HTTP_RESPONSE',{'status':200}),('HTTP_DISPATCH_ATTEMPT',{}),('HTTP_RESPONSE',{'status':200})]]
   (folder/('control-'+32*'a'+'-events.jsonl')).write_text(''.join(json.dumps(e)+'\n' for e in events))
   auth={'schema':1,'plan_sha256':s._digest(plan),'code_sha256':s.code_digest(),'archive_root':str(root),'expires_epoch':9999999999,'owner_api_pilot_authorized':True,'shared_quota_verified':True,'conflicting_clients_excluded':True,'evidence_reference':'OFFLINE_KNOWN_REPAIR'}
   # Changed all-nonce evidence blocks repair BEFORE any new sender entry.
   extra=folder/('control-'+32*'b'+'-events.jsonl')
   for event in ({'event':'HTTP_OUTCOME_UNKNOWN','plan':plan}, {'event':'HTTP_DISPATCH_ATTEMPT','plan':plan}):
    extra.write_text(json.dumps(event)+'\n')
    before={str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    with patch.object(s,'_load_known_failure_receipt',return_value=old):
     with self.assertRaises(s.PilotBlocked):s.run_step(root,plan,auth,lambda:self.fail('no sender for changed evidence'),now=1000.,admission_ceiling=1000,policy_sha256='b'*64,processing_recovery=True)
    self.assertEqual(before,{str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()})
    extra.unlink()
   calls=[]
   def sender(req):calls.append(req.body['rrdId']);return 200,[{'reportId':601780521,'reportType':1,'rrdId':20}]
   spec=importlib.util.spec_from_file_location('repair_control',ROOT/'scripts/finance_control/control.py');control=importlib.util.module_from_spec(spec);spec.loader.exec_module(control)
   import apps.msp_marketplace_reports as package
   with patch.object(package,'standalone_wb',s):self.assertEqual(control.choose(root,plan['cabinet']),plan)
   # Fixed published root receipt loader is the only external dependency.
   import apps.msp_marketplace_reports as package
   spec=importlib.util.spec_from_file_location('repair_worker',ROOT/'scripts/finance_control/worker.py');worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
   with patch.object(package,'standalone_wb',s),patch.object(s,'_load_known_failure_receipt',return_value=old):
    result=worker.execute(root,plan,auth,lambda:sender,'b'*64,clock=lambda:1000.,sleep=lambda t:None)
   self.assertEqual(result['wake_entries'],1);out=result['executor']
   self.assertEqual(calls,[10]);self.assertEqual(out['send_entries'],3);self.assertIn('processing_recovery',out)
   self.assertEqual((stage/'page-0.json').read_bytes(),prior)
   saved=s.read_control(bp);saved.pop('state_sha256');saved.update(status='HOLD_ERROR',error_type='GenerationError');bp.write_bytes(s._encode({**saved,'state_sha256':s._digest(saved)}))
   with patch.object(s,'_load_known_failure_receipt',return_value=old):
    held=s.run_step(root,plan,auth,lambda:self.fail('no automatic second recovery'),now=2000.,admission_ceiling=1000,policy_sha256='b'*64,processing_recovery=True)
   self.assertEqual(held['status'],'HOLD_ERROR');self.assertEqual(held['send_entries'],3)
