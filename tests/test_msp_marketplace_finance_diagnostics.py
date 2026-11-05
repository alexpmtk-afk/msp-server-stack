import importlib.util,json,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class Diagnostics(unittest.TestCase):
 def load(self):
  spec=importlib.util.spec_from_file_location('finance_diagnostics',ROOT/'scripts/finance_control/diagnostics.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
 def test_failure_has_location_not_secret_exception_or_locals(self):
  d=self.load()
  try:
   token='NEVER_EXPORT_TOKEN';raise ValueError(token)
  except Exception as e:r=d.failure(e,'SELECT')
  raw=json.dumps(r);self.assertNotIn('NEVER_EXPORT_TOKEN',raw);self.assertEqual(r['error_type'],'ValueError');self.assertTrue(r['frames']);self.assertEqual(r['phase'],'SELECT')
 def test_read_only_probe_stops_at_first_failed_stage(self):
  d=self.load();calls=[]
  def bad():raise PermissionError('PRIVATE_TOKEN_IN_EXCEPTION')
  r=d.probe([('VERIFY',lambda:calls.append('verify')),('SELECT',bad),('NO_HTTP',lambda:calls.append('bad'))])
  self.assertEqual(calls,['verify']);self.assertEqual(r['status'],'HOLD');self.assertEqual(r['failure']['phase'],'SELECT');self.assertNotIn('PRIVATE_TOKEN',json.dumps(r))
 def test_publication_preserves_old_receipts_and_rejects_symlink(self):
  d=self.load()
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);old=root/'old.json';old.write_text('keep')
   d.publish(root,{'status':'HOLD'},uid=None);self.assertEqual(old.read_text(),'keep');self.assertEqual(json.loads((root/'diagnostics-latest.json').read_text())['status'],'HOLD')
   (root/'diagnostics-latest.json').unlink();(root/'diagnostics-latest.json').symlink_to(old)
   with self.assertRaises(ValueError):d.publish(root,{'status':'HOLD'},uid=None)
   self.assertEqual(old.read_text(),'keep')

class Upgrade(unittest.TestCase):
 def fixture(self,folder):
  import base64,hashlib,os
  spec=importlib.util.spec_from_file_location('diagnostic_upgrade',ROOT/'scripts/finance_control/upgrade.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  m.STATE=folder/'state';m.STATE.mkdir();(m.STATE/'controller.lock').touch();m.BACKUP=m.STATE/'upgrades/diagnostics-20261105'
  old=folder/'old';old.mkdir();new=folder/'new'
  oldfiles={'units/msp-finance-control.service':b'old-control','units/msp-finance-recover.service':b'old-recover'}
  newfiles={**oldfiles,'units/msp-finance-control.service':b'new-control','units/msp-finance-recover.service':b'new-recover','units/msp-finance-diagnostics.service':b'diagnostic-only','units/48-msp-finance-diagnostics.rules':b'start-only','diagnostics.py':b'# safe probe'}
  for n,b in oldfiles.items():p=old/n;p.parent.mkdir(exist_ok=True);p.write_bytes(b)
  m.OLD={'release':str(old),'payload_sha256':'old','hashes':{n:m.sha(b) for n,b in oldfiles.items()}}
  m.PACKAGE={'release':str(new),'payload_sha256':'new','files':{n:base64.b64encode(b).decode() for n,b in newfiles.items()},'hashes':{n:m.sha(b) for n,b in newfiles.items()}}
  original=m.wiring
  def wiring(*args):return {folder/'wiring'/str(p).lstrip('/'):(b,mode) for p,(b,mode) in original(*args).items()}
  m.wiring=wiring
  for p,(b,mode) in wiring(str(old),oldfiles,False).items():p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b);p.chmod(mode)
  # New parent locations are fixed administrative directories, not created by upgrade.
  for p in wiring(str(new),newfiles,True):p.parent.mkdir(parents=True,exist_ok=True)
  receipt=m.STATE/'INSTALL.json';receipt.write_text(json.dumps({'status':'INSTALLED_NOT_EXECUTED','release':str(old),'payload_sha256':'old'}));receipt.chmod(0o644)
  sentinel=folder/'archive-budget';sentinel.write_bytes(b'887 old rows, counters and all generations retained')
  def trusted(p,directory=False):
   p=Path(p)
   if p!=Path(m.__file__):self.assertTrue(p.is_relative_to(folder))
   self.assertFalse(p.is_symlink());self.assertTrue(p.exists())
  m.trusted=trusted;calls=[]
  def run(args):
   calls.append(args)
   if args[1]=='show':return b'inactive\n'
   return b''
  m.run=run
  return m,calls,sentinel
 def invoke(self,m,args):
  from unittest.mock import patch
  # Tests run the full installer transaction only inside the temporary fixture.
  # Real root trust and systemd integration are tested separately in hosted CI.
  with patch.object(m.os,'geteuid',return_value=0),patch.object(m.sys,'argv',['upgrade.py',*args]):m.main()
 def test_actual_transaction_idempotence_and_rollback_without_financial_start(self):
  with tempfile.TemporaryDirectory() as tmp:
   m,calls,sentinel=self.fixture(Path(tmp));prior=sentinel.read_bytes();self.invoke(m,[])
   self.assertEqual(json.loads((m.STATE/'INSTALL.json').read_text())['payload_sha256'],'new')
   self.assertEqual([a for a in calls if a[1]=='start'],[['/usr/bin/systemctl','start','msp-finance-diagnostics.service']])
   self.invoke(m,[])
   self.invoke(m,['--rollback'])
   self.assertEqual(json.loads((m.STATE/'INSTALL.json').read_text())['payload_sha256'],'old');self.assertEqual(sentinel.read_bytes(),prior)
 def test_live_drift_stops_before_any_write_or_unit_start(self):
  with tempfile.TemporaryDirectory() as tmp:
   folder=Path(tmp);m,calls,sentinel=self.fixture(folder);target=folder/'old/units/msp-finance-control.service';target.write_bytes(b'drift')
   before={str(p):p.read_bytes() for p in folder.rglob('*') if p.is_file()}
   with self.assertRaises(ValueError):self.invoke(m,[])
   after={str(p):p.read_bytes() for p in folder.rglob('*') if p.is_file()};self.assertEqual(before,after);self.assertFalse(any(a[1]=='start' for a in calls))

