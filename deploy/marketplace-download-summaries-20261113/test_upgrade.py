import contextlib,hashlib,io,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
P=Path(os.environ.get('MP_TEST_PAYLOAD',Path(__file__).parent/'payload'));sys.path.insert(0,str(P))
import summary_upgrade as u
class UpgradeTests(unittest.TestCase):
 def fixture(self,tmp):
  root=Path(tmp);candidate=root/'candidate';candidate.mkdir();(candidate/'MANIFEST.json').write_text('{}');unitdir=root/'units';unitdir.mkdir();wb=root/'wb';wb.mkdir();oz=root/'oz';oz.mkdir();base=root/'notice';finance=root/'finance';finance.touch();oldwb=root/'oldwb';oldwb.mkdir();oldoz=root/'oldoz';oldoz.mkdir();files=[]
  for old in (oldwb,oldoz):
   (old/'controller.py').write_text('# accepted');(old/'MANIFEST.json').write_text(json.dumps({'controller.py':u.r.sha((old/'controller.py').read_bytes())}))
  for current,old,name in ((wb,oldwb,'msp-wb-daily-weekly.service'),(oz,oldoz,'msp-ozon-daily.service')):
   (current/'controller.lock').touch()
   for n in ('installation.json','schedule.json'):
    p=current/n;p.write_text(json.dumps(dict(root_release=str(old),time='08:45' if current==wb else '08:40')));files.append(p)
   p=unitdir/name;p.write_text('ExecStart=/usr/bin/python3 '+str(old/'controller.py')+'\n');files.append(p)
  cfg=dict(old_wb_root=str(oldwb),old_ozon_root=str(oldoz),old_wb_manifest=u.r.sha((oldwb/'MANIFEST.json').read_bytes()),old_ozon_manifest=u.r.sha((oldoz/'MANIFEST.json').read_bytes()),files={str(p):u.r.sha(p.read_bytes()) for p in files})
  (candidate/'summary-upgrade-baseline.json').write_text(json.dumps(cfg));return candidate,unitdir,wb,oz,base,finance,files
 def execute(self,tmp,fail_ready=False,drift=False,repeat=False,orphan=False):
  candidate,unitdir,wb,oz,base,finance,files=self.fixture(tmp);calls=[];started=False
  if drift:files[0].write_text('drift')
  if orphan:(Path(tmp)/'oldwb/cabinets.json').write_text('fixture, not a credential')
  def state(name):
   if name==u.NEWUNIT:return dict(ActiveState='failed' if fail_ready else 'active',MainPID='99',ExecStart=str(candidate/'notices/controller.py'))
   if name==u.r.SERVICE:return dict(ActiveState='inactive',PrivateNetwork='yes',DropInPaths='')
   return dict(ActiveState='inactive',ExecStart=(unitdir/name).read_text())
  def save(p,raw,mode=0o600,gid=0):p.write_bytes(raw);p.chmod(mode)
  def run(args,**kw):
   calls.append(args)
   if args[:3]==['/usr/bin/systemctl','enable','--now']:
    self.assertFalse(json.loads((wb/'schedule.json').read_text())['consolidated_notices']);self.assertFalse(json.loads((oz/'schedule.json').read_text())['consolidated_notices'])
   if args[0]=='/usr/sbin/runuser' and args[-1].endswith('cleanup_cli.py'):return b'{"status":"VERIFIED"}'
   if args[:2]==['/usr/bin/systemctl','show']:return b'ActiveState=active\nUnitFileState=enabled\n'
   return b''
  with patch.object(u,'ROOT',candidate),patch.object(u,'UNITDIR',unitdir),patch.object(u,'WB',wb),patch.object(u,'OZ',oz),patch.object(u,'BASE',base),patch.object(u,'FINANCE',finance),patch.object(u.os,'geteuid',return_value=0),patch.object(u.r,'trust'),patch.object(u.r,'verify_payload'),patch.object(u.r,'validate_platform'),patch.object(u.r,'save',side_effect=save),patch.object(u,'state',side_effect=state),patch.object(u.r,'run',side_effect=run),contextlib.redirect_stdout(io.StringIO()):
   if drift or orphan:
    with self.assertRaises(ValueError):u.main()
    self.assertFalse(base.exists());return
   if fail_ready:
    with self.assertRaises(ValueError):u.main()
    self.assertFalse(json.loads((wb/'schedule.json').read_text())['consolidated_notices']);self.assertFalse((base/'installation.json').exists());return
   u.main();self.assertTrue(json.loads((wb/'schedule.json').read_text())['consolidated_notices']);self.assertTrue(json.loads((oz/'schedule.json').read_text())['consolidated_notices']);self.assertEqual(json.loads((base/'installation.json').read_text())['status'],'INSTALLED')
   self.assertFalse(any(a[:2]==['/usr/bin/systemctl','stop'] for a in calls));self.assertFalse(any('timer' in arg for call in calls for arg in call if call[:2]!=['/usr/bin/systemctl','show']))
   if repeat:
    before=len(calls);u.main();self.assertEqual(len(calls),before)
 def test_transaction_flags_only_after_notifier_ready(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:self.execute(t)
 def test_failed_notifier_preserves_old_alerts(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:self.execute(t,fail_ready=True)
 def test_drift_refused_before_writes(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:self.execute(t,drift=True)
 def test_verified_repeat_no_additional_side_effects(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:self.execute(t,repeat=True)
 def test_unreconciled_source_artifact_is_preserved_before_writes(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
   self.execute(t,orphan=True);self.assertTrue((Path(t)/'oldwb/cabinets.json').exists())
if __name__=='__main__':unittest.main()
