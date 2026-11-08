import json,tempfile,unittest
from pathlib import Path
from apps.msp_marketplace_reports import standalone_wb as s,wb_discovery_resume as d
class Evidence(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.plan={'schema':1,'kind':'wb-discovery','cabinet':'wb_laser_master','year':2026,'date_from':'2025-12-29','date_to':'2026-01-04','limit':1000,'max_send_entries':2}
  self.auth={'schema':1,'plan_sha256':s._digest(self.plan),'code_sha256':s.code_digest(),'archive_root':str(self.root),'expires_epoch':9999999999,'owner_api_pilot_authorized':True,'shared_quota_verified':True,'conflicting_clients_excluded':True,'evidence_reference':'OFFLINE_NEW_YEAR'}
 def go(self,send,fault=None):return d.step(self.root,self.plan,self.auth,lambda:send,now=1000,fault=fault)
 def no(self,req):self.fail('no additional HTTP')
 def row(self,rid=9,start='2025-12-29',end='2026-01-04'):return {'reportId':rid,'reportType':1,'dateFrom':start,'dateTo':end}
 def test_valid_prior_year_item_is_retained_but_not_added_to_2026_inventory(self):
  out=self.go(lambda req:(200,[self.row(8,'2025-12-22','2025-12-28'),self.row()]))
  self.assertEqual(out['status'],'PAGE_STAGED_RECONCILE')
  out=self.go(self.no);self.assertEqual(out['status'],'COMPLETE');self.assertEqual(out['offset'],2);self.assertEqual(out['items'],[self.row()])
  metadata=next((self.root/'.wb-executor').glob('*-metadata-*.json'));self.assertEqual(len(json.loads(metadata.read_text())['items']),2)
 def test_bad_metadata_is_retained_with_fixed_reason_without_financial_values(self):
  out=self.go(lambda req:(200,[{'reportId':False,'reportType':1,'dateFrom':{'amount':'PRIVATE'},'dateTo':'SECRET_TOKEN','bankAmount':'PRIVATE'}]))
  self.assertEqual(out['status'],'HOLD_ERROR');self.assertIn('failure',out)
  metadata=next((self.root/'.wb-executor').glob('*-metadata-*.json'));self.assertNotIn('PRIVATE',metadata.read_text());self.assertNotIn('SECRET_TOKEN',metadata.read_text())
  self.assertEqual(self.go(self.no)['entries'],1)
 def test_interruption_after_metadata_write_replays_without_new_entry(self):
  def crash(phase):
   if phase=='after_metadata_before_validation':raise OSError('interrupted')
  with self.assertRaises(OSError):self.go(lambda req:(200,[self.row()]),crash)
  self.assertEqual(self.go(self.no)['status'],'PAGE_STAGED_RECONCILE')
  done=self.go(self.no);self.assertEqual(done['status'],'COMPLETE');self.assertEqual(done['entries'],1)
 def test_unknown_dispatch_without_metadata_does_not_get_retried(self):
  def crash(phase):
   if phase=='after_budget_before_factory':raise OSError('interrupted')
  with self.assertRaises(OSError):self.go(self.no,crash)
  out=self.go(self.no);self.assertEqual(out['last_error'],'UNKNOWN_DISCOVERY_DISPATCH');self.assertEqual(out['entries'],1)
 def test_duplicate_and_reversed_dates_remain_holds(self):
  for rows in ([self.row(),self.row()], [self.row(end='2025-12-01')]):
   with tempfile.TemporaryDirectory() as tmp:
    old=self.root;self.root=Path(tmp);self.auth['archive_root']=str(self.root)
    out=self.go(lambda req:(200,rows));self.assertEqual(out['status'],'HOLD_ERROR');self.assertIn('row_index',out['failure']);self.root=old
 def test_saved_metadata_tamper_is_not_resealed_or_refetched(self):
  def crash(phase):
   if phase=='after_metadata_before_validation':raise OSError('interrupted')
  with self.assertRaises(OSError):self.go(lambda req:(200,[self.row()]),crash)
  path=next((self.root/'.wb-executor').glob('*-metadata-*.json'));value=json.loads(path.read_text());value['items'][0]['reportId']=123;path.write_text(json.dumps(value))
  with self.assertRaises(Exception):self.go(self.no)
 def test_exact_known_lost_response_retries_once_in_same_two_entry_budget(self):
  from unittest.mock import patch
  state={'entries':1,'items':[],'last_error':'INVALID_DISCOVERY_METADATA','not_before_epoch':0,'offset':0,'plan_sha256':s._digest(self.plan),'schema':1,'status':'HOLD_ERROR'}
  folder=self.root/'.wb-executor';folder.mkdir();path=folder/('discovery-'+s._digest(self.plan)+'.json');path.write_bytes(s._encode({**state,'state_sha256':s._digest(state)}))
  with patch.object(d,'_verify_known_recovery') as proof:
   out=self.go(lambda req:(200,[self.row()]));self.assertEqual(out['entries'],2);self.assertEqual(proof.call_count,1)
   done=self.go(self.no);self.assertEqual(done['status'],'COMPLETE');self.assertEqual(done['entries'],2)
   self.assertEqual(self.go(self.no)['entries'],2)
 def test_other_holds_are_not_reopened(self):
  state={'entries':1,'items':[],'last_error':'INVALID_DISCOVERY_METADATA','not_before_epoch':0,'offset':1,'plan_sha256':s._digest(self.plan),'schema':1,'status':'HOLD_ERROR'}
  folder=self.root/'.wb-executor';folder.mkdir();(folder/('discovery-'+s._digest(self.plan)+'.json')).write_bytes(s._encode({**state,'state_sha256':s._digest(state)}))
  self.assertEqual(self.go(self.no)['status'],'HOLD_ERROR')
