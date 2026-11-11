import sys,unittest,json,tempfile,os,io,urllib.error
from pathlib import Path
from datetime import date
from unittest.mock import patch
ROOT=Path(__file__).parent
sys.path.insert(0,str(ROOT/'payload'))
from apps.msp_marketplace_reports import ozon_accruals as a
import capture_worker as w
import capture_root as c
import start_root as s
import root_common as r

def row(**extra):return {'accrual_id':9007199254740993,'date':'2026-01-15','accrued_category':'NON_ITEM','non_item_fee':{'type_id':123,'accrued':{'amount':'-15.50','currency':'RUB'}},'total_amount':{'amount':'-15.50','currency':'RUB'},**extra}
def raw(rows,cursor=''):return json.dumps({'accruals':rows,'last_id':cursor}).encode()
class ReaderTests(unittest.TestCase):
 def test_closed_plan_permanent_all_912_dates(self):
  plan=a.closed_history(date(2026,11,11));self.assertEqual(len(plan),30);self.assertEqual(sum(len(p['days']) for p in plan),912)
  self.assertEqual({p['cabinet'] for p in plan},set(a.CABINETS));self.assertTrue(all(p['dataset']=='ozon_financial_accruals' for p in plan))
 def test_november_rejected(self):
  with self.assertRaises(ValueError):a.request_body('2026-11-01')
 def test_wrong_request_date_rejected(self):
  for d in ['2026-01-1','2025-12-31','2026-02-30']:
   with self.assertRaises(ValueError):a.request_body(d)
 def test_categories_retained(self):
  for cat in [*a.CATEGORIES,'FUTURE_CATEGORY']:
   item=row(accrued_category=cat);parsed=a.inspect_page(raw([item]),'2026-01-15');self.assertEqual(parsed['rows'],[item]);self.assertFalse(parsed['provider_coverage_verified'])
 def test_unknown_nested_field_retained(self):
  item=row(new_branch={'x':'future'});self.assertEqual(a.inspect_page(raw([item]),'2026-01-15')['rows'][0],item)
 def test_explicit_empty_cursor_not_complete(self):
  p=a.inspect_page(raw([]),'2026-01-15');self.assertEqual(p['status'],'CURSOR_EXHAUSTED_UNRECONCILED');self.assertFalse(p['provider_coverage_verified'])
 def test_missing_cursor_not_terminal(self):
  with self.assertRaises(ValueError):a.inspect_page(b'{"accruals":[]}','2026-01-15')
 def test_null_cursor_not_terminal(self):
  with self.assertRaises(ValueError):a.inspect_page(raw([],None),'2026-01-15')
 def test_duplicate_json_keys_rejected(self):
  with self.assertRaises(ValueError):a.inspect_page(b'{"last_id":"","last_id":"x","accruals":[]}','2026-01-15')
 def test_false_identifier_rejected(self):
  with self.assertRaises(ValueError):a.inspect_page(raw([row(accrual_id=True)]),'2026-01-15')
 def test_precision_id_preserved(self):
  p=a.inspect_page(raw([row()]),'2026-01-15');self.assertIn('9007199254740993',p['seen'])
 def test_identical_duplicate_retained_once(self):
  p=a.inspect_page(raw([row(),row()]),'2026-01-15');self.assertEqual(len(p['rows']),1);self.assertEqual(p['identical_duplicates'],1)
 def test_conflicting_duplicate_rejected(self):
  with self.assertRaises(ValueError):a.inspect_page(raw([row(),row(unit_number='changed')]),'2026-01-15')
 def test_wrong_day_rejected(self):
  with self.assertRaises(ValueError):a.inspect_page(raw([row(date='2026-01-14')]),'2026-01-15')
 def test_cursor_cycle_rejected(self):
  with self.assertRaises(ValueError):a.inspect_page(raw([row()],'again'),'2026-01-15',input_cursor='again')
 def test_cursor_ttl_prevents_silent_restart(self):
  p=a.inspect_page(raw([row()],'opaque'),'2026-01-15')
  self.assertEqual(a.next_request(p,'2026-01-15',age_seconds=10)['last_id'],'opaque')
  with self.assertRaises(ValueError):a.next_request(p,'2026-01-15',age_seconds=900)
 def test_empty_page_with_cursor_holds(self):
  p=a.inspect_page(raw([],'opaque'),'2026-01-15')
  with self.assertRaises(ValueError):a.next_request(p,'2026-01-15',age_seconds=1)
 def test_negative_money_and_currency(self):
  leaves=a.money_leaves(row(),{123:{'description':'Example fee'}});self.assertEqual(len(leaves),2);self.assertTrue(all(x['amount']=='-15.50' for x in leaves));self.assertTrue(all(x['aggregation'].startswith('DO_NOT_SUM') for x in leaves))
 def test_nonfinite_money_rejected(self):
  with self.assertRaises(ValueError):a.money({'amount':'NaN','currency':'RUB'})
 def test_unknown_fee_not_discarded(self):
  leaf=a.money_leaves(row(),{})[0];self.assertEqual(leaf['type_id'],123);self.assertFalse(leaf['type_known'])
 def test_types_duplicates_rejected(self):
  item={'id':123,'name':'X','description':'Y'}
  with self.assertRaises(ValueError):a.types_catalog({'accrual_types':[item,item]})

class CaptureTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=ROOT);self.addCleanup(self.tmp.cleanup);self.state=Path(self.tmp.name)
  self.patch=patch.object(w,'STATE',self.state);self.patch.start();self.addCleanup(self.patch.stop)
 def test_import_and_nonroot_do_not_activate(self):
  with patch.object(s.os,'geteuid',return_value=1001),patch.object(c,'preflight') as pf:
   with self.assertRaises(PermissionError):s.main()
   pf.assert_not_called()
 def test_quota_busy_consumes_no_sender_entry(self):
  with patch.object(w.CaptureQuota,'reserve',side_effect=w.q.QuotaBusy(60)):
   with self.assertRaises(w.q.QuotaBusy):w.capture_one(1,w.CALLS[0][0],{},'types',{})
  self.assertFalse(list(self.state.iterdir()))
 def test_unknown_outcome_never_retried(self):
  def factory():
   class Opener:
    def open(self,*args,**kwargs):raise TimeoutError()
   return Opener()
  with patch.object(w.CaptureQuota,'reserve',return_value=[]),patch.object(w,'_headers',return_value={}):
   with self.assertRaises(TimeoutError):w.capture_one(1,w.CALLS[0][0],{},'types',{},factory=factory)
   with self.assertRaises(ValueError):w.capture_one(1,w.CALLS[0][0],{},'types',{},factory=factory)
  self.assertTrue((self.state/'types.entry.json').exists())
 def test_invalid_json_raw_saved_before_parser(self):
  class Response:
   status=200
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def read(self,n):return b'{not json'
  class Opener:
   def open(self,*args,**kwargs):return Response()
  with patch.object(w.CaptureQuota,'reserve',return_value=[]),patch.object(w,'_headers',return_value={}):
   actual=w.capture_one(1,w.CALLS[0][0],{},'types',{},factory=Opener)
  self.assertEqual((self.state/'types.response.json').read_bytes(),actual)
  with self.assertRaises(ValueError):a.strict_json(actual)
 def test_full_two_read_capture_has_no_coverage_claim(self):
  types=json.dumps({'accrual_types':[{'id':123,'name':'fixture','description':'Example fee'}]}).encode()
  replies=iter([types,raw([row()])])
  class Response:
   status=200
   def __init__(self,data):self.data=data
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def read(self,n):return self.data
  class Opener:
   def open(self,*args,**kwargs):return Response(next(replies))
  job={'cabinet':w.CABINET,'date':w.DAY,'max_send_entries':2,'nonce':'a'*32}
  with patch.object(w,'check_job',return_value=job),patch.object(w,'load_credentials',return_value={w.CABINET:{}}),patch.dict(os.environ,{'CREDENTIALS_DIRECTORY':str(self.state)}),patch.object(w.CaptureQuota,'reserve',return_value=[]),patch.object(w,'_headers',return_value={}),patch.object(w.urllib.request,'build_opener',return_value=Opener()),patch.object(w.time,'sleep'):
   result=w.execute()
  self.assertEqual(result['status'],'CAPTURED_NOT_RECONCILED');self.assertFalse(result['full_day_complete']);self.assertEqual(len(list(self.state.glob('*.entry.json'))),2);self.assertEqual(len(list(self.state.glob('*.response.json'))),2)
 def test_http_error_retained_and_no_retry(self):
  class Opener:
   def open(self,*args,**kwargs):raise urllib.error.HTTPError('https://example.invalid',403,'forbidden',{},io.BytesIO(b'error-fixture'))
  with patch.object(w.CaptureQuota,'reserve',return_value=[]),patch.object(w,'_headers',return_value={}):
   with self.assertRaises(ValueError):w.capture_one(1,w.CALLS[0][0],{},'types',{},factory=Opener)
  self.assertEqual((self.state/'types.response.json').read_bytes(),b'error-fixture')
 def test_quota_rejects_other_endpoint(self):
  with self.assertRaises(ValueError):w.CaptureQuota('ozon',{}).reserve(w.Request('ozon','/v1/finance/realization/posting',{}))
 def test_unit_rebinds_conditions_and_minimal_credentials(self):
  text=c.unit_text(['127.0.0.1/32']).decode();self.assertIn('ConditionPathExists=\nConditionPathIsDirectory=',text);self.assertIn('LoadCredential=\nLoadCredential=cabinets.json:',text);self.assertNotIn('MSP_REPORTS_OZON_FINANCE_METHODS_VERIFIED',text)
 def test_foreign_activation_not_removed(self):
  ledger=self.state/'ledger';ledger.mkdir();drop=self.state/'drop';drop.write_bytes(b'foreign');(ledger/'activation.json').write_text(json.dumps({'drop_sha256':r.sha(b'owned'),'credential_sha256':'x'}))
  with patch.object(c,'LEDGER',ledger),patch.object(r,'DROP',drop),patch.object(r,'trust'),patch.object(r,'run') as run:
   with self.assertRaises(ValueError):c.cleanup_owned()
   run.assert_not_called();self.assertEqual(drop.read_bytes(),b'foreign')
 def test_cleanup_restores_before_credential_removal(self):
  ledger=self.state/'ledger';ledger.mkdir();(ledger/'activation.json').write_text(json.dumps({'drop_sha256':'x','credential_sha256':r.sha(b'fixture')}));cred=self.state/'cabinets.json';cred.write_bytes(b'fixture')
  with patch.object(c,'LEDGER',ledger),patch.object(c,'ROOT',self.state),patch.object(r,'DROP',self.state/'absent'),patch.object(r,'trust'),patch.object(r,'show',return_value={'PrivateNetwork':'no','DropInPaths':'','ActiveState':'inactive'}):
   with self.assertRaises(ValueError):c.cleanup_owned()
  self.assertTrue(cred.exists())

