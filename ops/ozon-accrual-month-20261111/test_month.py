import unittest,sys,json,tempfile,io,os,csv
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).parent;sys.path.insert(0,str(ROOT/'payload'))
import capture_worker as w
import capture_root as c
import start_root as s

def row(day,i=1,**extra):return {'accrual_id':i,'date':day,'accrued_category':'NON_ITEM','non_item_fee':{'type_id':46,'accrued':{'amount':'-0.10','currency':'RUB'}},'total_amount':{'amount':'-0.10','currency':'RUB'},**extra}
def raw(rows,last=''):return json.dumps({'accruals':rows,'last_id':last}).encode()
class MonthTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=ROOT);self.addCleanup(self.tmp.cleanup);self.state=Path(self.tmp.name)
  p=patch.object(w,'STATE',self.state);p.start();self.addCleanup(p.stop)
 def test_actual_seed_offline_all_fields_preserved(self):
  source=Path('/opt/mcp/data/msp-marketplace-reports/ozon-accrual-pilot-20261111/day-first-page.response.json').read_bytes()
  (self.state/'day-first-page.seed.json').write_bytes(source)
  def forbidden(*args,**kwargs):raise AssertionError('must reuse known response without fetch')
  d=w.collect_day('2026-01-15',{},fetcher=forbidden)
  self.assertEqual(d['rows'],json.loads(source)['accruals']);self.assertEqual(len(d['rows']),15);self.assertFalse(d['provider_coverage_verified'])
 def test_two_pages_dedup_identical_not_conflict(self):
  calls=[]
  def fetch(day,index,cursor,cred,**kwargs):
   calls.append(cursor);return (raw([row(day)],'next') if index==1 else raw([row(day),row(day,2)])),w.time.time()
  result=w.collect_day('2026-01-01',{},fetcher=fetch,sleeper=lambda _:None)
  self.assertEqual(calls,['','next']);self.assertEqual(len(result['rows']),2)
 def test_conflicting_pages_hold(self):
  def fetch(day,index,cursor,cred,**kwargs):return raw([row(day,unit_number=str(index))],'next' if index==1 else ''),w.time.time()
  with self.assertRaises(ValueError):w.collect_day('2026-01-01',{},fetcher=fetch,sleeper=lambda _:None)
 def test_page_limit_not_marked_complete(self):
  def fetch(day,index,cursor,cred,**kwargs):return raw([row(day,index)],str(index)),w.time.time()
  with patch.object(w,'PAGE_LIMIT',2),self.assertRaises(ValueError):w.collect_day('2026-01-01',{},fetcher=fetch,sleeper=lambda _:None)
 def test_missing_cursor_retained_not_complete(self):
  def fetch(*args,**kwargs):return b'{"accruals":[]}',w.time.time()
  with self.assertRaises(ValueError):w.collect_day('2026-01-01',{},fetcher=fetch,sleeper=lambda _:None)
 def test_month_views_roundtrip_and_no_money_double_count(self):
  rows=[row('2026-01-01'),row('2026-01-02',2,extra_unknown={'x':True})]
  result=w.write_views([{'date':r['date'],'rows':[r],'pages':[],'status':'CURSOR_EXHAUSTED_UNRECONCILED'} for r in rows],{46:{'description':'placement'}})
  saved=list(csv.DictReader(io.StringIO((self.state/'month.csv').read_text('utf-8-sig')),delimiter=';'))
  self.assertEqual([json.loads(x['_raw_json']) for x in saved],rows)
  coverage=json.loads((self.state/'coverage.json').read_text());self.assertEqual(coverage['net_total_amount_by_currency'],{'RUB':'-0.20'});self.assertFalse(coverage['cabinet_export_reconciliation_complete']);self.assertNotIn('net_total_amount_by_currency',result)
 def test_full31days_mocked_execution(self):
  cat={'accrual_types':[{'id':46,'name':'Placement','description':'placement'}]}
  def collect(day,cred):return {'date':day,'rows':[row(day)],'pages':[],'status':'CURSOR_EXHAUSTED_UNRECONCILED'}
  with patch.object(w,'check_job',return_value={'nonce':'b'*32}),patch.object(w,'seed',side_effect=lambda label:json.dumps(cat).encode() if label=='types' else raw([row('2026-01-15')])),patch.object(w,'load_credentials',return_value={w.CABINET:{}}),patch.dict(os.environ,{'CREDENTIALS_DIRECTORY':str(self.state)}),patch.object(w,'collect_day',side_effect=collect),patch.object(w.time,'sleep'):
   result=w.execute()
  self.assertEqual(result['days_collected'],31);self.assertEqual(result['rows'],31);self.assertEqual(len(list(self.state.glob('*.summary.json'))),31);self.assertFalse(result['full_month_complete'])
 def test_budget_refused_before_transport(self):
  d=self.state/'2026-01-01';d.mkdir();(d/'old.entry.json').write_text('{}')
  with patch.object(w,'BUDGET',1),patch.object(w,'check_job'),self.assertRaises(ValueError):w.fetch_day_page('2026-01-01',1,'',{})
 def test_expired_cursor_no_dispatch(self):
  with patch.object(w,'check_job'),self.assertRaises(ValueError):w.fetch_day_page('2026-01-01',1,'cursor',{},cursor_issued=w.time.time()-900)
  self.assertEqual(len(list(self.state.glob('*/*.entry.json'))),0)
 def test_quota_denies_february_and_unrelated_method(self):
  for path,body in [(w.PATH,{'date':'2026-02-01','last_id':''}),('/v1/finance/accrual/types',{}),('/v1/finance/realization/posting',{})]:
   with self.assertRaises(ValueError):w.MonthQuota('ozon',{}).reserve(w.Request('ozon',path,body))
 def test_unknown_http_outcome_cannot_dispatch_again(self):
  class Opener:
   def open(self,*args,**kwargs):raise TimeoutError('fixture')
  with patch.object(w,'check_job'),patch.object(w.MonthQuota,'reserve',return_value=[]),patch.object(w,'_headers',return_value={}):
   with self.assertRaises(TimeoutError):w.fetch_day_page('2026-01-01',1,'',{},factory=Opener)
   with self.assertRaises(ValueError):w.fetch_day_page('2026-01-01',1,'',{},factory=Opener)
  self.assertEqual(len(list(self.state.glob('*/*.entry.json'))),1)
 def test_invalid_payload_durable_before_page_parser(self):
  class Response:
   status=200
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def read(self,n):return b'{invalid-json'
  class Opener:
   def open(self,*args,**kwargs):return Response()
  with patch.object(w,'check_job'),patch.object(w.MonthQuota,'reserve',return_value=[]),patch.object(w,'_headers',return_value={}):
   rawbytes,_=w.fetch_day_page('2026-01-01',1,'',{},factory=Opener)
  self.assertEqual((self.state/'2026-01-01/001.response.json').read_bytes(),rawbytes)
  with self.assertRaises(ValueError):w.inspect_page(rawbytes,'2026-01-01')
 def test_nonroot_no_scheduling(self):
  with patch.object(s.os,'geteuid',return_value=1001),patch.object(c,'preflight') as pf:
   with self.assertRaises(PermissionError):s.main()
   pf.assert_not_called()
 def test_unit_runtime_and_credentials(self):
  text=c.unit_text(['127.0.0.1/32']).decode();self.assertIn('TimeoutStartSec=10800',text);self.assertIn('ConditionPathExists=\nConditionPathIsDirectory=',text);self.assertNotIn('MSP_REPORTS_OZON_FINANCE_METHODS_VERIFIED',text)

if __name__=='__main__':
 def deny(event,args):
  if event in ('socket.connect','socket.bind','socket.getaddrinfo'):raise RuntimeError('NETWORK DENIED')
 sys.addaudithook(deny);unittest.main(verbosity=2)
