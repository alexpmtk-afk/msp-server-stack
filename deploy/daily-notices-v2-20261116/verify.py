import hashlib,importlib.util,io,json,os,subprocess,sys,tarfile,tempfile
from pathlib import Path
B=Path(__file__).resolve().parent
subprocess.run(['python3','-B',str(B/'build.py')],check=True)
raw=(B/'daily-notices-v2.tar.gz').read_bytes();command=(B/'ROOT_NOTICES.txt').read_bytes();pin=json.loads((B/'package-receipt.json').read_text());results=[]
assert len(command.splitlines())==1 and hashlib.sha256(raw).hexdigest()==pin['archive_sha256']
with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
 root=Path(t)
 with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as tar:
  members=tar.getmembers();names=[m.name for m in members];assert len(names)==len(set(names))
  for m in members:
   assert m.isfile() and m.mode==0o644 and not Path(m.name).is_absolute() and '..' not in Path(m.name).parts
   p=root/m.name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(tar.extractfile(m).read())
 manifest=json.loads((root/'MANIFEST.json').read_text());assert set(names)==set(manifest)|{'MANIFEST.json'};assert hashlib.sha256((root/'MANIFEST.json').read_bytes()).hexdigest()==pin['manifest_sha256'];assert all(hashlib.sha256((root/n).read_bytes()).hexdigest()==h for n,h in manifest.items())
 for exe,label in [('python3','3.14'),('/usr/bin/python3','3.12')]:
  for name,count in [('test_daily_v2.py',17),('test_regression.py',22)]:
   code='import os,sys,runpy,pathlib\ndef deny(e,a):\n if e in ("socket.connect","socket.bind","socket.getaddrinfo"):raise AssertionError("NETWORK DENIED")\nsys.addaudithook(deny)\n'
   code+='os.environ["NOTICE_PAYLOAD"]='+repr(str(root))+'\nsys.argv=["release-tests"]\ntry:runpy.run_path('+repr(str(B/name))+',run_name="__main__")\nexcept SystemExit as e:assert e.code==0\n'
   code+='mods=[m for n,m in sys.modules.items() if n in ("model","sender","notice_controller","notices_controller","upgrade")];assert mods and all(pathlib.Path(m.__file__).resolve().is_relative_to(pathlib.Path('+repr(str(root))+')) for m in mods);print("EXTRACTED_IMPORTS",len(mods))'
   r=subprocess.run([exe,'-I','-B','-c',code],capture_output=True,text=True);(B/(name+'-'+label+'.log')).write_text(r.stdout+r.stderr);assert r.returncode==0 and 'Ran '+str(count)+' tests' in r.stderr,r.stdout+r.stderr;results.append(dict(python=label,suite=name,tests=count,status='PASS',network='denied',imports='extracted archive'))
  r=subprocess.run([exe,'-I','-B',str(root/'upgrade.py')],capture_output=True,text=True);assert r.returncode!=0 and 'Linux root console required' in r.stderr
 # Exact read-only runtime pin verification and syntax; no service action.
 spec=importlib.util.spec_from_file_location('upgrade_gate',root/'upgrade.py');u=importlib.util.module_from_spec(spec);spec.loader.exec_module(u);cfg=json.loads((root/'baseline.json').read_text());u.pins(cfg)
 old=Path('/etc/systemd/system/msp-finance-notices.service').read_bytes();new=old
 for n in ('controller.py','sender.py'):
  needle=str(Path(cfg['old_root'])/'notices'/n).encode();assert new.count(needle)==1;new=new.replace(needle,str(root/'notices'/n).encode())
 fixture=B/'msp-finance-notices.service';fixture.write_bytes(new);r=subprocess.run(['systemd-analyze','verify',str(fixture)],capture_output=True,text=True);(B/'systemd-verify.log').write_text(r.stdout+r.stderr);assert r.returncode==0,r.stderr
subprocess.run(['python3','-B',str(B/'build.py')],check=True);assert raw==(B/'daily-notices-v2.tar.gz').read_bytes() and command==(B/'ROOT_NOTICES.txt').read_bytes()
result=dict(status='PREPARED_NOT_INSTALLED',tests=results,tests_per_python=39,systemd_syntax='PASS_NOT_RUNTIME',reproducible=True,provider_calls=0,telegram_messages=0,source_changes=False,weekly_format_changed=False,root_executed=False)
(B/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