class PackageTests(unittest.TestCase):
 def test_exact_archive_and_manifest(self):
  import tarfile,hashlib
  receipt=json.loads((ROOT/'package-receipt.json').read_text());blob=(ROOT/'ozon-accrual.tar.gz').read_bytes();self.assertEqual(hashlib.sha256(blob).hexdigest(),receipt['archive_sha256'])
  with tarfile.open(fileobj=io.BytesIO(blob),mode='r:gz') as archive:
   members=archive.getmembers();self.assertEqual(len(members),len({m.name for m in members}));self.assertTrue(all(m.isfile() and m.mode==0o644 and not Path(m.name).is_absolute() and '..' not in Path(m.name).parts for m in members));files={m.name:archive.extractfile(m).read() for m in members}
  manifest=json.loads(files['MANIFEST.json']);self.assertEqual(hashlib.sha256(files['MANIFEST.json']).hexdigest(),receipt['manifest_sha256']);self.assertEqual(set(files),set(manifest)|{'MANIFEST.json'})
  for n,h in manifest.items():self.assertEqual(hashlib.sha256(files[n]).hexdigest(),h)
 def test_bootstrap_nonroot_refuses_before_staging(self):
  with patch.object(os,'geteuid',return_value=1001),patch.object(tempfile,'mkdtemp') as mk:
   with self.assertRaises(AssertionError):exec(compile((ROOT/'launch_verified.py').read_text(),'launcher','exec'),{})
   mk.assert_not_called()
 def test_bootstrap_tamper_refuses_before_execution(self):
  import hashlib
  with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
   tmp=Path(tmp);stage=tmp/'stage';stage.mkdir();bad=tmp/'bad.tar.gz';bad.write_bytes(b'corrupt')
   text=(ROOT/'launch_verified.py').read_text().replace(repr(str(ROOT/'ozon-accrual.tar.gz')),repr(str(bad)))
   with patch.object(os,'geteuid',return_value=0),patch.object(tempfile,'mkdtemp',return_value=str(stage)),patch('subprocess.run') as run:
    old=os.umask(0o077)
    try:
     with self.assertRaises(AssertionError):exec(compile(text,'launcher','exec'),{})
    finally:os.umask(old)
    run.assert_not_called()
 def test_one_line_command_digest(self):
  import hashlib,subprocess
  cmd=(ROOT/'ROOT_OZON_ACCRUAL.txt').read_bytes();self.assertEqual(len(cmd.splitlines()),1);self.assertEqual(hashlib.sha256(cmd).hexdigest(),json.loads((ROOT/'package-receipt.json').read_text())['command_sha256'])
  subprocess.run(['bash','-n','-c',cmd.decode()],check=True)

if __name__=='__main__':
 def deny(event,args):
  if event in ('socket.connect','socket.bind','socket.getaddrinfo'):raise RuntimeError('NETWORK DENIED IN TESTS')
 sys.addaudithook(deny)
 unittest.main(verbosity=2)
