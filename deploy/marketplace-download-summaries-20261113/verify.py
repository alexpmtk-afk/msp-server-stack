import hashlib,io,json,os,subprocess,tarfile,tempfile
from pathlib import Path
B=Path(__file__).resolve().parent
sha=lambda raw:hashlib.sha256(raw).hexdigest()
def build():subprocess.run(['python3','-B',str(B/'build.py')],check=True)
build();raw=(B/'marketplace-download-summaries.tar.gz').read_bytes();command=(B/'ROOT_SUMMARIES.txt').read_bytes();receipt=json.loads((B/'package-receipt.json').read_text());assert sha(raw)==receipt['archive_sha256'] and len(command.splitlines())==1
results=[]
with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as tmp:
 root=Path(tmp);names=set()
 with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as tar:
  for m in tar:
   assert m.isfile() and m.mode==0o644 and m.name not in names and not Path(m.name).is_absolute() and '..' not in Path(m.name).parts
   p=root/m.name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(tar.extractfile(m).read());names.add(m.name)
 manifest=json.loads((root/'MANIFEST.json').read_text());assert names==set(manifest)|{'MANIFEST.json'};assert all(sha((root/n).read_bytes())==h for n,h in manifest.items());assert sha((root/'MANIFEST.json').read_bytes())==receipt['manifest_sha256']
 nested=json.loads((root/'ozon/MANIFEST.json').read_text());assert all(sha((root/'ozon'/n).read_bytes())==h for n,h in nested.items())
 cfg=json.loads((root/'summary-upgrade-baseline.json').read_text());old=Path(cfg['old_wb_root']);prior=json.loads((old/'MANIFEST.json').read_text());changed={n for n,h in prior.items() if sha((root/n).read_bytes())!=h};assert changed=={'controller.py','plan.py','worker.py','ozon/controller.py','ozon/MANIFEST.json'},changed
 suites=[('notices',B/'test_notices.py',22,root,'MP_TEST_PAYLOAD'),('cleanup_plan',B/'test_cleanup_plan.py',13,root,'MP_TEST_PAYLOAD'),('upgrade',B/'test_upgrade.py',5,root,'MP_TEST_PAYLOAD'),('wb_regression',B/'test_wb_regression.py',39,root,'WB_TEST_PAYLOAD'),('wb_policy',B.parent/'wb-available-reports-20261113/test_policy.py',3,root,'WB_TEST_PAYLOAD'),('wb_policy_edges',B.parent/'wb-available-reports-20261113/test_policy_more.py',12,root,'WB_TEST_PAYLOAD'),('wb_variants',B.parent/'wb-available-reports-20261113/test_availability.py',10,root,'WB_TEST_PAYLOAD'),('ozon_regression',B.parent/'ozon-daily-wait-20261113/test_v2.py',22,root/'ozon','DAILY_TEST_PAYLOAD')]
 for exe,label in [('python3','3.14'),('/usr/bin/python3','3.12')]:
  for name,script,count,payload,variable in suites:
   code="import os,sys,pathlib,runpy\ndef deny(e,a):\n if e in ('socket.connect','socket.bind','socket.getaddrinfo'):raise AssertionError('No live network')\nsys.addaudithook(deny)\nos.environ["+repr(variable)+"]="+repr(str(payload))+"\nsys.argv=['release-test']\ntry:runpy.run_path("+repr(str(script))+",run_name='__main__')\nexcept SystemExit as e:assert e.code==0\n"
   code+="mods=[m for n,m in sys.modules.items() if n in ('controller','worker','catalog','plan','policy','cleanup','summary_upgrade','root_common','notify','model','sender','notices_controller','capture_worker') or n.startswith('apps.')]\nassert mods and all(pathlib.Path(m.__file__).resolve().is_relative_to(pathlib.Path("+repr(str(root))+")) for m in mods if getattr(m,'__file__',None));print('EXTRACTED_IMPORTS',len(mods))"
   r=subprocess.run([exe,'-I','-B','-c',code],capture_output=True,text=True);(B/('tests-'+name+'-'+label+'.txt')).write_text(r.stdout+r.stderr);assert r.returncode==0,r.stdout+r.stderr;assert 'Ran '+str(count)+' tests' in r.stderr and 'skipped=' not in r.stderr;results.append(dict(python=label,suite=name,tests=count,status='PASS',network='denied',project_imports='extracted payload'))
 # Real privilege guard before any root reads/writes.
 r=subprocess.run(['/usr/bin/python3','-I','-B',str(root/'summary_upgrade.py')],capture_output=True,text=True);assert r.returncode!=0 and 'PermissionError' in r.stderr
 # Parse the generated service with the real systemd validator; not sandbox E2E.
 code="import sys,pathlib\nsys.path.insert(0,"+repr(str(root))+" )\nimport summary_upgrade as u\npathlib.Path("+repr(str(B/'msp-finance-notices.service'))+").write_bytes(u.unit_bytes())"
 subprocess.run(['/usr/bin/python3','-I','-B','-c',code],check=True)
 r=subprocess.run(['systemd-analyze','verify',str(B/'msp-finance-notices.service')],capture_output=True,text=True);(B/'systemd-verify.txt').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stderr
build();assert raw==(B/'marketplace-download-summaries.tar.gz').read_bytes() and command==(B/'ROOT_SUMMARIES.txt').read_bytes()
out=dict(status='PREPARED_NOT_INSTALLED',archive_sha256=sha(raw),tests=results,changed_existing_modules=sorted(changed),systemd_syntax='PASS_not_runtime_acceptance',source_timer_changes=False,provider_calls=0,telegram_messages=0,background_model_calls=0,reproducible_archive=True,root_upgrade_executed=False)
(B/'verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
