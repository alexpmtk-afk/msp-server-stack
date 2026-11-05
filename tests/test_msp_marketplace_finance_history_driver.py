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
   self.assertEqual(out['phase'],'READY');self.assertEqual(out['wakes'],1);self.assertEqual(calls,['DISPATCHING'])
