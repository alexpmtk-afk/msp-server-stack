import unittest,sys,tempfile,json,time,os
from pathlib import Path
from unittest.mock import patch
B=Path(__file__).parent;P=Path(os.environ.get('RECOVERY_TEST_PAYLOAD',str(B/'payload')));sys.path.insert(0,str(P))
class RecoveryTests(unittest.TestCase):
 def test_lost_start_notification_does_not_stop_or_start_twice(self):
  from recovery import wait_worker,StartNotificationLost
  calls=[];states=iter(['activating','unavailable','active','inactive']);receipts=iter([False,False,False,True])
  def start():calls.append('start');raise StartNotificationLost('bus lost')
  r=wait_worker(start=start,state=lambda:next(states),has_result=lambda:next(receipts),pause=lambda reason:calls.append('pause'),sleeper=lambda x:None,deadline=time.time()+60)
  self.assertEqual(r,'receipt');self.assertEqual(calls.count('start'),1);self.assertIn('pause',calls);self.assertNotIn('stop',calls)
 def test_terminal_receipt_never_restarts_worker(self):
  from recovery import wait_worker
  r=wait_worker(start=lambda:(_ for _ in ()).throw(AssertionError('restart')),state=lambda:'inactive',has_result=lambda:True,pause=lambda x:None,sleeper=lambda x:None,deadline=time.time()+60)
  self.assertEqual(r,'receipt')
 def test_unsafe_reconciliation_failure_not_treated_as_bus_pause(self):
  from recovery import wait_worker
  with self.assertRaises(ValueError):wait_worker(start=lambda:(_ for _ in ()).throw(ValueError('unknown outcome')),state=lambda:'failed',has_result=lambda:False,pause=lambda x:None,sleeper=lambda x:None,deadline=time.time()+60)
 def test_inactive_worker_without_result_requests_reconciliation(self):
  from recovery import wait_worker
  result=wait_worker(start=lambda:None,state=lambda:'failed',has_result=lambda:False,pause=lambda x:None,sleeper=lambda x:None,deadline=time.time()+60)
  self.assertEqual(result,'reconcile')
 def test_retained_page_replay_does_not_enter_transport(self):
  from recovery import retained_page
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as tmp:
   d=Path(tmp);entry={'cabinet':'ozon_novokshenov','method':'/v1/finance/accrual/by-day','body':{'date':'2026-11-01','last_id':''},'send_entry_number':1};raw=b'{"accruals":[],"last_id":""}'
   import hashlib
   (d/'001.entry.json').write_text(json.dumps(entry));(d/'001.response.json').write_bytes(raw);(d/'001.meta.json').write_text(json.dumps({'status':200,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'truncated':False,'received_epoch':1}))
   self.assertEqual(retained_page(d,1,'ozon_novokshenov','2026-11-01',''),(raw,1))
   (d/'001.response.json').unlink()
   with self.assertRaises(ValueError):retained_page(d,1,'ozon_novokshenov','2026-11-01','')
 def test_no_entry_is_new_but_orphan_response_is_hold(self):
  from recovery import retained_page
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as tmp:
   d=Path(tmp);self.assertIsNone(retained_page(d,1,'ozon_novokshenov','2026-11-01',''))
   (d/'001.response.json').write_bytes(b'{}')
   with self.assertRaises(ValueError):retained_page(d,1,'ozon_novokshenov','2026-11-01','')
 def test_expired_cursor_is_hold_not_new_day_request(self):
  from recovery import check_cursor_age
  with self.assertRaises(ValueError):check_cursor_age('opaque',1,now=1000)
  check_cursor_age('',1,now=1000)
class WorkerRecoveryTests(unittest.TestCase):
 def test_completed_pages_are_reused_through_publication_without_http(self):
  import subprocess
  p=subprocess.run([sys.executable,str(B/'test_worker_recovery.py')],capture_output=True,text=True,env=dict(os.environ,RECOVERY_TEST_PAYLOAD=str(P)))
  self.assertEqual(p.returncode,0,p.stdout+p.stderr)

if __name__=='__main__':
 def deny(event,args):
  if event in ('socket.connect','socket.bind','socket.getaddrinfo'):raise RuntimeError('NETWORK DENIED')
 sys.addaudithook(deny);unittest.main(verbosity=2)
