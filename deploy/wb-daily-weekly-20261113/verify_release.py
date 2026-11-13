"""Exercise the actual frozen payload, not a checkout or installed modules."""
import hashlib,io,json,os,re,subprocess,tarfile,tempfile
from pathlib import Path
B=Path(__file__).resolve().parent;sha=lambda raw:hashlib.sha256(raw).hexdigest()
subprocess.run(['python3',str(B/'build.py')],check=True)
receipt=json.loads((B/'package-receipt.json').read_bytes());raw=(B/'wb-daily-weekly.tar.gz').read_bytes();assert sha(raw)==receipt['archive_sha256']
command=(B/'ROOT_WB_DAILY.txt').read_bytes();assert len(command.splitlines())==1 and sha(command)==receipt['command_sha256'];assert sha((B/'launch_verified.py').read_bytes())==receipt['launcher_sha256']
subprocess.run(['bash','-n','-c',command.decode()],check=True)
results=[]
with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
 stage=Path(t);names=[]
 with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as tar:
  for m in tar:
   assert m.isfile() and m.mode==0o644 and not Path(m.name).is_absolute() and '..' not in Path(m.name).parts and m.name not in names
   names.append(m.name);p=stage/m.name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(tar.extractfile(m).read())
 for sub in ('','ozon'):
  folder=stage/sub;manifest=json.loads((folder/'MANIFEST.json').read_bytes());assert all(sha((folder/name).read_bytes())==pin for name,pin in manifest.items())
 assert set(names)==set(json.loads((stage/'MANIFEST.json').read_bytes()))|{'MANIFEST.json'}
 for exe,label in [('python3','3.14'),('/usr/bin/python3','3.12')]:
  for kind,folder,script,count,envvar in [('wb',stage,B/'test_wb.py',35,'WB_TEST_PAYLOAD'),('ozon',stage/'ozon',B.parent/'ozon-daily-wait-20261113/test_v2.py',22,'DAILY_TEST_PAYLOAD')]:
   code="import sys,os,pathlib,runpy\ndef deny(e,a):\n if e in ('socket.connect','socket.bind','socket.getaddrinfo'):raise AssertionError('No live network in release tests')\nsys.addaudithook(deny)\nos.environ["+repr(envvar)+"]="+repr(str(folder))+"\nsys.argv=['test_release.py']\ntry:runpy.run_path("+repr(str(script))+",run_name='__main__')\nexcept SystemExit as e:assert e.code==0\n"
   code+="mods=[m for n,m in sys.modules.items() if n in ('controller','start_root','root_common','recovery','worker','catalog','plan','notify','capture_worker') or n.startswith('apps.')]\nassert mods and all(pathlib.Path(m.__file__).resolve().is_relative_to(pathlib.Path("+repr(str(folder))+")) for m in mods if getattr(m,'__file__',None));print('EXTRACTED_PROJECT_IMPORTS',len(mods))\n"
   run=subprocess.run([exe,'-I','-B','-c',code],capture_output=True,text=True);(B/('tests-'+kind+'-'+label+'.txt')).write_text(run.stdout+run.stderr);assert run.returncode==0,run.stdout+run.stderr;assert 'Ran '+str(count)+' tests' in run.stderr
   results.append(dict(python=label,suite=kind,tests=count,status='PASS',imports='extracted payload only',live_network='denied'))
 # A separate real flock fixture for the changed Ozon shared-slot wrapper.
 code="""import fcntl,sys,tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,FOLDER)
import controller as c
with tempfile.TemporaryDirectory(dir=SCRATCH) as t:
 d=Path(t);lock=d/'slot';lock.touch()
 def inside(*args):
  with lock.open('rb') as f:
   try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
   except BlockingIOError:pass
   else:raise AssertionError('shared slot not held during worker')
  return 42
 with patch.object(c,'context'),patch.object(c.r,'trust'),patch.object(c,'FINANCE_LOCK',lock),patch.object(c,'LEDGER',d),patch.object(c,'state',return_value={'ActiveState':'inactive'}),patch.object(c,'_run_one_inner',side_effect=inside):assert c.run_one({},{})==42
 with lock.open('rb') as f:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
print('OZON_SHARED_SLOT_FIXTURE_PASS')
""".replace('FOLDER',repr(str(stage/'ozon'))).replace('SCRATCH',repr('/home/hermes/.hermes/cache/scratch'))
 run=subprocess.run(['/usr/bin/python3','-I','-B','-c',code],capture_output=True,text=True);assert run.returncode==0,run.stdout+run.stderr;(B/'ozon-slot-fixture.txt').write_text(run.stdout)
 code="import sys;from pathlib import Path;sys.path.insert(0,"+repr(str(stage))+");import start_root as s;Path("+repr(str(stage/'msp-wb-daily-weekly.service'))+").write_bytes(s.service_text());Path("+repr(str(stage/'msp-wb-daily-weekly.timer'))+").write_bytes(s.timer_text())"
 subprocess.run(['/usr/bin/python3','-I','-B','-c',code],check=True)
 run=subprocess.run(['systemd-analyze','verify',str(stage/'msp-wb-daily-weekly.service'),str(stage/'msp-wb-daily-weekly.timer')],capture_output=True,text=True);assert run.returncode==0,run.stderr;(B/'unit-syntax.txt').write_text(run.stdout+run.stderr)
 run=subprocess.run(['/usr/bin/python3','-I','-B',str(stage/'start_root.py')],capture_output=True,text=True);assert run.returncode!=0 and 'PermissionError' in run.stderr
 # Verify one physical shell command also has exactly the intended argv.
 source=(B/'launch_verified.py').read_text();compile(source,'launcher','exec');assert 'read(16000001)' in source and 'msp-wb-daily-weekly.' in source
subprocess.run(['python3',str(B/'build.py')],check=True);assert raw==(B/'wb-daily-weekly.tar.gz').read_bytes();assert command==(B/'ROOT_WB_DAILY.txt').read_bytes()
evidence=dict(status='PREPARED_NOT_INSTALLED',archive_sha256=sha(raw),tests=results,unit_syntax='PASS',ozon_shared_slot_real_flock_fixture='PASS',nonroot_boundary='PASS',reproducible_archive='PASS',provider_calls=0,telegram_messages_sent=0,root_installation=False,initial_backfill_verified=False)
(B/'verification.json').write_text(json.dumps(evidence,indent=2)+'\n');print(json.dumps(evidence))
