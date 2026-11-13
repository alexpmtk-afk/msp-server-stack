import datetime, json, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
P=Path(os.environ.get('WB_TEST_PAYLOAD',Path(__file__).parent/'payload'));sys.path.insert(0,str(P))
import policy, controller as c, plan
sys.path.insert(0,str(Path(__file__).parent))
import test_policy as fixture
from test_policy import job, rec

class AvailabilityTests(unittest.TestCase):
 def test_three_publication_variants_complete_on_first_check(self):
  for period in ('daily','weekly'):
   for bootstrap in (False,True):
    for types in ((1,),(2,),(1,2)):
     with self.subTest(period=period,bootstrap=bootstrap,types=types):
      parts=[dict(type=t,status='VERIFIED' if t in types else 'WAITING_DATA',report_ids=[str(t)] if t in types else []) for t in (1,2)]
      j=job(period=period,attempt=1);j['bootstrap']=bootstrap
      result=policy.assess(j,parts,{'reports':{}})
      self.assertEqual(policy.overall(result),'VERIFIED')
      self.assertEqual(policy.required_missing(result),[])
      for part in result:
       if part['type'] not in types:self.assertFalse(part['financial_zero_inferred']);self.assertFalse(part['report_downloaded'])
 def test_neither_report_retains_daily_and_monday_retry_limits(self):
  for period,limit in (('daily',3),('weekly',10)):
   for attempt in (1,limit):
    parts=[dict(type=t,status='WAITING_DATA',report_ids=[]) for t in (1,2)]
    result=policy.assess(job(period=period,attempt=attempt),parts,{'reports':{}})
    self.assertEqual(policy.overall(result),'WAITING_DATA')
    self.assertEqual([p['type'] for p in policy.required_missing(result)],[1,2])
 def test_listed_but_uncaptured_counterpart_is_not_absence(self):
  for ready in (1,2):
   parts=[dict(type=t,status='VERIFIED' if t==ready else 'WAITING_DATA',report_ids=[str(t)]) for t in (1,2)]
   result=policy.assess(job(),parts,{'reports':{}})
   self.assertEqual(policy.overall(result),'WAITING_DATA');self.assertEqual([p['type'] for p in policy.required_missing(result)],[3-ready])
 def test_either_weekly_type_sets_watermark(self):
  for typ in (1,2):
   coverage={cab:[rec(typ=typ)] for cab in plan.CABINETS}
   cycle=plan.make_cycle(datetime.datetime(2026,11,13,8,45,tzinfo=plan.TZ),{},coverage)
   self.assertEqual({j['from'] for j in cycle['jobs']},{'2026-11-%02d'%d for d in range(9,13)})
 def test_no_notice_or_send_intent_if_either_type_complete(self):
  for ready in (1,2):
   with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
    root=Path(t);j=plan.make_job(plan.CABINETS[0],'daily','2026-11-09','2026-11-09')
    j.update(status='WAITING_NEXT_RUN',attempts=3,result={'parts':[dict(type=x,status='VERIFIED' if x==ready else 'WAITING_DATA',report_ids=[]) for x in (1,2)]})
    with patch.object(c,'BASE',root),patch.object(c.r,'run',side_effect=AssertionError('NO MESSAGE')):c.notice({'key':'fixture'},j)
    self.assertFalse(list(root.rglob('*')))
 def test_old_buyout_only_wait_is_reassessed_without_mutating_source(self):
  j=plan.make_job(plan.CABINETS[0],'daily','2026-11-09','2026-11-09');j.update(attempts=1)
  source=dict(status='WAITING_DATA',cabinet=j['cabinet'],period=j['period'],date_from=j['from'],date_to=j['to'],source_verified=True,parts=[dict(type=t,status='VERIFIED' if t==2 else 'WAITING_DATA',report_ids=['2'] if t==2 else []) for t in (1,2)])
  result=policy.reassess_result(j,source,{'reports':{}})
  self.assertEqual(result['status'],'VERIFIED');self.assertEqual(source['status'],'WAITING_DATA');self.assertEqual(j['attempts'],1)
 def test_weekly_coverage_union_must_not_mix_types(self):
  index={'reports':{'a':rec(1,1,start='2026-11-01',end='2026-11-02'),'b':rec(2,2,start='2026-11-03',end='2026-11-04')}}
  self.assertFalse(policy.weekly_closure(index,'2026-11-01','2026-11-04'))
 def test_buyout_weekly_reuse_needs_no_transport(self):
  result=fixture.PolicyTests().run_worker(job(),{'cabinet':plan.CABINETS[0],'reports':{'buyout':rec(typ=2)}},[],True)
  self.assertEqual(result['status'],'VERIFIED')
 def test_worker_all_three_variants_complete_on_first_check(self):
  for period in ('daily','weekly'):
   for types in ((1,),(2,),(1,2)):
    j=job(period=period,start='2026-11-02',end='2026-11-02' if period=='daily' else '2026-11-08')
    rows=[dict(reportId=t,reportType=t,dateFrom=j['date_from'],dateTo=j['date_to'],currency='RUB',sellerFinanceName='seller') for t in types]
    result=fixture.PolicyTests().run_worker(j,{'cabinet':j['cabinet'],'reports':{}},rows)
    self.assertEqual(result['status'],'VERIFIED')
 def test_real_catalog_daily_then_weekly_for_all_three_variants(self):
  import catalog as a, worker as w
  for types in ((1,),(2,),(1,2)):
   with self.subTest(types=types),tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
    root=Path(t);folder=root/'wb-current-catalog'/plan.CABINETS[0];(folder/'generations').mkdir(parents=True)
    index=dict(schema=1,cabinet=plan.CABINETS[0],reports={},baseline_seeded=True)
    def seed(*args):return a.load_index(plan.CABINETS[0],root) if (folder/'sources.json').exists() else index
    class Sender:
     def __init__(self,j,state):self.job=j;self.state=state;self.allowed=set();self.verified_files={}
     def __call__(self,key,path,body):
      def row(typ):return dict(reportId=9007199254740993+typ,reportType=typ,rrdId=1,dateFrom=self.job['date_from'],dateTo=self.job['date_to'],currency='RUB',sellerFinanceName='seller',retailAmount=11)
      if path==w.WB_LIST:return 200,[row(typ) for typ in types]
      typ=int(path[len(w.WB_DETAIL):])-9007199254740993
      if body['rrdId']:return 204,None
      values=[row(typ)];(self.state/(key+'.response')).write_bytes(a.doc(values));return 200,values
    for period in ('daily','weekly'):
     j=job(period=period,start='2026-11-02',end='2026-11-02' if period=='daily' else '2026-11-08');state=root/period;state.mkdir()
     with patch.object(w,'ARCHIVE',root),patch.object(a,'seed_baseline',side_effect=seed),patch.object(w,'Transport',Sender):result=w.execute(j,state)
     self.assertEqual(result['status'],'VERIFIED')
    active,replaced=a.active_reports(a.load_index(plan.CABINETS[0],root))
    self.assertEqual({r['report_type'] for r in active},set(types));self.assertEqual(len(active),len(types));self.assertEqual(len(replaced),len(types))
    for typ in (1,2):
     self.assertEqual(len(list(a.iter_view(a.snapshot(plan.CABINETS[0],typ,2026,root,allow_empty=True)))),int(typ in types))
     if typ not in types:
      with self.assertRaises(ValueError):a.snapshot(plan.CABINETS[0],typ,2026,root)
    original_snapshot=a.snapshot
    with patch.object(c.catalog,'snapshot',side_effect=lambda cab,typ,year,**kwargs:original_snapshot(cab,typ,year,root,**kwargs)):
     self.assertEqual(len(c.verified_index(plan.CABINETS[0])['reports']),len(types))

if __name__=='__main__':
 unittest.main()
