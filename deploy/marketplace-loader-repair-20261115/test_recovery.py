import copy,importlib.util,os,sys,unittest
from pathlib import Path
P=Path(os.environ.get('REPAIR_PAYLOAD',Path(__file__).parent/'payload'))
sys.path.insert(0,str(P))
import calendar_recovery as r

class RecoveryTests(unittest.TestCase):
 def fixture(self):
  cycle=dict(key='2026-11-15',cycle_id='a'*32,status='HOLD',jobs=[])
  catalog={};sources={}
  for cab in r.CABINETS:
   key=cab+'|2026-11-14';result=dict(status='HOLD',cabinet=cab,day='2026-11-14',error_type='AccrualError',frames=[dict(file='ozon_accruals.py',function='request_body',line=54)])
   cycle['jobs'].append(dict(key=key,cabinet=cab,day='2026-11-14',status='HOLD',attempts=1,result=result,next_due=0))
   catalog[key]=dict(status='HOLD',result=result,cycle_id='a'*32,receipt='retained')
   sources[cab]=dict(result=result,entries=0,responses=0,derived=0,nonce='b'*32)
  return cycle,catalog,sources
 def test_rearm_preserves_attempt_identity_and_original_diagnostics(self):
  cycle,catalog,sources=self.fixture();before=copy.deepcopy((cycle,catalog,sources))
  cy,ca=r.rearm(cycle,catalog,sources,day='2026-11-14',cycle_id='a'*32,now=123)
  self.assertEqual((cycle,catalog,sources),before);self.assertEqual(cy['cycle_id'],'a'*32)
  self.assertEqual(cy['status'],'RUNNING')
  self.assertTrue(all(j['attempts']==1 and j['status']=='IN_FLIGHT' for j in cy['jobs']))
  self.assertTrue(all(j['calendar_recovery']['original_result']['error_type']=='AccrualError' for j in cy['jobs']))
  self.assertTrue(all(ca[j['key']]['status']=='RECOVERY_PENDING' for j in cy['jobs']))
 def test_any_sender_entry_or_response_blocks_rearm(self):
  for field in ('entries','responses','derived'):
   cycle,catalog,sources=self.fixture();sources[r.CABINETS[0]][field]=1
   with self.subTest(field=field),self.assertRaises(ValueError):r.rearm(cycle,catalog,sources,day='2026-11-14',cycle_id='a'*32,now=0)
 def test_wrong_error_cabinet_day_cycle_or_attempt_blocks_rearm(self):
  for change in ('error','cabinet','day','cycle','attempt','missing'):
   cy,ca,s=self.fixture()
   if change=='error':s[r.CABINETS[0]]['result']['error_type']='HTTPError'
   elif change=='cabinet':cy['jobs'][0]['cabinet']='foreign'
   elif change=='day':cy['jobs'][0]['day']='2026-11-13'
   elif change=='cycle':cy['cycle_id']='c'*32
   elif change=='attempt':cy['jobs'][0]['attempts']=2
   else:cy['jobs'].pop()
   with self.subTest(change=change),self.assertRaises(ValueError):r.rearm(cy,ca,s,day='2026-11-14',cycle_id='a'*32,now=0)

if __name__=='__main__':unittest.main(verbosity=2)
