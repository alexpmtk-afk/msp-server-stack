import importlib.util,json,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class HistoryDriver(unittest.TestCase):
 def load(self):
  spec=importlib.util.spec_from_file_location('history_driver',ROOT/'scripts/finance_control/history_driver.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
 def test_waits_for_exact_release_without_wake(self):
  d=self.load();calls=[]
  with tempfile.TemporaryDirectory() as f:
   p=Path(f)/'state.json';out=d.advance(p,lambda:'WAITING_UPDATE',lambda:calls.append('wake'),lambda x:None)
   self.assertEqual(out['phase'],'WAITING_UPDATE');self.assertEqual(calls,[])
 def test_partial_stops_and_next_invocation_does_not_retry(self):
  d=self.load();calls=[]
  with tempfile.TemporaryDirectory() as f:
   p=Path(f)/'state.json'
   def wake():calls.append(1);return {'status':'PARTIAL','nonce':'a'*32}
   out=d.advance(p,lambda:'READY',wake,lambda x:None)
   self.assertEqual(out['phase'],'HOLD');self.assertEqual(len(calls),1)
   again=d.advance(p,lambda:'READY',wake,lambda x:None);self.assertEqual(again['phase'],'HOLD');self.assertEqual(len(calls),1)
 def test_crash_unknown_dispatch_is_not_repeated(self):
  d=self.load();calls=[]
  with tempfile.TemporaryDirectory() as f:
   p=Path(f)/'state.json';p.write_text(json.dumps({'schema':1,'phase':'DISPATCHING','wakes':1,'last':None}))
   out=d.advance(p,lambda:'READY',lambda:calls.append('repeat'),lambda x:None)
   self.assertEqual(out['phase'],'HOLD');self.assertEqual(calls,[])
 def test_pass_is_persisted_before_next_portion(self):
  d=self.load();calls=[]
  with tempfile.TemporaryDirectory() as f:
   p=Path(f)/'state.json'
   def wake():calls.append(json.loads(p.read_text())['phase']);return {'status':'PASS','nonce':'a'*32}
   out=d.advance(p,lambda:'READY',wake,lambda x:None)
   self.assertEqual(out['phase'],'COOLDOWN');self.assertEqual(out['wakes'],1);self.assertEqual(calls,['DISPATCHING'])

def budget_pause(count=3,statuses=None):
 return {'status':'PARTIAL','api_enabled_after_run':False,'schedule_enabled':False,'request_nonce':'d'*32,'jobs':[{'status':'PARTIAL','outcome':{'executor':{'status':'PAUSED_BUDGET','send_entries':count,'approved_total_entries':1000,'plan_sha256':'a'*64,'not_before_epoch':1066.},'wake_entries':3,'http_dispatch_attempts':3,'http_outcomes_unknown':0,'http_response_statuses':statuses or [200,200,200],'report_detail_complete':False}}]}

class Continuation(unittest.TestCase):
 load=HistoryDriver.load
 def test_known_page_budget_pause_waits_then_continues_monotonically(self):
  d=self.load();calls=[];now=[1000.]
  with tempfile.TemporaryDirectory() as f:
   p=Path(f)/'state.json'
   def wake():calls.append(1);return budget_pause(3*len(calls))
   r=d.advance(p,lambda:'READY',wake,lambda r:None,clock=lambda:now[0]);self.assertEqual(r['phase'],'COOLDOWN');self.assertGreaterEqual(r['resume_not_before'],1070.)
   now[0]=1069.;d.advance(p,lambda:'READY',wake,lambda r:None,clock=lambda:now[0]);self.assertEqual(len(calls),1)
   now[0]=1070.;r=d.advance(p,lambda:'READY',wake,lambda r:None,clock=lambda:now[0]);self.assertEqual(len(calls),2);self.assertEqual(r['counters']['a'*64],6)
 def test_429_unknown_outcome_or_exhausted_ceiling_is_not_normal_pause(self):
  import copy
  d=self.load()
  for field,value in [('http_response_statuses',[200,429,200]),('http_outcomes_unknown',1),('wake_entries',2)]:
   r=budget_pause();r['jobs'][0]['outcome'][field]=value;self.assertIsNone(d.safe_budget_pause(r))
  self.assertIsNone(d.safe_budget_pause(budget_pause(1000)))
 def test_only_exact_root_receipt_can_recover_old_safe_hold_without_reset(self):
  d=self.load()
  with tempfile.TemporaryDirectory() as f:
   p=Path(f)/'state.json';r=budget_pause();p.write_text(json.dumps({'schema':1,'phase':'HOLD','reason':'non_pass_no_retry','last':r,'wakes':11,'cabinet_index':0}))
   self.assertFalse(d.recover_pause(p,lambda nonce:{**r,'status':'FAIL'},lambda:'READY',clock=lambda:1000.))
   self.assertTrue(d.recover_pause(p,lambda nonce:r,lambda:'READY',clock=lambda:1000.));v=json.loads(p.read_text());self.assertEqual(v['wakes'],11);self.assertEqual(v['last'],r);self.assertEqual(v['phase'],'COOLDOWN')
