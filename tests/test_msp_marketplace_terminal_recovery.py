import importlib.util,json,tempfile,unittest,copy
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'scripts/finance_control/history_driver.py';spec=importlib.util.spec_from_file_location('terminal_driver_test',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class TerminalRecoveryTests(unittest.TestCase):
 def setUp(self):
  self.result={'request_nonce':'a'*32,'status':'PARTIAL','api_enabled_after_run':False,'schedule_enabled':False,'jobs':[{'status':'STOP_OR_UNCERTAIN'}]}
  plan={'schema':1,'cabinet':'wb_laser_master','year':2026,'report_id':42,'report_type':1,'max_send_entries':3}
  self.diag={'request_nonce':'a'*32,'status':'READ_ONLY_PASS','checked_epoch':1000,'selected_plan':plan,'interrupted_recovery':{'plan':plan,'receipt':{'status':'STAGED_PUBLICATION_PENDING'},'evidence':{'stage_status':'STAGED_COMPLETE','pages':3,'budget_entries':4,'http_attempts':4,'unknown_outcomes':0,'pending_response_present':False,'http_statuses':[200,200,200,204]}}}
 def test_safe_local_recovery_keeps_original_receipt_and_counter(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
   p=Path(t)/'state.json';value={'phase':'HOLD','reason':'non_pass_no_retry','wakes':60,'last':self.result};p.write_text(json.dumps(value))
   self.assertTrue(m.recover_terminal_stop(p,lambda:self.diag,lambda n:self.result,lambda:None,clock=lambda:1001))
   saved=json.loads(p.read_text());self.assertEqual(saved['last'],self.result);self.assertEqual(saved['wakes'],60);self.assertEqual(saved['phase'],'COOLDOWN')
 def test_unknown_incomplete_corrupt_stale_or_foreign_never_retries(self):
  for key,val in [('unknown_outcomes',1),('http_statuses',[200,200,200,500]),('stage_status','RUNNING'),('pending_response_present',True)]:
   d=copy.deepcopy(self.diag);d['interrupted_recovery']['evidence'][key]=val
   with self.subTest(key=key):self.assertIsNone(m.safe_terminal_stop(self.result,d,now=1001))
  self.assertIsNone(m.safe_terminal_stop(self.result,self.diag,now=2801))
 def test_two_local_attempts_is_a_hard_bound(self):
  key=m.safe_terminal_stop(self.result,self.diag,now=1001)
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
   p=Path(t)/'state.json';p.write_text(json.dumps({'phase':'HOLD','reason':'non_pass_no_retry','wakes':60,'last':self.result,'local_publication_recoveries':{key:2}}))
   self.assertFalse(m.recover_terminal_stop(p,lambda:self.diag,lambda n:self.result,lambda:None,clock=lambda:1001))
