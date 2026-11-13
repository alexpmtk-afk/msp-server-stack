import gzip,hashlib,io,json,os,pathlib,subprocess,sys,tarfile,tempfile
assert os.geteuid()==0,"Run in Linux root console"
os.umask(0o077)
stage=pathlib.Path(tempfile.mkdtemp(prefix="msp-ozon-remaining-accruals.",dir="/var/lib"))
raw=pathlib.Path('/home/hermes/workspace/ozon-remaining-accruals-20261112/ozon-remaining-accruals.tar.gz').read_bytes()
assert len(raw)<16000000 and hashlib.sha256(raw).hexdigest()=='0a14fe0de006bd7d9391b3a6ed0453076cec72bcb405ca404eef92a0cf3c15f8',"Archive hash mismatch"
(stage/"package.tar.gz").write_bytes(raw)
with tarfile.open(fileobj=io.BytesIO(raw),mode="r:gz") as t:
 members=t.getmembers();names=[m.name for m in members]
 assert len(names)==len(set(names)) and len(names)<100
 assert all(m.isfile() and m.mode==0o644 and m.size<4000000 and not pathlib.PurePosixPath(m.name).is_absolute() and ".." not in pathlib.PurePosixPath(m.name).parts for m in members)
 data={m.name:t.extractfile(m).read() for m in members}
 assert sum(map(len,data.values()))<16000000
 assert hashlib.sha256(data["MANIFEST.json"]).hexdigest()=='debdca24297fefe305c0b172d9a7a3d87c98dc433a0949eeb5b2af5dd3a2e8b7'
 expected=json.loads(data["MANIFEST.json"])
 assert set(data)==set(expected)|{"MANIFEST.json"}
 assert all(hashlib.sha256(data[n]).hexdigest()==h for n,h in expected.items())
 for n,b in data.items():
  p=stage/n;p.parent.mkdir(parents=True,exist_ok=True)
  with p.open("xb") as f:f.write(b);f.flush();os.fchmod(f.fileno(),0o644);os.fsync(f.fileno())
 for p in sorted([stage]+[p for p in stage.rglob("*") if p.is_dir()],key=lambda p:len(p.parts),reverse=True):
  os.chmod(p,0o755);fd=os.open(p,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
subprocess.run(["/usr/bin/python3","-I","-B",str(stage/"start_root.py")],check=True)
