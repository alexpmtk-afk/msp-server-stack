import importlib.util,copy,unittest
from pathlib import Path
p=Path(__file__).resolve().parents[1]/'scripts/finance_control/resume_memory_recovery.py';s=importlib.util.spec_from_file_location('memory_resume',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class MemoryResumeTests(unittest.TestCase):
 def setUp(self):
  self.prior={'request_nonce':m.PREVIOUS_NONCE}
  plan={'schema':1,'cabinet':'wb_laser_master','year':2026,'report_id':743994450,'report_type':1,'max_send_entries':3}
  self.d={'request_nonce':m.EXPECTED_NONCE,'checked_epoch':1000,'status':'READ_ONLY_PASS','selected_plan':plan,'interrupted_recovery':{'plan':plan,'receipt':{'status':'STAGED_PUBLICATION_PENDING'},'evidence':{'stage_status':'STAGED_COMPLETE','pages':3,'budget_entries':4,'http_attempts':4,'unknown_outcomes':0,'pending_response_present':False,'http_statuses':[200,200,200,204]}}}
 def test_exact_terminal_local_replay_is_accepted(self):m.validate_reconciled_timeout(self.prior,self.d,1001)
 def test_unknown_or_nonterminal_never_admitted(self):
  for key,value in [('unknown_outcomes',1),('http_attempts',5),('stage_status','RUNNING'),('pending_response_present',True),('http_statuses',[200,200,200,500])]:
   d=copy.deepcopy(self.d);d['interrupted_recovery']['evidence'][key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):m.validate_reconciled_timeout(self.prior,d,1001)
 def test_corrupt_receipt_not_reclassified_as_publication_pending(self):
  self.d['interrupted_recovery']['receipt']={'status':'HOLD_INVALID_LOCAL_EVIDENCE'}
  with self.assertRaises(ValueError):m.validate_reconciled_timeout(self.prior,self.d,1001)
