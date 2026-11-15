"""WB/Ozon operational invariants at calendar boundaries; all local fixtures."""
import datetime,importlib.util,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
P=Path(os.environ.get('REPAIR_PAYLOAD',Path(__file__).parent/'payload'));sys.path.insert(0,str(P))
import plan,worker,catalog,calendar_upgrade as upgrade

class AuditTests(unittest.TestCase):
 def test_wb_monday_across_year_daily_first_weekly_exact_previous_week(self):
  now=datetime.datetime(2027,1,4,8,45,tzinfo=plan.TZ)
  coverage={c:[dict(report_type=1,to='2026-12-27')] for c in plan.CABINETS}
  cy=plan.make_cycle(now,{},coverage)
  weeks=[j for j in cy['jobs'] if j['period']=='weekly'];daily=[j for j in cy['jobs'] if j['period']=='daily']
  self.assertEqual(len(weeks),3);self.assertEqual(len(daily),21)
  self.assertTrue(all(j['from']=='2026-12-28' and j['to']=='2027-01-03' for j in weeks))
  self.assertEqual(plan.due_job(cy,now.timestamp())['period'],'daily')
  self.assertTrue(all(j['max_attempts']==10 for j in weeks));self.assertTrue(all(j['max_attempts']==3 for j in daily))
 def test_wb_real_job_boundary_accepts_new_year_rejects_today_and_wrong_daily_span(self):
  class Clock(datetime.datetime):
   @classmethod
   def now(cls,tz=None):return cls(2027,1,2,8,45,tzinfo=tz)
  job=dict(cabinet=plan.CABINETS[0],date_from='2027-01-01',date_to='2027-01-01',period='daily',cycle_id='a'*32,nonce='b'*32,attempt=1,bootstrap=False)
  st=type('St',(),dict(st_mode=0o100644,st_uid=0,st_nlink=1))()
  def read(value):
   with patch.dict(os.environ,MSP_REPORT_JOB='/fixture'),patch.object(worker.Path,'lstat',return_value=st),patch.object(worker.Path,'read_bytes',return_value=json.dumps(value).encode()),patch.object(worker.datetime,'datetime',Clock):return worker.read_job()
  self.assertEqual(read(job),job)
  for change in ({'date_to':'2027-01-02'},{'date_from':'2026-12-31'},{'attempt':4},{'cabinet':'unknown'}):
   with self.subTest(change=change),self.assertRaises(ValueError):read(dict(job,**change))
 def test_wb_cross_year_weekly_coverage_excludes_daily_only_same_type_currency(self):
  reports={}
  for rid,period,typ,currency,start,end in [('1','weekly',1,'RUB','2026-12-28','2027-01-03'),('2','daily',1,'RUB','2027-01-01','2027-01-01'),('3','daily',2,'RUB','2027-01-01','2027-01-01'),('4','daily',1,'USD','2027-01-01','2027-01-01')]:
   reports[rid]=dict(report_id=rid,period=period,report_type=typ,currency=currency,**{'from':start,'to':end})
  active,sup=catalog.active_reports(dict(reports=reports));self.assertEqual([r['report_id'] for r in sup],['2']);self.assertEqual({r['report_id'] for r in active},{'1','3','4'})
 def test_installer_nonroot_refuses_before_system_reads(self):
  with patch.object(upgrade.os,'geteuid',return_value=1001),patch.object(upgrade.r,'verify_payload') as verify:
   with self.assertRaises(PermissionError):upgrade.main()
   verify.assert_not_called()
 def test_installer_drift_refuses_before_mutation(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
   path=Path(t)/'unit';path.write_bytes(b'changed')
   with patch.object(upgrade.r,'trust'),self.assertRaises(ValueError):upgrade.pins(dict(files={str(path):'0'*64}))
 def test_ozon_plan_at_new_year_never_requests_today(self):
  spec=importlib.util.spec_from_file_location('oz_calendar_plan',P/'ozon/plan.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  now=datetime.datetime(2027,1,1,8,40,tzinfo=m.TZ)
  known={c+'|'+d.isoformat():{'status':'VERIFIED'} for c in m.CABINETS for d in (datetime.date(2026,11,13)+datetime.timedelta(days=n) for n in range(48))}
  cy=m.make_cycle(now,known);self.assertEqual({j['day'] for j in cy['jobs']},{'2026-12-31'});self.assertEqual(len(cy['jobs']),3)

if __name__=='__main__':
 def deny(e,a):
  if e in ('socket.connect','socket.bind','socket.getaddrinfo'):raise AssertionError('NO NETWORK')
 sys.addaudithook(deny);unittest.main(verbosity=2)
