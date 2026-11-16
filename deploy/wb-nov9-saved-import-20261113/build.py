import gzip,hashlib,io,json,subprocess,tarfile
from pathlib import Path
BASE=Path(__file__).resolve().parent
sha=lambda raw:hashlib.sha256(raw).hexdigest()
files={name:(BASE/name).read_bytes() for name in ('baseline.json','publish.py','import_root.py')}
manifest=(json.dumps({n:sha(v) for n,v in files.items()},sort_keys=True,indent=2)+'\n').encode()
files['MANIFEST.json']=manifest
buf=io.BytesIO()
with tarfile.open(fileobj=buf,mode='w') as tar:
 for name,raw in sorted(files.items()):
  m=tarfile.TarInfo(name);m.size=len(raw);m.mode=0o644;m.uid=m.gid=m.mtime=0;tar.addfile(m,io.BytesIO(raw))
raw=gzip.compress(buf.getvalue(),mtime=0);archive=BASE/'nov9-import.tar.gz';archive.write_bytes(raw)
digest,manifest_digest=sha(raw),sha(manifest)
bootstrap = '''import gzip,hashlib,io,json,os,pathlib,subprocess,sys,tarfile,tempfile
assert os.geteuid()==0,"Run in Linux root console"
os.umask(0o077)
stage=pathlib.Path(tempfile.mkdtemp(prefix="msp-wb-nov9-import.",dir="/var/lib"))
with pathlib.Path(SOURCE).open("rb") as f:raw=f.read(16000001)
assert len(raw)<16000000 and hashlib.sha256(raw).hexdigest()==ARCHIVE_HASH,"Archive hash mismatch"
(stage/"package.tar.gz").write_bytes(raw)
with tarfile.open(fileobj=io.BytesIO(raw),mode="r:gz") as t:
 members=t.getmembers();names=[m.name for m in members]
 assert len(names)==len(set(names)) and len(names)<200
 assert all(m.isfile() and m.mode==0o644 and m.size<4000000 and not pathlib.PurePosixPath(m.name).is_absolute() and ".." not in pathlib.PurePosixPath(m.name).parts for m in members)
 data={m.name:t.extractfile(m).read() for m in members}
 assert sum(map(len,data.values()))<16000000
 assert hashlib.sha256(data["MANIFEST.json"]).hexdigest()==MANIFEST_HASH
 expected=json.loads(data["MANIFEST.json"])
 assert set(data)==set(expected)|{"MANIFEST.json"}
 assert all(hashlib.sha256(data[n]).hexdigest()==h for n,h in expected.items())
 for n,b in data.items():
  p=stage/n;p.parent.mkdir(parents=True,exist_ok=True)
  with p.open("xb") as f:f.write(b);f.flush();os.fchmod(f.fileno(),0o644);os.fsync(f.fileno())
 for p in sorted([stage]+[p for p in stage.rglob("*") if p.is_dir()],key=lambda p:len(p.parts),reverse=True):
  os.chmod(p,0o755);fd=os.open(p,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
subprocess.run(["/usr/bin/python3","-I","-B",str(stage/"import_root.py")],check=True)
'''.replace('SOURCE', repr(str(archive))).replace('ARCHIVE_HASH', repr(digest)).replace('MANIFEST_HASH', repr(manifest_digest))
compile(bootstrap,'launcher','exec')
launcher=BASE/'launch_verified.py';launcher.write_text(bootstrap)
h=sha(bootstrap.encode())
command='wb_nov9=$(mktemp -d /var/lib/msp-wb-nov9-launch.XXXXXXXX) && install -o root -g root -m 600 '+str(launcher)+' "$wb_nov9/import.py" && printf \'%s  %s\\n\' '+h+' "$wb_nov9/import.py" | sha256sum -c - && /usr/bin/python3 -I -B "$wb_nov9/import.py"'
assert '\n' not in command
subprocess.run(['bash','-n','-c',command],check=True)
(BASE/'ROOT_IMPORT.txt').write_text(command+'\n')
(BASE/'package-receipt.json').write_text(json.dumps(dict(status='PREPARED_NOT_EXECUTED',archive_sha256=digest,manifest_sha256=manifest_digest,launcher_sha256=h,files={n:sha(v) for n,v in files.items()},provider_calls=0,scope='One verified saved Nov9 document and exact queue settlement only; no transport, timer change or recurring fallback'),indent=2)+'\n')
print(json.dumps(dict(archive_sha256=digest,launcher_sha256=h)))
