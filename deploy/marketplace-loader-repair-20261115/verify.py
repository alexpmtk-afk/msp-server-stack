"""Build, extract and test the actual private release without network or root."""
import hashlib,io,json,os,subprocess,tarfile,tempfile
from pathlib import Path
B=Path(__file__).resolve().parent
PREVIOUS=B.parent/'marketplace-download-summaries-20261113'
def sha(raw):return hashlib.sha256(raw).hexdigest()
subprocess.run(['python3','-B',str(B/'build.py')],check=True)
raw=(B/'marketplace-loader-repair.tar.gz').read_bytes();command=(B/'ROOT_REPAIR.txt').read_bytes()
receipt=json.loads((B/'package-receipt.json').read_text());results=[]
assert len(command.splitlines())==1 and sha(raw)==receipt['archive_sha256']
with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as tmp:
 root=Path(tmp)
 with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as tar:
  members=tar.getmembers();names=[m.name for m in members]
  assert len(names)==len(set(names))
  for m in members:
   assert m.isfile() and m.mode==0o644 and not Path(m.name).is_absolute() and '..' not in Path(m.name).parts
   p=root/m.name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(tar.extractfile(m).read())
 manifest=json.loads((root/'MANIFEST.json').read_text());assert set(names)==set(manifest)|{'MANIFEST.json'}
 assert sha((root/'MANIFEST.json').read_bytes())==receipt['manifest_sha256']
 assert all(sha((root/n).read_bytes())==h for n,h in manifest.items())
 nested=json.loads((root/'ozon/MANIFEST.json').read_text());assert all(sha((root/'ozon'/n).read_bytes())==h for n,h in nested.items())
 cfg=json.loads((root/'repair-baseline.json').read_text());old=Path(cfg['old_root']);prior=json.loads((old/'MANIFEST.json').read_text())
 changed={n for n,h in prior.items() if sha((root/n).read_bytes())!=h}
 assert changed=={'ozon/MANIFEST.json'}|{'ozon/'+cab+'/apps/msp_marketplace_reports/ozon_accruals.py' for cab in ('ozon_dmitrieva','ozon_laser_master','ozon_novokshenov')},changed
 suites=[('notices',PREVIOUS/'test_notices.py',22,root,'MP_TEST_PAYLOAD',{}),('cleanup_plan',PREVIOUS/'test_cleanup_plan.py',13,root,'MP_TEST_PAYLOAD',{}),('previous_upgrade',PREVIOUS/'test_upgrade.py',5,root,'MP_TEST_PAYLOAD',{}),('wb_regression',PREVIOUS/'test_wb_regression.py',39,root,'WB_TEST_PAYLOAD',{}),('wb_policy',B.parent/'wb-available-reports-20261113/test_policy.py',3,root,'WB_TEST_PAYLOAD',{}),('wb_policy_edges',B.parent/'wb-available-reports-20261113/test_policy_more.py',12,root,'WB_TEST_PAYLOAD',{}),('wb_variants',B.parent/'wb-available-reports-20261113/test_availability.py',10,root,'WB_TEST_PAYLOAD',{}),('ozon_regression',B.parent/'ozon-daily-wait-20261113/test_v2.py',22,root/'ozon','DAILY_TEST_PAYLOAD',{}),('recovery',B/'test_recovery.py',3,root,'REPAIR_PAYLOAD',{}),('loader_audit',B/'test_loader_audit.py',6,root,'REPAIR_PAYLOAD',{})]
 for cab in ('ozon_dmitrieva','ozon_laser_master','ozon_novokshenov'):suites.append(('calendar_'+cab,B/'test_calendar.py',4,root,'REPAIR_PAYLOAD',{'REPAIR_CABINET':cab}))
 for exe,label in [('python3','3.14'),('/usr/bin/python3','3.12')]:
  for name,script,count,payload,var,extra in suites:
   code="import os,sys,pathlib,runpy\ndef deny(e,a):\n if e in ('socket.connect','socket.bind','socket.getaddrinfo'):raise AssertionError('NO NETWORK')\nsys.addaudithook(deny)\n"
   code+='os.environ.update('+repr(dict(extra,**{var:str(payload)}))+')\nsys.argv=["release-test"]\n'
   code+='try:runpy.run_path('+repr(str(script))+',run_name="__main__")\nexcept SystemExit as e:assert e.code==0\n'
   code+='mods=[m for n,m in sys.modules.items() if n in ("controller","worker","catalog","plan","policy","cleanup","calendar_upgrade","calendar_recovery","summary_upgrade","root_common","capture_worker","model","notify","sender","notices_controller") or n.startswith("apps.")]\n'
   code+='assert mods and all(pathlib.Path(m.__file__).resolve().is_relative_to(pathlib.Path('+repr(str(root))+')) for m in mods if getattr(m,"__file__",None));print("EXTRACTED_IMPORTS",len(mods))\n'
   r=subprocess.run([exe,'-I','-B','-c',code],capture_output=True,text=True)
   (B/('tests-'+name+'-'+label+'.txt')).write_text(r.stdout+r.stderr)
   assert r.returncode==0 and 'Ran '+str(count)+' tests' in r.stderr and 'skipped=' not in r.stderr,r.stdout+r.stderr
   results.append(dict(python=label,suite=name,tests=count,status='PASS',network='denied',imports='extracted release'))
  env=dict(os.environ,REPAIR_PAYLOAD=str(old),REPAIR_CABINET='ozon_dmitrieva')
  r=subprocess.run([exe,'-I','-B',str(B/'test_calendar.py')],env=env,capture_output=True,text=True)
  (B/('baseline-calendar-red-'+label+'.txt')).write_text(r.stdout+r.stderr)
  assert r.returncode!=0 and 'outside bounded current snapshot' in r.stderr
 r=subprocess.run(['/usr/bin/python3','-I','-B',str(root/'calendar_upgrade.py')],capture_output=True,text=True)
 assert r.returncode!=0 and 'Linux root console required' in r.stderr
 # Read-only pin preflight, no root platform credentials, writes or provider.
 import importlib.util,sys
 sys.path.insert(0,str(root));spec=importlib.util.spec_from_file_location('calendar_upgrade_gate',root/'calendar_upgrade.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.pins(cfg)
subprocess.run(['python3','-B',str(B/'build.py')],check=True)
assert raw==(B/'marketplace-loader-repair.tar.gz').read_bytes() and command==(B/'ROOT_REPAIR.txt').read_bytes()
out=dict(status='PREPARED_NOT_INSTALLED',tests=results,tests_per_python=sum(r['tests'] for r in results if r['python']=='3.12'),baseline_regression='RED_BOTH_PYTHONS',changed_existing_modules=sorted(changed),archive_sha256=sha(raw),reproducible=True,provider_calls=0,telegram_messages=0,root_install_executed=False)
(B/'verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
