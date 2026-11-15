import gzip,hashlib,io,json,os,pathlib,subprocess,sys,tarfile,tempfile
assert os.geteuid()==0,"Run in Linux root console"
os.umask(0o077)
stage=pathlib.Path(tempfile.mkdtemp(prefix="msp-marketplace-loader-repair.",dir="/var/lib"))
with pathlib.Path('/home/hermes/workspace/marketplace-loader-repair-20261115/marketplace-loader-repair.tar.gz').open("rb") as f:raw=f.read(16000001)
assert len(raw)<16000000 and hashlib.sha256(raw).hexdigest()=='f196496209bbf168275a1020e65d7621d527f6e27c32b27a181591cbff841b07',"Archive hash mismatch"
(stage/"package.tar.gz").write_bytes(raw)
with tarfile.open(fileobj=io.BytesIO(raw),mode="r:gz") as t:
 members=t.getmembers();names=[m.name for m in members]
 assert len(names)==len(set(names)) and len(names)<200
 assert all(m.isfile() and m.mode==0o644 and m.size<4000000 and not pathlib.PurePosixPath(m.name).is_absolute() and ".." not in pathlib.PurePosixPath(m.name).parts for m in members)
 data={m.name:t.extractfile(m).read() for m in members}
 assert sum(map(len,data.values()))<16000000
 assert hashlib.sha256(data["MANIFEST.json"]).hexdigest()=='a8f9a666d0ea6da082889a927262d53dd375dce15dec259369e2db38c5cbd41c'
 expected=json.loads(data["MANIFEST.json"])
 assert set(data)==set(expected)|{"MANIFEST.json"}
 assert all(hashlib.sha256(data[n]).hexdigest()==h for n,h in expected.items())
 for n,b in data.items():
  p=stage/n;p.parent.mkdir(parents=True,exist_ok=True)
  with p.open("xb") as f:f.write(b);f.flush();os.fchmod(f.fileno(),0o644);os.fsync(f.fileno())
 for p in sorted([stage]+[p for p in stage.rglob("*") if p.is_dir()],key=lambda p:len(p.parts),reverse=True):
  os.chmod(p,0o755);fd=os.open(p,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
subprocess.run(["/usr/bin/python3","-I","-B",str(stage/"calendar_upgrade.py")],check=True)
