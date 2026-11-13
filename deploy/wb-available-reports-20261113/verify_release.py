import hashlib,io,json,os,subprocess,tarfile,tempfile
from pathlib import Path
B=Path(__file__).resolve().parent;sha=lambda raw:hashlib.sha256(raw).hexdigest()
subprocess.run(['python3',str(B/'build.py')],check=True);raw=(B/'wb-available-reports.tar.gz').read_bytes();receipt=json.loads((B/'package-receipt.json').read_bytes());assert sha(raw)==receipt['archive_sha256'];command=(B/'ROOT_WB_AVAILABLE.txt').read_bytes();assert len(command.splitlines())==1 and sha(command)==receipt['command_sha256'];subprocess.run(['bash','-n','-c',command.decode()],check=True);results=[]
with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
 root=Path(t);names=[]
 with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as tar:
  for member in tar:
   assert member.isfile() and member.mode==0o644 and member.name not in names and not Path(member.name).is_absolute() and '..' not in Path(member.name).parts
   names.append(member.name);p=root/member.name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(tar.extractfile(member).read())
 manifest=json.loads((root/'MANIFEST.json').read_bytes());assert set(names)==set(manifest)|{'MANIFEST.json'};assert sha((root/'MANIFEST.json').read_bytes())==receipt['manifest_sha256'];assert all(sha((root/n).read_bytes())==p for n,p in manifest.items())
 baseline=json.loads((root/'upgrade-baseline.json').read_bytes());old=Path(baseline['old_root']);old_manifest=json.loads((old/'MANIFEST.json').read_bytes());assert sha((old/'MANIFEST.json').read_bytes())==baseline['old_manifest_sha256']
 changed={name for name,pin in old_manifest.items() if sha((root/name).read_bytes())!=pin};assert changed=={'controller.py','worker.py','plan.py','notify.py','catalog.py'},changed
 nested=json.loads((root/'ozon/MANIFEST.json').read_bytes());assert all(sha((root/'ozon'/n).read_bytes())==p for n,p in nested.items())
 suites=[('policy',B/'test_policy.py',3),('policy_more',B/'test_policy_more.py',12),('availability',B/'test_availability.py',10),('upgrade',B/'test_upgrade.py',6),('existing_wb',B.parent/'wb-daily-weekly-20261113/test_wb.py',39)]
 for exe,label in [('python3','3.14'),('/usr/bin/python3','3.12')]:
  for name,script,count in suites:
   code="import sys,os,pathlib,runpy\ndef deny(e,a):\n if e in ('socket.connect','socket.bind','socket.getaddrinfo'):raise AssertionError('No live network')\nsys.addaudithook(deny)\nos.environ['WB_TEST_PAYLOAD']="+repr(str(root))+"\nsys.argv=['release-test']\ntry:runpy.run_path("+repr(str(script))+",run_name='__main__')\nexcept SystemExit as e:assert e.code==0\n"
   code+="mods=[m for n,m in sys.modules.items() if n in ('controller','worker','catalog','plan','policy','upgrade_root','root_common','start_root','notify','recovery') or n.startswith('apps.')]\nassert mods and all(pathlib.Path(m.__file__).resolve().is_relative_to(pathlib.Path("+repr(str(root))+")) for m in mods if getattr(m,'__file__',None));print('EXTRACTED_IMPORTS',len(mods))"
   r=subprocess.run([exe,'-I','-B','-c',code],capture_output=True,text=True);(B/('tests-'+name+'-'+label+'.txt')).write_text(r.stdout+r.stderr);assert r.returncode==0,r.stdout+r.stderr;assert 'Ran '+str(count)+' tests' in r.stderr and 'skipped=' not in r.stderr;results.append(dict(python=label,suite=name,tests=count,status='PASS',live_network='denied',imports='extracted payload only'))
 r=subprocess.run(['/usr/bin/python3','-I','-B',str(root/'upgrade_root.py')],capture_output=True,text=True);assert r.returncode!=0 and 'PermissionError' in r.stdout
subprocess.run(['python3',str(B/'build.py')],check=True);assert raw==(B/'wb-available-reports.tar.gz').read_bytes() and command==(B/'ROOT_WB_AVAILABLE.txt').read_bytes()
out=dict(status='PREPARED_NOT_INSTALLED',archive_sha256=sha(raw),tests=results,existing_changed_modules=sorted(changed),ozon_payload='unchanged',request_budgets_reset=False,provider_calls=0,telegram_messages_sent=0,root_upgrade_executed=False,reproducible_archive=True)
(B/'verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
