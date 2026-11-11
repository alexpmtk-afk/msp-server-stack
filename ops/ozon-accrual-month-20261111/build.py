import gzip
import hashlib
import io
import json
from pathlib import Path
import shlex
import subprocess
import tarfile

BASE = Path(__file__).parent
PAYLOAD = BASE / 'payload'
sha = lambda b: hashlib.sha256(b).hexdigest()
files = {str(p.relative_to(PAYLOAD)): p.read_bytes() for p in PAYLOAD.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name != 'MANIFEST.json'}
manifest = (json.dumps({name: sha(raw) for name, raw in sorted(files.items())}, sort_keys=True, indent=2) + '\n').encode()
(PAYLOAD / 'MANIFEST.json').write_bytes(manifest)
files['MANIFEST.json'] = manifest

def build():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w') as tar:
        for name, raw in sorted(files.items()):
            m = tarfile.TarInfo(name)
            m.size = len(raw); m.mode = 0o644; m.uid = m.gid = m.mtime = 0
            tar.addfile(m, io.BytesIO(raw))
    return gzip.compress(buf.getvalue(), mtime=0)

raw = build()
assert raw == build(), 'non-reproducible package'
archive = BASE / 'ozon-accrual-month.tar.gz'
archive.write_bytes(raw)
digest, manifest_digest = sha(raw), sha(manifest)
bootstrap = '''import gzip,hashlib,io,json,os,pathlib,subprocess,sys,tarfile,tempfile
assert os.geteuid()==0,"Run in Linux root console"
os.umask(0o077)
stage=pathlib.Path(tempfile.mkdtemp(prefix="msp-ozon-accrual-month.",dir="/var/lib"))
raw=pathlib.Path(SOURCE).read_bytes()
assert len(raw)<16000000 and hashlib.sha256(raw).hexdigest()==ARCHIVE_HASH,"Archive hash mismatch"
(stage/"package.tar.gz").write_bytes(raw)
with tarfile.open(fileobj=io.BytesIO(raw),mode="r:gz") as t:
 members=t.getmembers();names=[m.name for m in members]
 assert len(names)==len(set(names)) and len(names)<100
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
subprocess.run(["/usr/bin/python3","-I","-B",str(stage/"start_root.py")],check=True)
'''.replace('SOURCE', repr(str(archive))).replace('ARCHIVE_HASH', repr(digest)).replace('MANIFEST_HASH', repr(manifest_digest))
compile(bootstrap, 'bootstrap', 'exec')
# Copy the pinned verifier to a root-owned snapshot before executing any code.
launcher = BASE / 'launch_verified.py'
launcher.write_text(bootstrap)
launcher_hash = sha(bootstrap.encode())
command = ('ozon_stage=$(mktemp -d /var/lib/msp-ozon-accrual-month-launch.XXXXXXXX) && install -o root -g root -m 600 '
           + str(launcher) + ' "$ozon_stage/launch.py" && printf \'%s  %s\\n\' '
           + launcher_hash + ' "$ozon_stage/launch.py" | sha256sum -c - && /usr/bin/python3 -I -B "$ozon_stage/launch.py"')
assert '\n' not in command
subprocess.run(['bash', '-n', '-c', command], check=True)
(BASE / 'ROOT_OZON_ACCRUAL_MONTH.txt').write_text(command + '\n')
(BASE / 'package-receipt.json').write_text(json.dumps({'status': 'PREPARED_NOT_EXECUTED', 'archive_sha256': digest, 'manifest_sha256': manifest_digest, 'launcher_sha256': launcher_hash, 'files': len(files), 'command_sha256': sha((command+'\n').encode()), 'scope': 'Only January2026 ozon_dmitrieva all31days, pinned types/day15 reused; max128 new sender entries, max10pages/day; no month financial reconciliation claim; same executor/Redis, no timer/LLM', 'command_physical_lines': 1}, indent=2)+'\n')
print(json.dumps({'archive_sha256': digest, 'files': len(files), 'command_chars': len(command)}))
