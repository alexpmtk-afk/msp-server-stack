import datetime,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
P=Path(os.environ.get('WB_TEST_PAYLOAD',Path(__file__).parent/'payload'));sys.path.insert(0,str(P))
import policy,worker as w,controller as c,plan
CAB=plan.CABINETS[0]
def index():return {'cabinet':CAB,'reports':{'x':{'report_id':'10','report_type':1,'period':'weekly','from':'2026-11-02','to':'2026-11-08','currency':'RUB'}}}
def job(period='daily',attempt=1,start='2026-11-09',end=None):return {'cabinet':CAB,'period':period,'date_from':start,'date_to':end or start,'attempt':attempt,'bootstrap':False}
def parts(main='VERIFIED',listed=False):return [{'type':1,'status':main,'report_ids':[]},{'type':2,'status':'WAITING_DATA','report_ids':['99'] if listed else []}]
MON=datetime.datetime(2026,11,9,9,tzinfo=policy.TZ);TUE=MON+datetime.timedelta(days=1)
class MorePolicyTests(unittest.TestCase):
 def test_daily_never_waits_for_absent_counterpart(self):
  for attempt in (1,2,3):
   r=policy.assess(job(attempt=attempt),parts(),index(),MON)
   self.assertEqual(r[1]['status'],policy.OPTIONAL);self.assertFalse(r[1]['financial_zero_inferred'])
 def test_weekly_monday_never_waits_for_absent_counterpart(self):
  for attempt in (1,9,10):self.assertEqual(policy.assess(job('weekly',attempt,'2026-11-02','2026-11-08'),parts(),index(),MON)[1]['status'],policy.OPTIONAL)
 def test_weekly_tuesday_main_ready_closes_absent_optional(self):self.assertEqual(policy.assess(job('weekly',1,'2026-11-02','2026-11-08'),parts(),index(),TUE)[1]['status'],policy.OPTIONAL)
 def test_later_verified_main_closes_previous_optional_day(self):
  i=index();i['reports']['daily']={'report_id':'11','report_type':1,'period':'daily','from':'2026-11-10','to':'2026-11-10'}
  self.assertEqual(policy.assess(job(),parts(),i,MON)[1]['reason'],'COUNTERPART_NOT_PUBLISHED_OTHER_TYPE_VERIFIED')
 def test_missing_main_remains_required(self):
  r=policy.assess(job(attempt=3),parts('WAITING_DATA'),index(),MON);self.assertEqual(policy.overall(r),'WAITING_DATA');self.assertEqual([p['type'] for p in policy.required_missing(r)],[1,2])
 def test_positively_listed_optional_is_never_treated_as_absent(self):
  r=policy.assess(job(attempt=3),parts(listed=True),index(),MON);self.assertEqual(r[1]['status'],'WAITING_DATA');self.assertEqual([p['type'] for p in policy.required_missing(r)],[2])
 def test_incomplete_weekly_main_does_not_close_a_gap(self):self.assertFalse(policy.main_closure(index(),'2026-11-01','2026-11-02'))
 def test_hold_result_is_never_reassessed(self):
  j=plan.make_job(CAB,'daily','2026-11-02','2026-11-02');j['attempts']=3;r={'status':'HOLD'};self.assertIs(policy.reassess_result(j,r,index()),r)
 def test_settled_optional_wait_reassesses_without_mutating_source(self):
  j=plan.make_job(CAB,'daily','2026-11-02','2026-11-02');j['attempts']=3;r=dict(status='WAITING_DATA',cabinet=CAB,period='daily',date_from=j['from'],date_to=j['to'],parts=parts(),source_verified=True)
  updated=policy.reassess_result(j,r,index());self.assertEqual(updated['status'],'VERIFIED');self.assertEqual(r['status'],'WAITING_DATA');self.assertEqual(j['attempts'],3)
 def test_root_cycle_reassessment_preserves_attempts_and_request_evidence(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
   root=Path(t);(root/'cycles').mkdir();j=plan.make_job(CAB,'daily','2026-11-02','2026-11-02');j.update(attempts=3,status='WAITING_NEXT_RUN');j['result']=dict(status='WAITING_DATA',cabinet=CAB,period='daily',date_from=j['from'],date_to=j['to'],parts=parts(),source_verified=True);cycle=dict(key='fixture',jobs=[j]);(root/'jobs.json').write_text('{}')
   def replace(p,v,*args):p.write_text(json.dumps(v))
   with patch.object(c,'BASE',root),patch.object(c,'verified_index',return_value=index()),patch.object(c,'replace',side_effect=replace),patch.object(c.r,'run',side_effect=AssertionError('NO API OR SERVICE CALL')):c.refresh_optional_waits(cycle)
   self.assertEqual(j['status'],'VERIFIED');self.assertEqual(j['attempts'],3)
 def test_unknown_retained_outcome_blocks_early_closure(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
   p=Path(t);(p/'list-000.entry.json').write_text('{}')
   with self.assertRaises(ValueError):w.retained_inventory(job(),p)
 def test_optional_only_notice_creates_no_send_intent(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
   root=Path(t);j=plan.make_job(CAB,'daily','2026-11-09','2026-11-09');j.update(status='WAITING_NEXT_RUN',attempts=3,result={'parts':parts()})
   with patch.object(c,'BASE',root),patch.object(c.r,'trust'),patch.object(c.r,'run',side_effect=AssertionError('NO NOTIFICATION')):c.notice({'key':'fixture'},j)
   self.assertFalse(list(root.rglob('*.json')))
if __name__=='__main__':unittest.main()
