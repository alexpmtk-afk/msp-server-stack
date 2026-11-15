"""Offline production-worker calendar and publication regressions; no provider calls."""
import datetime, importlib.util, io, json, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

P=Path(os.environ.get('REPAIR_PAYLOAD', Path(__file__).parent/'payload'))
CAB=os.environ.get('REPAIR_CABINET','ozon_dmitrieva')
sys.path.insert(0,str(P/'ozon'/CAB))
import capture_worker as w
from apps.msp_marketplace_reports.ozon_accruals import request_body, inspect_page
from apps.msp_marketplace_reports.generation_store import read_active
from apps.msp_marketplace_reports.versioned_archive import import_csv_versioned

class CalendarTests(unittest.TestCase):
 def test_actual_request_path_accepts_next_day_month_year_and_leap_day(self):
  for day in ('2026-11-14','2026-11-30','2026-12-01','2026-12-31','2027-01-01','2028-02-29','2028-03-01'):
   with self.subTest(day=day):
    self.assertEqual(request_body(day),{'date':day,'last_id':''})
    self.assertEqual(inspect_page(b'{"accruals":[],"last_id":""}',day)['rows'],[])

 def test_bad_calendar_inputs_rejected(self):
  for day in ('2027-02-29','2026-13-01','2026-11-31','2026-1-1','../2026-11-14',None,20261114):
   with self.subTest(day=day),self.assertRaises((ValueError,TypeError)):request_body(day)

 def test_future_today_and_unauthorized_jobs_rejected_at_worker_boundary(self):
  class Clock(datetime.datetime):
   @classmethod
   def now(cls,tz=None):return cls(2027,1,2,8,40,tzinfo=tz)
  job=dict(cabinet=CAB,period='2027-01',day='2027-01-01',max_send_entries=10,nonce='a'*32,expires_epoch=0,cycle_id='b'*32,attempt=1)
  st=type('St',(),dict(st_mode=0o100644,st_uid=0,st_nlink=1))()
  def check(value):
   with patch.object(w.Path,'lstat',return_value=st),patch.object(w.Path,'read_bytes',return_value=w.doc(value)),patch('datetime.datetime',Clock):return w.check_job()
  self.assertEqual(check(job),job)
  for change in ({'day':'2027-01-02'},{'day':'2027-01-03'},{'period':'2026-12'},{'day':'2026-11-12','period':'2026-11'},{'cabinet':'foreign'},{'attempt':4}):
   with self.subTest(change=change),self.assertRaises(ValueError):check(dict(job,**change))

 def test_full_worker_new_month_and_year_publication_replay_preserves_other_days(self):
  for day in ('2026-11-14','2026-12-01','2027-01-01','2028-02-29'):
   with self.subTest(day=day),tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
    archive=Path(t)/'archive';history=archive/'history';state=history/day/('b'*32)/'attempt-01';d=state/day;d.mkdir(parents=True)
    row={'date':day,'accrual_id':1,'accrued_category':'ITEM','total_amount':{'amount':'12.34','currency':'RUB'}}
    raw=w.doc({'accruals':[row],'last_id':''})
    (d/'001.entry.json').write_bytes(w.doc({'cabinet':CAB,'method':w.PATH,'body':request_body(day),'send_entry_number':1}))
    (d/'001.response.json').write_bytes(raw)
    (d/'001.meta.json').write_bytes(w.doc({'status':200,'sha256':w.sha(raw),'bytes':len(raw),'truncated':False,'received_epoch':1}))
    seed=b'{"accrual_types":[{"id":1,"name":"fixture","description":"offline fixture"}]}'
    job=dict(cabinet=CAB,period=day[:7],day=day,max_send_entries=10,nonce='a'*32,expires_epoch=0,cycle_id='b'*32,attempt=1)
    with patch.object(w,'ARCHIVE',archive),patch.object(w,'HISTORY',history),patch.object(w,'check_job',return_value=job),patch.object(w,'seed',return_value=seed),patch.object(w,'load_credentials',side_effect=AssertionError('NO CREDENTIALS OR HTTP')):
     first=w.execute();second=w.execute()
     self.assertEqual(first,second);self.assertEqual(first['rows'],1);self.assertTrue(first['other_days_preserved'])
     self.assertEqual(read_active(archive,'ozon_current_accruals',CAB,day[:7])['generation'],first['generation'])

if __name__=='__main__':
 def deny(event,args):
  if event in ('socket.connect','socket.bind','socket.getaddrinfo'):raise AssertionError('NO NETWORK')
 sys.addaudithook(deny);unittest.main(verbosity=2)