class ReadOnlyCompletedReceipt(unittest.TestCase):
 def test_completed_receipt_does_not_require_writable_archive_lock(self):
  import ast,base64,subprocess,sys,os
  # Isolated subprocess uses exact packaged code, never the installed archive.
  script=r'''
import ast,base64,sys,json,errno,os
from pathlib import Path
from unittest.mock import patch
bundle=Path(sys.argv[1]);folder=Path(sys.argv[2]);node=next(n for n in ast.parse(bundle.read_bytes()).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PACKAGE' for t in n.targets));p=ast.literal_eval(node.value)
for name,raw in p['files'].items():
 if name.startswith('apps/'):
  target=folder/'code'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(base64.b64decode(raw))
sys.path.insert(0,str(folder/'code'))
from apps.msp_marketplace_reports import standalone_wb as s
from apps.msp_marketplace_reports.finance_receipts import report_receipt
root=folder/'archive';root.mkdir();plan={'schema':1,'cabinet':'wb_laser_master','year':2026,'report_id':865431404,'report_type':1,'max_send_entries':3}
auth={'schema':1,'plan_sha256':s._digest(plan),'code_sha256':s.code_digest(),'archive_root':str(root),'expires_epoch':9999999999,'owner_api_pilot_authorized':True,'shared_quota_verified':True,'conflicting_clients_excluded':True,'evidence_reference':'OFFLINE_READ_ONLY_TEST'}
answers=iter([(200,[{'reportId':865431404,'reportType':1,'rrdId':5}]),(204,None)]);now=[1000.]
s.run_bounded(root,plan,auth,lambda:lambda req:next(answers),clock=lambda:now[0],sleep=lambda t:now.__setitem__(0,now[0]+t))
assert report_receipt(root,plan['cabinet'],2026,865431404,1)['verified']
before={str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}
real_open=os.open;write_attempts=[]
def readonly(path,flags,*args,**kwargs):
 if flags&(os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND):
  write_attempts.append(str(path));raise OSError(errno.EROFS,'Read-only file system')
 return real_open(path,flags,*args,**kwargs)
with patch.object(os,'open',readonly):result=report_receipt(root,plan['cabinet'],2026,865431404,1)
assert result['verified'],(result,write_attempts)
assert write_attempts==[],write_attempts
assert before=={str(p):p.read_bytes() for p in root.rglob('*') if p.is_file()}
print('READ_ONLY_COMPLETED_RECEIPT_PASS')
'''
  with tempfile.TemporaryDirectory() as tmp:
   p=subprocess.run([sys.executable,'-I','-B','-c',script,str(ROOT/'docs/marketplace-reports/autonomous-control-20261105/install.py'),tmp],capture_output=True,text=True)
   self.assertEqual(p.returncode,0,p.stderr);self.assertIn('READ_ONLY_COMPLETED_RECEIPT_PASS',p.stdout)
