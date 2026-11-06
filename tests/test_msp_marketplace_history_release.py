"""New history slice exercises unchanged accepted archive, discovery and budget."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from apps.msp_marketplace_reports import standalone_wb as s
from apps.msp_marketplace_reports.finance_receipts import report_receipt
from apps.msp_marketplace_reports.providers import WB_LIST
ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
 p=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(p);p.loader.exec_module(m);return m
w=load('history_worker','scripts/wb_history/worker.py')
l=load('history_launch','scripts/wb_history/launch.py')
class History(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR',str(ROOT)));self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.now=1000.;self.calls=[]
  self.pilot={'schema':1,'cabinet':'wb_laser_master','year':2026,'report_id':883801632,'report_type':1,'max_send_entries':3}
  rows=[{'reportId':883801632,'reportType':1,'rrdId':n} for n in range(1,842)]
  answers=iter([(200,rows),(204,None)])
  s.run_bounded(self.root,self.pilot,self.auth(self.pilot),lambda:lambda r:next(answers),clock=lambda:self.now,sleep=self.sleep)
  self.pilotbudget=self.root/'.wb-executor'/(s._digest(self.pilot)+'.json');self.original=self.pilotbudget.read_bytes()
 def sleep(self,t):self.now+=t
 def auth(self,plan):return {'schema':1,'plan_sha256':s._digest(plan),'code_sha256':s.code_digest(),'archive_root':str(self.root),'expires_epoch':9999999999,'owner_api_pilot_authorized':True,'shared_quota_verified':True,'conflicting_clients_excluded':True,'evidence_reference':'OFFLINE_TEST'}
 def factory(self,answers):
  it=iter(answers)
  def sender(req):
   assert not req.path.endswith('/883801632'),'completed pilot must never dispatch'
   self.calls.append(req);return next(it)
  return lambda:sender
 def execute(self,answers):return w.execute(self.root,self.auth(w.BATCH),self.factory(answers),clock=lambda:self.now,sleep=self.sleep)
 def inventory(self):return [{'reportId':883801632,'reportType':1,'dateFrom':'2026-10-19','dateTo':'2026-10-25'},{'reportId':883801636,'reportType':2,'dateFrom':'2026-10-19','dateTo':'2026-10-25'}]
 def test_list_then_full_type2_preserves_completed_report_and_budget(self):
  result=self.execute([(200,self.inventory()),(200,[{'reportId':883801636,'reportType':2,'rrdId':1}]),(204,None)])
  self.assertTrue(result['report_detail_complete']);self.assertEqual(result['receipt']['rows'],1)
  self.assertEqual([r.path for r in self.calls],[WB_LIST,'/api/finance/v1/sales-reports/detailed/883801636','/api/finance/v1/sales-reports/detailed/883801636'])
  self.assertEqual(self.original,self.pilotbudget.read_bytes());self.assertEqual(report_receipt(self.root,'wb_laser_master',2026,883801632,1)['rows'],841)
  self.calls=[];again=self.execute([]);self.assertTrue(again['report_detail_complete']);self.assertEqual(self.calls,[])
 def test_missing_confirmed_report_never_substitutes_another(self):
  with self.assertRaisesRegex(ValueError,'not confirmed'):self.execute([(200,self.inventory()[:1])])
  self.assertEqual(len(self.calls),1);self.assertEqual(self.original,self.pilotbudget.read_bytes())
 def test_three_detail_entries_pause_and_repeat_does_not_reset(self):
  rows=lambda n:[{'reportId':883801636,'reportType':2,'rrdId':n}]
  result=self.execute([(200,self.inventory()),(200,rows(1)),(200,rows(2)),(200,rows(3))])
  self.assertEqual(result['executor']['status'],'PAUSED_BUDGET');self.assertFalse(result['report_detail_complete']);self.assertEqual(len(self.calls),4)
  self.calls=[];again=self.execute([]);self.assertEqual(again['executor']['send_entries'],3);self.assertEqual(self.calls,[])
 def test_discovery429_wait_is_preserved_with_bounded_deadline(self):
  from apps.msp_marketplace_reports.quota import QuotaBusy
  def factory():
   def send(req):raise QuotaBusy(600,'offline synthetic')
   return send
  result=w.execute(self.root,self.auth(w.BATCH),factory,clock=lambda:self.now,sleep=self.sleep,max_seconds=30)
  self.assertFalse(result['report_detail_complete']);self.assertEqual(self.original,self.pilotbudget.read_bytes())
 def test_wrong_batch_authorization_prevents_factory(self):
  auth=self.auth(w.DETAIL)
  with self.assertRaises(s.PilotBlocked):w.execute(self.root,auth,lambda:(_ for _ in ()).throw(AssertionError('no sender')),clock=lambda:self.now,sleep=self.sleep)
 def test_corrupt_completed_pilot_stops_before_new_requests(self):
  page=next((self.root/'.wb-report-stage/wb_laser_master/2026/883801632-type-1').glob('page-*.json'));page.write_bytes(b'corrupt')
  with self.assertRaisesRegex(ValueError,'reconciliation'):self.execute([])
  self.assertEqual(self.calls,[])
 def test_nonroot_installer_stops_before_setup(self):
  with patch.object(os,'geteuid',return_value=1001),patch.object(l,'setup',side_effect=AssertionError('no setup')):self.assertEqual(l.main(),2)

class ReleaseFiles(unittest.TestCase):
 def test_manifest_accepted_files_are_identical_new_modules_present_and_templates_inert(self):
  folder=ROOT/'docs/marketplace-reports/history-first-20261103';manifest=json.loads((folder/'MANIFEST.json').read_text())
  artifact=load('history_built','docs/marketplace-reports/history-first-20261103/history.py')
  import base64
  files={n:base64.b64decode(v) for n,v in artifact.PACKAGE['files'].items()}
  accepted=json.loads((ROOT/'docs/marketplace-reports/deployment/autonomous-wb/INSTALL_MANIFEST.json').read_text())['files']
  # Frozen PR117 bundle is pinned to its own bytes, not newer source modules.
  frozen={Path(n).name:hashlib.sha256(b).hexdigest() for n,b in files.items() if n.startswith('apps/') and n.endswith('.py')}
  self.assertEqual(artifact.PACKAGE['accepted_assets']['app_code_sha256'],s._digest(frozen))
  for n,h in accepted.items():self.assertEqual(hashlib.sha256(files[n]).hexdigest(),h)
  for n in ['wb_discovery_resume.py','finance_receipts.py','finance_refresh_plan.py','wb_report_revision.py','ozon_connection_plan.py']:self.assertIn('apps/msp_marketplace_reports/'+n,files)
  self.assertEqual(manifest['schedule'],'DISABLED');self.assertEqual(hashlib.sha256((folder/'history.py').read_bytes()).hexdigest(),manifest['launcher_sha256'])
 def test_unsafe_member_rejected_before_writes(self):
  import base64,types
  with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR',str(ROOT))) as d:
   root=Path(d)/'target';raw=b'bad';package={'release':str(root),'files':{'../escape':base64.b64encode(raw).decode()},'hashes':{'../escape':hashlib.sha256(raw).hexdigest()}}
   with patch.object(l,'PACKAGE',package),self.assertRaisesRegex(ValueError,'unsafe'):l.install_release(types.SimpleNamespace(parents=lambda p:None))
   self.assertFalse(root.exists())

class ImmutableInstall(unittest.TestCase):
 def test_exclusive_install_reuse_and_drift_preserve_other_files(self):
  import types,base64
  with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR',str(ROOT))) as d:
   parent=Path(d);root=parent/'release';other=parent/'archive';other.write_bytes(b'never change')
   payload={'apps/msp_marketplace_reports/test.py':b'pass\n','worker.py':b'pass\n'}
   package={'release':str(root),'files':{n:base64.b64encode(v).decode() for n,v in payload.items()},'hashes':{n:hashlib.sha256(v).hexdigest() for n,v in payload.items()}}
   def trusted(p,mode=None):
    self.assertFalse(p.is_symlink())
    if mode is not None:self.assertEqual(p.stat().st_mode&0o777,mode)
   def write(p,raw,mode):
    fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY,mode)
    try:os.write(fd,raw);os.fchmod(fd,mode);os.fsync(fd)
    finally:os.close(fd)
   core=types.SimpleNamespace(parents=lambda p:None,trusted=trusted,write_new=write,syncdir=lambda p:None)
   old_umask=os.umask(0o077)
   try:
    with patch.object(l,'PACKAGE',package):
     l.install_release(core);l.install_release(core)
     self.assertEqual((root/'worker.py').stat().st_mode&0o777,0o644)
     (root/'worker.py').write_bytes(b'drift')
     with self.assertRaisesRegex(ValueError,'drift'):l.install_release(core)
     self.assertEqual((root/'worker.py').read_bytes(),b'drift')
   finally:os.umask(old_umask)
   self.assertEqual(other.read_bytes(),b'never change')
 def test_partial_staging_is_not_removed_or_overwritten(self):
  import types
  with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR',str(ROOT))) as d:
   root=Path(d)/'target';partial=root.with_name('target.staging');partial.mkdir();(partial/'evidence').write_bytes(b'keep')
   with patch.object(l,'PACKAGE',{'release':str(root),'files':{},'hashes':{}}),self.assertRaisesRegex(ValueError,'partial'):
    l.install_release(types.SimpleNamespace(parents=lambda p:None))
   self.assertEqual((partial/'evidence').read_bytes(),b'keep')

class HTTPAudit(unittest.TestCase):
 def test_real_opener_boundary_records_no_tokens_and_denies_completed_report(self):
  import urllib.request,types
  with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR',str(ROOT))) as d:
   journal=Path(d)/'events';calls=[]
   inner=types.SimpleNamespace(open=lambda req,timeout:(calls.append(1) or types.SimpleNamespace(status=200)))
   opener=w.AuditedOpener(inner,journal)
   req=urllib.request.Request('https://finance-api.wildberries.ru/api/finance/v1/sales-reports/list',data=b'{}',headers={'Authorization':'test-only-private-value'},method='POST')
   opener.open(req,60);self.assertEqual(len(w.events(journal)),2);self.assertNotIn('test-only-private-value',journal.read_text())
   req=urllib.request.Request('https://finance-api.wildberries.ru/api/finance/v1/sales-reports/detailed/883801632',data=b'{}',method='POST')
   with self.assertRaises(ValueError):opener.open(req,60)
   self.assertEqual(calls,[1])

class EvidenceReconciliation(unittest.TestCase):
 def test_http_history_without_original_budget_refuses_fresh_execution(self):
  with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR',str(ROOT))) as d:
   with self.assertRaises(FileNotFoundError):w.reconcile_events(Path(d),[{'event':'HTTP_DISPATCH_ATTEMPT','method_scope':'detail'}])
   self.assertEqual(list(Path(d).iterdir()),[])
