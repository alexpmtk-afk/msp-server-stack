from pathlib import Path
import json,subprocess,tarfile,tempfile,os,hashlib,re
B=Path(__file__).parent
with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as tmp:
 stage=Path(tmp)
 with tarfile.open(B/'ozon-resilient-recovery.tar.gz') as tar:
  for m in tar.getmembers():
   assert m.isfile() and not Path(m.name).is_absolute() and '..' not in Path(m.name).parts
   p=stage/m.name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(tar.extractfile(m).read())
 manifest=json.loads((stage/'MANIFEST.json').read_bytes());assert all(hashlib.sha256((stage/n).read_bytes()).hexdigest()==h for n,h in manifest.items())
 for c in ('ozon_dmitrieva','ozon_novokshenov','ozon_laser_master'):
  for n,h in json.loads((stage/c/'MANIFEST.json').read_bytes()).items():assert hashlib.sha256((stage/c/n).read_bytes()).hexdigest()==h
 for exe,label in [('python3','3.14'),('/usr/bin/python3','3.12')]:
  logs=[];count=0
  for name in ('test_recovery.py','test_controller.py'):
   if name=='test_recovery.py':cmd=[exe,str(B/name)];env=dict(os.environ,RECOVERY_TEST_PAYLOAD=str(stage))
   else:
    code=(B/name).read_text().replace("P=Path(__file__).parent/'payload'",'P=Path('+repr(str(stage))+')');f=stage/'controller-tests.py';f.write_text(code);cmd=[exe,str(f)];env=dict(os.environ)
   r=subprocess.run(cmd,capture_output=True,text=True,env=env);logs.append(r.stdout+r.stderr);assert r.returncode==0,r.stdout+r.stderr;count+=int(re.search(r'Ran (\d+) tests',r.stderr).group(1))
  assert count==14
  (B/f'tests-{label}.txt').write_text('\n'.join(logs));print(label,count,'network-denied tests PASS from extracted artifact')
old=(B/'ozon-resilient-recovery.tar.gz').read_bytes();subprocess.run(['python3',str(B/'build.py')],check=True);assert old==(B/'ozon-resilient-recovery.tar.gz').read_bytes()
print('Exact archive/manifests and reproducibility PASS')
