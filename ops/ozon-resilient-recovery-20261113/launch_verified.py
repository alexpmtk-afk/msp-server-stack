import gzip,hashlib,io,json,os,pathlib,subprocess,sys,tarfile,tempfile
assert os.geteuid()==0,"Run in Linux root console"
os.umask(0o077)
stage=pathlib.Path(tempfile.mkdtemp(prefix="msp-ozon-resilient-recovery.",dir="/var/lib"))
raw=pathlib.Path('/home/hermes/workspace/ozon-resilient-recovery-20261113/ozon-resilient-recovery.tar.gz').read_bytes()
assert len(raw)<16000000 and hashlib.sha256(raw).hexdigest()=='d91882c26cbc74f89e266d1f62a5b90402623557fd98fab377d97649c58ad875',"Archive hash mismatch"
(stage/"package.tar.gz").write_bytes(raw)
with tarfile.open(fileobj=io.BytesIO(raw),mode="r:gz") as t:
 members=t.getmembers();names=[m.name for m in members]
 assert len(names)==len(set(names)) and len(names)<120
 assert all(m.isfile() and m.mode==0o644 and m.size<4000000 and not pathlib.PurePosixPath(m.name).is_absolute() and ".." not in pathlib.PurePosixPath(m.name).parts for m in members)
 data={m.name:t.extractfile(m).read() for m in members}
 assert sum(map(len,data.values()))<16000000
 assert hashlib.sha256(data["MANIFEST.json"]).hexdigest()=='dfc46ba46167baf458e2b0b4b68963718864a848c12db75c82c5ccfca7f077ad'
 expected=json.loads(data["MANIFEST.json"])
 assert set(data)==set(expected)|{"MANIFEST.json"}
 assert all(hashlib.sha256(data[n]).hexdigest()==h for n,h in expected.items())
 for n,b in data.items():
  p=stage/n;p.parent.mkdir(parents=True,exist_ok=True)
  with p.open("xb") as f:f.write(b);f.flush();os.fchmod(f.fileno(),0o644);os.fsync(f.fileno())
 for p in sorted([stage]+[p for p in stage.rglob("*") if p.is_dir()],key=lambda p:len(p.parts),reverse=True):
  os.chmod(p,0o755);fd=os.open(p,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
subprocess.run(["/usr/bin/python3","-I","-B",str(stage/"start_root.py")],check=True)
