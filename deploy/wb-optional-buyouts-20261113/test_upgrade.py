import os,sys,tempfile,unittest,json,fcntl,io,contextlib
from pathlib import Path
from unittest.mock import patch
P=Path(os.environ.get('WB_TEST_PAYLOAD',Path(__file__).parent/'payload'));sys.path.insert(0,str(P))
import upgrade_root as u
class UpgradeTests(unittest.TestCase):
 def test_nonroot_refuses_before_payload_or_state_read(self):
  with patch.object(u.r,'verify_payload',side_effect=AssertionError('NO PRIVILEGED READ')),self.assertRaises(PermissionError):u.main()
 def test_pause_never_stops_shared_worker_or_resets_sources(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
   root=Path(t);(root/'runs').mkdir();old=root/'old';old.mkdir();calls=[]
   def state(unit):
    if unit==u.UNIT:return {'ActiveState':'inactive'}
    return dict(ActiveState='inactive',PrivateNetwork='yes',DropInPaths='')
   with patch.object(u,'BASE',root),patch.object(u,'state',side_effect=state),patch.object(u.r,'run',side_effect=lambda cmd,**kwargs:calls.append(cmd)):
    u.pause_and_close(old)
   self.assertEqual(calls,[['/usr/bin/systemctl','stop','--no-block',u.UNIT]])
   self.assertEqual(list((root/'runs').iterdir()),[])
 def test_foreign_live_worker_is_not_stopped_or_cleaned(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
   root=Path(t);(root/'runs').mkdir();calls=[]
   def state(unit):return {'ActiveState':'inactive'} if unit==u.UNIT else {'ActiveState':'active','DropInPaths':'/foreign/drop.conf'}
   with patch.object(u,'BASE',root),patch.object(u,'state',side_effect=state),patch.object(u.r,'run',side_effect=lambda cmd,**kwargs:calls.append(cmd)),patch.object(u,'old_controller',side_effect=AssertionError('NO FOREIGN CLEANUP')),self.assertRaises(ValueError):u.pause_and_close(root)
   self.assertEqual(calls,[['/usr/bin/systemctl','stop','--no-block',u.UNIT]])
 def test_owned_live_worker_is_allowed_to_exit_itself(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
   root=Path(t);(root/'runs').mkdir();worker_calls=[dict(ActiveState='active',DropInPaths=str(u.DROP)),dict(ActiveState='inactive',PrivateNetwork='yes',DropInPaths=''),dict(ActiveState='inactive',PrivateNetwork='yes',DropInPaths='')];calls=[]
   def state(unit):return {'ActiveState':'inactive'} if unit==u.UNIT else worker_calls.pop(0)
   with patch.object(u,'BASE',root),patch.object(u,'state',side_effect=state),patch.object(u.time,'sleep'),patch.object(u.r,'run',side_effect=lambda cmd,**kwargs:calls.append(cmd)):u.pause_and_close(root)
   self.assertEqual(len(calls),1)
 def test_unexplained_orphan_credentials_are_not_deleted(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
   root=Path(t);(root/'runs').mkdir();p=root/'cabinets.json';p.write_text('fixture')
   def state(unit):return {'ActiveState':'inactive'} if unit==u.UNIT else dict(ActiveState='inactive',PrivateNetwork='yes',DropInPaths='')
   with patch.object(u,'BASE',root),patch.object(u,'state',side_effect=state),patch.object(u.r,'run'),self.assertRaises(ValueError):u.pause_and_close(root)
   self.assertEqual(p.read_text(),'fixture')
class TransactionTests(unittest.TestCase):
 def test_exact_transaction_preserves_state_and_releases_locks_before_start(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
   root=Path(t);base=root/'state';base.mkdir();(base/'controller.lock').touch();(base/'runs').mkdir();evidence=base/'runs/retained';evidence.write_text('nonce-and-source-journal');candidate=root/'candidate';candidate.mkdir();old=root/'old';old.mkdir();unitdir=root/'units';unitdir.mkdir();finance=root/'finance.lock';finance.touch();(candidate/'MANIFEST.json').write_text('{}');(old/'controller.py').write_text('# accepted old source')
   pins={'controller.py':u.r.sha((old/'controller.py').read_bytes())};(old/'MANIFEST.json').write_text(json.dumps(pins));unit=unitdir/u.UNIT;unit.write_text('ExecStart=/usr/bin/python3 -I -B '+str(old/'controller.py')+'\n');installation=base/'installation.json';installation.write_text(json.dumps(dict(status='INSTALLED',root_release=str(old),time_moscow='08:45')));schedule=base/'schedule.json';schedule.write_text(json.dumps(dict(root_release=str(old),time='08:45',not_before_epoch=1794635100)))
   b=dict(old_root=str(old),old_manifest_sha256=u.r.sha((old/'MANIFEST.json').read_bytes()),files={str(p):u.r.sha(p.read_bytes()) for p in (unit,installation,schedule)},changed_files=[str(unit),str(installation),str(schedule)]);(candidate/'upgrade-baseline.json').write_text(json.dumps(b));calls=[]
   def save(path,raw,mode=0o600,gid=0):
    with path.open('xb') as f:f.write(raw)
    path.chmod(mode)
   def state(name):
    if name==u.r.SERVICE:return dict(ActiveState='inactive',PrivateNetwork='yes',DropInPaths='')
    if name.endswith('.timer'):return dict(ActiveState='active',UnitFileState='enabled')
    return dict(ActiveState='active',ExecStart=unit.read_text())
   def run(args,**kwargs):
    calls.append(args)
    if args[:3]==['/usr/bin/systemctl','start','--no-block']:
     for p in (finance,base/'controller.lock'):
      with p.open('rb') as f:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
    return b''
   with patch.object(u,'ROOT',candidate),patch.object(u,'BASE',base),patch.object(u,'PUBLIC',base/'upgrade.json'),patch.object(u,'UNIT_DIR',unitdir),patch.object(u,'FINANCE',finance),patch.object(u.os,'geteuid',return_value=0),patch.object(u.r,'verify_payload'),patch.object(u.r,'validate_platform'),patch.object(u.r,'trust'),patch.object(u.r,'save',side_effect=save),patch.object(u,'state',side_effect=state),patch.object(u,'pause_and_close'),patch.object(u.r,'run',side_effect=run),contextlib.redirect_stdout(io.StringIO()):
    u.main();first_calls=len(calls);u.main();self.assertEqual(len(calls),first_calls)
   self.assertEqual(json.loads(installation.read_bytes())['optional_buyout_policy'],u.RULE);self.assertEqual(json.loads(schedule.read_bytes())['not_before_epoch'],1794635100);self.assertEqual(evidence.read_text(),'nonce-and-source-journal');self.assertIn(str(candidate/'controller.py'),unit.read_text());self.assertTrue(list(base.glob('optional-policy-backups-*')))
if __name__=='__main__':unittest.main()
