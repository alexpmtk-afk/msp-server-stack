import datetime,json,os,sys,unittest
from pathlib import Path
from unittest.mock import patch
P=Path(os.environ.get('WB_TEST_PAYLOAD',Path(__file__).parent/'payload'));sys.path.insert(0,str(P))
import plan,worker as w,catalog
CAB='wb_dmitrieva'
def rec(rid=1,typ=1,period='weekly',start='2026-11-02',end='2026-11-08'):
 return {'report_id':str(rid),'report_type':typ,'period':period,'from':start,'to':end,'currency':'RUB','rows':1,'csv':'/unused','sha256':'0'*64}
def job(period='daily',attempt=1,start='2026-11-02',end=None):return dict(cabinet=CAB,period=period,date_from=start,date_to=end or start,cycle_id='a'*32,nonce='b'*32,attempt=attempt,bootstrap=False)
class PolicyTests(unittest.TestCase):
 def run_worker(self,j,index,rows,transport_forbidden=False):
  class Sender:
   calls=[]
   def __init__(self,*args):
    if transport_forbidden:raise AssertionError('No new HTTP transport for dates closed by weekly main')
   def __call__(self,*args):self.calls.append(args);return (200,rows)
  with patch.object(catalog,'seed_baseline',return_value=index),patch.object(w,'Transport',Sender),patch.object(w,'capture_report',side_effect=lambda job,sender,r,index:rec(r['reportId'],r['reportType'],j['period'],r['dateFrom'],r['dateTo'])),patch.object(catalog,'publish',return_value=dict(generation='c'*32,sha256='d'*64)),patch.object(catalog,'store_index'),patch.object(catalog,'snapshot',return_value={}),patch.object(catalog,'iter_view',return_value=iter([])):
   return w.execute(j,Path('/nonexistent-state-fixture'))
 def test_primary_weekly_watermark_does_not_wait_for_optional_buyout(self):
  coverage={c:[rec(),rec(2,2,start='2026-10-26',end='2026-10-31')] for c in plan.CABINETS}
  cycle=plan.make_cycle(datetime.datetime(2026,11,13,8,45,tzinfo=plan.TZ),{},coverage)
  self.assertEqual({j['from'] for j in cycle['jobs']},{'2026-11-%02d'%d for d in range(9,13)})
 def test_daily_already_closed_by_weekly_main_requires_no_http(self):
  result=self.run_worker(job(),{'cabinet':CAB,'reports':{'main':rec()}},[],True)
  self.assertEqual(result['status'],'VERIFIED');self.assertEqual(result['parts'][1]['status'],'OPTIONAL_NOT_LISTED')
 def test_absent_optional_daily_is_quiet_after_last_check(self):
  row=dict(reportId=12,reportType=1,dateFrom='2026-11-12',dateTo='2026-11-12',currency='RUB',sellerFinanceName='seller')
  result=self.run_worker(job(attempt=3,start='2026-11-12'),{'cabinet':CAB,'reports':{}},[row])
  self.assertEqual(result['status'],'VERIFIED');self.assertEqual(result['parts'][1]['status'],'OPTIONAL_NOT_LISTED')
if __name__=='__main__':unittest.main()
