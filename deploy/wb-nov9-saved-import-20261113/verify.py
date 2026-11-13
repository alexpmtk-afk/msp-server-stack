import hashlib,io,json,os,subprocess,tarfile,tempfile
from pathlib import Path
B=Path(__file__).resolve().parent
def build():subprocess.run(['python3','-B',str(B/'build.py')],check=True)
build();raw=(B/'nov9-import.tar.gz').read_bytes();command=(B/'ROOT_IMPORT.txt').read_bytes();receipt=json.loads((B/'package-receipt.json').read_text())
assert hashlib.sha256(raw).hexdigest()==receipt['archive_sha256']
assert len(command.splitlines())==1
results=[]
with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as tmp:
 root=Path(tmp);names=set()
 with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as tar:
  for member in tar:
   assert member.isfile() and member.mode==0o644 and not Path(member.name).is_absolute() and '..' not in Path(member.name).parts and member.name not in names
   names.add(member.name);(root/member.name).write_bytes(tar.extractfile(member).read())
 assert names=={'baseline.json','publish.py','import_root.py','MANIFEST.json'}
 manifest=json.loads((root/'MANIFEST.json').read_text());assert all(hashlib.sha256((root/n).read_bytes()).hexdigest()==h for n,h in manifest.items())
 for exe in ('python3','/usr/bin/python3'):
  code="""import os,sys,unittest,pathlib
def deny(e,a):
 if e in ('socket.connect','socket.bind','socket.getaddrinfo'):raise AssertionError('No network')
sys.addaudithook(deny)
"""+"os.environ['IMPORT_TEST_PAYLOAD']="+repr(str(root))+"\nsys.path.insert(0,"+repr(str(B))+" )\nsuite=unittest.defaultTestLoader.loadTestsFromNames(['test_import','test_transaction'])\nr=unittest.TextTestRunner().run(suite)\nassert r.wasSuccessful() and r.testsRun==12\nimport publish,import_root\nassert all(pathlib.Path(m.__file__).parent==pathlib.Path("+repr(str(root))+" ) for m in (publish,import_root))\n"
  r=subprocess.run([exe,'-I','-B','-c',code],capture_output=True,text=True);assert r.returncode==0,r.stderr+r.stdout
  results.append(dict(python=exe,tests=12,status='PASS',network='denied',payload_imports='extracted archive'))
  (B/('test-'+Path(exe).name+('-system' if exe.startswith('/') else '')+'.txt')).write_text(r.stdout+r.stderr)
 # Exercise the real 92-row source through the extracted publisher twice.
 code="import sys,json,pathlib,tempfile,importlib.util\nsys.path.insert(0,"+repr(str(root))+" )\nimport publish as p\ncfg=json.loads((pathlib.Path(p.__file__).parent/'baseline.json').read_text())\nspec=importlib.util.spec_from_file_location('accepted_catalog',pathlib.Path(cfg['release'])/'catalog.py');a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)\nrows=p.select(json.loads(pathlib.Path('/home/hermes/workspace/msp-report-api-reconciliation-20261113/api-readback/detail.json').read_text()))\nwith tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as tmp:\n archive=pathlib.Path(tmp);base=a.root(p.CAB,archive);(base/'generations').mkdir(parents=True);(base/'documents').mkdir();a.store_index(dict(schema=1,cabinet=p.CAB,baseline_seeded=True,reports={}),archive);a.publish(a.load_index(p.CAB,archive),archive)\n first=p.publish(rows,a,archive,cfg['capture_sha256']);second=p.publish(rows,a,archive,cfg['capture_sha256']);assert first==second and first['rows']==92\n print('REAL_SOURCE_92_ROWS_PRESERVED_REPEAT_NO_DUPLICATES')\n"
 r=subprocess.run(['/usr/bin/python3','-I','-B','-c',code],capture_output=True,text=True);assert r.returncode==0,r.stderr;print(r.stdout.strip())
build();assert raw==(B/'nov9-import.tar.gz').read_bytes() and command==(B/'ROOT_IMPORT.txt').read_bytes()
out=dict(status='PREPARED_NOT_IMPORTED',tests=results,actual_saved_rows_roundtrip=92,repeated_import_no_duplicates=True,reproducible_archive=True,provider_calls=0,production_writes=0,root_execution=False)
(B/'verification.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
