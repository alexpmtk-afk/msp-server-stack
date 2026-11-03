"""Build a deterministic, secrets-free offline root-bootstrap bundle.

Usage: system python package.py --wheel <previously hash-verified candidate>
--output <new .tar>. Does not install, sudo, read secrets or call any service.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import subprocess
import tarfile

CODE='c1fee070e9efa0c925a78f266fdf03cb12a173cf'
ADMIN='4df06d795b494cff167b67489f17b2028142aa79'
ROOT=Path(__file__).resolve().parents[2]
WHEEL_SHA='a4fe1aac3d3b3cc791d4b3d5931c5a956045dc951ee74d1c913ee3ac4d2ee9fb'


def sha(b): return hashlib.sha256(b).hexdigest()


def gitfile(ref,name):
    return subprocess.check_output(['git','show',ref+':'+name],cwd=ROOT)


def validate(raw, manifest_sha):
    """All validation before writes; intentionally no tar extract/extractall."""
    result={}
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as tar:
        for entry in tar:
            name=entry.name
            if (not entry.isfile() or entry.mode != 0o644 or entry.uid or entry.gid
                or name.startswith('/') or '\\' in name
                or any(x in ('','.','..') for x in name.split('/'))
                or name in result or entry.size > 8*1024*1024):
                raise ValueError('unsafe tar member')
            result[name]=tar.extractfile(entry).read()
    manifest=result.pop('BUNDLE_MANIFEST.json')
    if sha(manifest)!=manifest_sha: raise ValueError('manifest hash mismatch')
    entries=json.loads(manifest)['files']
    expected={e['path']:e['sha256'] for e in entries}
    if len(expected)!=len(entries) or set(expected)!=set(result): raise ValueError('inventory mismatch')
    for name,b in result.items():
        if sha(b)!=expected[name]: raise ValueError('file hash mismatch')
    return result,manifest


# This literal verifier runs from the owner's pasted command, NOT from writable
# source. It validates archive+manifest+ALL files before any extraction/execution.
LAUNCHER = '''import os,sys,stat,hashlib,tarfile,io,json,subprocess
from pathlib import Path
assert os.geteuid()==0,"ROOT_REQUIRED"
p,ah,mh=sys.argv[1:4]
raw=Path(p).read_bytes()
assert len(raw)<16777216 and hashlib.sha256(raw).hexdigest()==ah,"BUNDLE_HASH"
files={}
with tarfile.open(fileobj=io.BytesIO(raw),mode="r:") as tar:
 for e in tar:
  n=e.name
  assert e.isfile() and e.mode==420 and e.uid==0 and e.gid==0 and e.size<8388608 and n not in files and not n.startswith("/") and "\\\\" not in n and all(x not in ("",".","..") for x in n.split("/")),"TAR_MEMBER"
  files[n]=tar.extractfile(e).read()
m=files.pop("BUNDLE_MANIFEST.json")
assert hashlib.sha256(m).hexdigest()==mh,"MANIFEST_HASH"
entries=json.loads(m)["files"]
expected={e["path"]:e["sha256"] for e in entries}
assert len(expected)==len(entries) and set(expected)==set(files),"INVENTORY"
assert all(hashlib.sha256(b).hexdigest()==expected[n] for n,b in files.items()),"FILE_HASH"
base=Path("/var/lib")
for x in (Path("/"),Path("/var"),base):
 s=x.lstat();assert stat.S_ISDIR(s.st_mode) and s.st_uid==0 and not s.st_mode&18,"ROOT_PARENT"
stage=base/("msp-wb-bootstrap-package-"+ah[:16])
assert not stage.exists() and not stage.is_symlink(),"STAGE_EXISTS_STOP_NO_RETRY"
os.umask(63);stage.mkdir(mode=448)
files["BUNDLE_MANIFEST.json"]=m
for n,b in files.items():
 f=stage/n;f.parent.mkdir(parents=True,exist_ok=True)
 fd=os.open(f,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,384)
 with os.fdopen(fd,"wb") as out:out.write(b);out.flush();os.fsync(out.fileno())
for d in sorted([x for x in stage.rglob("*") if x.is_dir()]+[stage],key=lambda x:len(x.parts),reverse=True):
 fd=os.open(d,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
raise SystemExit(subprocess.run(["/usr/bin/python3","-I","-B",str(stage/"install.py")],cwd=stage,env={"PATH":"/usr/sbin:/usr/bin:/sbin:/bin","LANG":"C.UTF-8"}).returncode)
'''


def command(path,bundle_sha,manifest_sha):
    # Shell one-line with the exact trusted verifier embedded, not command substitution.
    return 'sudo /usr/bin/python3 -I -B -c '+shlex.quote(LAUNCHER.replace('\n','\n'))+' '+shlex.quote(str(path))+' '+bundle_sha+' '+manifest_sha


def main():
    p=argparse.ArgumentParser();p.add_argument('--wheel',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args()
    wheel=a.wheel.read_bytes()
    if sha(wheel)!=WHEEL_SHA: raise ValueError('wheel hash mismatch')
    install=json.loads(gitfile(CODE,'docs/marketplace-reports/deployment/autonomous-wb/INSTALL_MANIFEST.json'))
    files={n:gitfile(CODE,n) for n in install['files']}
    for n,h in install['files'].items(): assert sha(files[n])==h
    files['INSTALL_MANIFEST.json']=gitfile(CODE,'docs/marketplace-reports/deployment/autonomous-wb/INSTALL_MANIFEST.json')
    files['pilot-plan.json']=gitfile(CODE,'docs/marketplace-reports/deployment/autonomous-wb/pilot-plan.json')
    for source,target in [('select_pilot_credential.py','select_pilot_credential.py'),('redis_readonly_probe.py','redis_readonly_probe.py'),('msp-wb-pilot.STAGED.service.in','staged.service.in')]:
        files[target]=gitfile(ADMIN,'docs/marketplace-reports/admin-ready/'+source)
    for name in ['install.py','smoke.py']:files[name]=(Path(__file__).parent/name).read_bytes()
    files['redis-8.1.0-py3-none-any.whl']=wheel
    manifest=json.dumps({'code_sha':CODE,'admin_sha':ADMIN,'state':'PREPARED_NOT_EXECUTED',
        'files':[{'path':n,'sha256':sha(b),'bytes':len(b)} for n,b in sorted(files.items())]},indent=2).encode()+b'\n'
    files['BUNDLE_MANIFEST.json']=manifest
    buf=io.BytesIO()
    with tarfile.open(fileobj=buf,mode='w',format=tarfile.USTAR_FORMAT) as tar:
        for n,b in sorted(files.items()):
            info=tarfile.TarInfo(n);info.size=len(b);info.mode=0o644;info.uid=info.gid=info.mtime=0
            tar.addfile(info,io.BytesIO(b))
    raw=buf.getvalue();validate(raw,sha(manifest))
    with a.output.open('xb') as f:f.write(raw)
    # repr of the multiline trusted verifier gives ONE physical shell line.
    launcher='exec('+repr(LAUNCHER)+')'
    line='sudo /usr/bin/python3 -I -B -c '+shlex.quote(launcher)+' '+shlex.quote(str(a.output.resolve()))+' '+sha(raw)+' '+sha(manifest)
    a.output.with_suffix('.command.txt').write_text(line+'\n')
    a.output.with_suffix('.manifest.json').write_bytes(manifest)
    summary={'bundle':str(a.output.resolve()),'bundle_sha256':sha(raw),'manifest_sha256':sha(manifest),
             'files':len(files)-1,'bytes':len(raw),'code_sha':CODE,'admin_sha':ADMIN}
    a.output.with_suffix('.summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary))


if __name__=='__main__':main()
