import unittest,sys,os,json,csv,io,tempfile,hashlib,calendar
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).parent;sys.path.insert(0,str(ROOT/'payload'))
import capture_worker as w
import year_root as h
import root_common as r
import verify_results as v
import start_root as s
from apps.msp_marketplace_reports.providers import Request
from apps.msp_marketplace_reports.archive import _location

SOURCE=Path('/opt/mcp/data/msp-marketplace-reports/ozon-accrual-month-pilot-20261111/month.csv')
def row(day,idx=1):return {'date':day,'accrual_id':idx,'accrued_category':'NON_ITEM','non_item_fee':{'type_id':46,'accrued':{'amount':'-0.10','currency':'RUB'}},'total_amount':{'amount':'-0.10','currency':'RUB'}}
def reply(rows,last=''):return json.dumps({'accruals':rows,'last_id':last}).encode()

class YearTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=ROOT);self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.archive=self.root/'archive';self.archive.mkdir();self.history=self.archive/'history';self.history.mkdir()
  for module,key,value in [(w,'ARCHIVE',self.archive),(w,'HISTORY',self.history),(v,'ARCHIVE',self.archive),(v,'HISTORY',self.history)]:
   p=patch.object(module,key,value);p.start();self.addCleanup(p.stop)
 def state(self,m):
  state=self.history/f'2026-{m:02d}';state.mkdir();w.PERIOD=state.name;w.STATE=state;w.BUDGET=0 if m==1 else 128
  return state
 def populate(self,m):
  state=self.state(m)
  if m==1:
   (state/'month.csv').write_bytes(SOURCE.read_bytes())
   result={'rows':728,'days_collected':31,'send_entries':0}
  else:
   days=[]
   for n in range(1,calendar.monthrange(2026,m)[1]+1):
    day=f'2026-{m:02d}-{n:02d}';folder=state/day;folder.mkdir();b=reply([row(day,n)])
    (folder/'001.response.json').write_bytes(b);meta={'status':200,'sha256':w.sha(b),'bytes':len(b),'truncated':False}
    (folder/'001.meta.json').write_text(json.dumps(meta));(folder/'001.entry.json').write_text(json.dumps({'cabinet':w.CABINET,'method':w.PATH,'body':{'date':day,'last_id':''}}))
    days.append({'date':day,'rows':[row(day,n)],'status':'CURSOR_EXHAUSTED_UNRECONCILED','pages':[{'page':1,'sha256':w.sha(b)}]})
   result=w.write_views(days,{46:{'description':'Placement'}});result.update(days_collected=len(days),send_entries=len(days))
  return w.publish_month(result)
 def test_actual_january_publish_without_credentials_or_http(self):
  state=self.state(1);(state/'month.csv').write_bytes(SOURCE.read_bytes())
  job={'period':'2026-01','max_send_entries':0,'nonce':'a'*32}
  with patch.object(w,'check_job',return_value=job),patch.object(w,'load_credentials',side_effect=AssertionError('credentials must not be read')):
   result=w.execute()
  self.assertEqual(result['rows'],728);self.assertEqual(result['send_entries'],0);self.assertEqual(result['status'],'PUBLISHED_SOURCE_VERIFIED')
 def test_full_mocked_ten_month_roundtrip_independent_verifier(self):
  months=[self.populate(m) for m in range(1,11)]
  result=v.verify_months({'cabinet':w.CABINET,'from_month':1,'to_month':10,'months':months},check_inodes=False)
  self.assertEqual(result['verified_days'],304);self.assertEqual(result['verified_new_send_entries'],273);self.assertTrue(result['all_monthly_source_and_published_values_match'])
 def test_duplicate_month_cannot_claim_complete(self):
  with self.assertRaises(ValueError):v.verify_months({'cabinet':w.CABINET,'from_month':1,'to_month':10,'months':[{'period':'2026-01'}]*10},check_inodes=False)
 def test_raw_corruption_rejected(self):
  months=[self.populate(m) for m in range(1,11)]
  p=self.history/'2026-02/2026-02-01/001.response.json';p.write_bytes(p.read_bytes()+b' ')
  with self.assertRaises(ValueError):v.verify_months({'cabinet':w.CABINET,'from_month':1,'to_month':10,'months':months},check_inodes=False)
 def test_permanent_not_current(self):
  self.assertIn('PERMANENT',_location(self.archive,'ozon_financial_accruals',w.CABINET,'2026-02').parts)
  self.assertNotIn('CURRENT',_location(self.archive,'ozon_financial_accruals',w.CABINET,'2026-02').parts)
 def test_january_refetch_quota_denied(self):
  w.PERIOD='2026-01'
  with self.assertRaises(ValueError):w.MonthQuota('ozon',{}).reserve(Request('ozon',w.PATH,{'date':'2026-01-01','last_id':''}))
 def test_november_other_month_method_denied(self):
  w.PERIOD='2026-02'
  for path,body in [(w.PATH,{'date':'2026-11-01','last_id':''}),(w.PATH,{'date':'2026-03-01','last_id':''}),('/v1/finance/realization/posting',{}),('/v1/finance/accrual/types',{})]:
   with self.assertRaises(ValueError):w.MonthQuota('ozon',{}).reserve(Request('ozon',path,body))
 def test_unknown_outcome_entry_preserved_no_retry(self):
  self.state(2)
  class Opener:
   def open(self,*args,**kwargs):raise TimeoutError('fixture')
  with patch.object(w,'check_job'),patch.object(w.MonthQuota,'reserve',return_value=[]),patch.object(w,'_headers',return_value={}):
   with self.assertRaises(TimeoutError):w.fetch_day_page('2026-02-01',1,'',{},factory=Opener)
   with self.assertRaises(ValueError):w.fetch_day_page('2026-02-01',1,'',{},factory=Opener)
  self.assertEqual(len(list(w.STATE.glob('*/*.entry.json'))),1)
 def test_quota_only_wait_consumes_no_entry(self):
  self.state(2)
  with patch.object(w,'check_job'),patch.object(w.MonthQuota,'reserve',side_effect=w.q.QuotaBusy(1)),patch.object(w.time,'sleep'):
   with self.assertRaises(w.q.QuotaBusy):w.fetch_day_page('2026-02-01',1,'',{})
  self.assertFalse(list(w.STATE.glob('*/*.entry.json')))
 def test_budget_exhausted_before_transport(self):
  self.state(2);d=w.STATE/'2026-02-01';d.mkdir();(d/'old.entry.json').write_text('{}')
  with patch.object(w,'BUDGET',1),patch.object(w,'check_job'),self.assertRaises(ValueError):w.fetch_day_page('2026-02-01',1,'',{})
 def test_cursor_expired_no_hidden_restart(self):
  self.state(2)
  with patch.object(w,'check_job'),self.assertRaises(ValueError):w.fetch_day_page('2026-02-01',1,'expired',{},cursor_issued=w.time.time()-900)
  self.assertFalse(list(w.STATE.glob('*/*.entry.json')))
 def test_nested_unknowns_and_container_retained(self):
  original=row('2026-02-01');original.update(accrued_category='CONTAINER_FEES',non_item_fee=None,container_fees={'fees':[{'type_id':999999,'accrued':{'amount':'-0.10','currency':'RUB'}}]},future={'x':'untouched'})
  result=w.inspect_page(reply([original]),'2026-02-01');self.assertEqual(result['rows'],[original])
 def test_identical_page_overlap_once_conflict_hold(self):
  first=w.inspect_page(reply([row('2026-02-01')],'next'),'2026-02-01')
  last=w.inspect_page(reply([row('2026-02-01')]),'2026-02-01',input_cursor='next',seen=first['seen']);self.assertEqual(last['rows'],[])
  changed=row('2026-02-01');changed['unit_number']='changed'
  with self.assertRaises(ValueError):w.inspect_page(reply([changed]),'2026-02-01',input_cursor='next',seen=first['seen'])
 def test_zero_money_and_no_sku_not_dropped(self):
  self.state(2);x=row('2026-02-01');x['total_amount']['amount']='0.00';x['non_item_fee']['accrued']['amount']='0.00'
  result=w.write_views([{'date':x['date'],'rows':[x],'pages':[],'status':'CURSOR_EXHAUSTED_UNRECONCILED'}],{46:{'description':'Placement'}});self.assertEqual(result['rows'],1)
 def test_conflicting_published_month_not_overwritten(self):
  self.populate(1);p=w.STATE/'month.csv';p.write_bytes(p.read_bytes().replace(b'2026-01-01',b'2026-01-02'))
  with self.assertRaises(ValueError):w.publish_month({})
 def test_nonroot_installer_refuses_before_reads(self):
  with patch.object(s.os,'geteuid',return_value=1001),patch.object(h,'preflight') as pf:
   with self.assertRaises(PermissionError):s.main()
   pf.assert_not_called()
 def test_policy_is_one_unit_one_verb_one_user(self):
  text=s.rule_text().decode();self.assertIn('subject.user === "hermes"',text);self.assertIn('action.lookup("verb") === "start"',text);self.assertIn('action.lookup("unit") === "'+h.UNIT+'"',text);self.assertNotIn('stop',text);self.assertNotIn('restart',text)
 def test_monthly_worker_keeps_january_network_closed(self):
  off=h.unit_text([],Path('2026-01'),False).decode();on=h.unit_text(['127.0.0.1/32'],Path('2026-02'),True).decode()
  self.assertIn('PrivateNetwork=yes',off);self.assertNotIn('LoadCredential=cabinets.json:',off);self.assertIn('LoadCredential=cabinets.json:',on);self.assertNotIn('MSP_REPORTS_OZON_FINANCE_METHODS_VERIFIED',on)
 def test_root_service_is_fixed_no_restart_and_cleanup(self):
  text=s.service_text().decode();self.assertIn('Restart=no',text);self.assertIn(' --cleanup',text);self.assertIn('year_root.py',text)
 def test_foreign_worker_activation_not_removed(self):
  ledger=self.root/'ledger';ledger.mkdir();drop=self.root/'drop';drop.write_bytes(b'foreign');(ledger/'activation.json').write_text(json.dumps({'nonce':'b'*32,'drop_sha256':r.sha(b'owned'),'credential_sha256':None}))
  with patch.object(h,'LEDGER',ledger),patch.object(r,'DROP',drop),patch.object(r,'trust'),patch.object(r,'run') as run:
   with self.assertRaises(ValueError):h.cleanup_worker()
   run.assert_not_called();self.assertTrue(drop.exists())
 def test_foreign_policy_not_removed(self):
  root=self.root/'code';root.mkdir();policy=self.root/'policy.rules';policy.write_bytes(b'foreign');(root/'setup-ownership.json').write_text(json.dumps({'rule_sha256':r.sha(b'owned')}))
  with patch.object(h.os,'geteuid',return_value=0),patch.object(h,'ROOT',root),patch.object(h,'RULE',policy),patch.object(h,'PUBLIC',self.root/'absent'),patch.object(h,'cleanup_worker'),patch.object(r,'trust'):
   with self.assertRaises(ValueError):h.cleanup_campaign()
  self.assertEqual(policy.read_bytes(),b'foreign')

if __name__=='__main__':
 def deny(event,args):
  if event in ('socket.connect','socket.bind','socket.getaddrinfo'):raise RuntimeError('NETWORK DENIED')
 sys.addaudithook(deny);unittest.main(verbosity=2)
