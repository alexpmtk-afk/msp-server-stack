"""Deterministic offline package, verified Ubuntu payload, short root launcher."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import tarfile

ROOT=Path(__file__).resolve().parents[2]
DEBS=Path('/home/hermes/.hermes/cache/scratch/wb-redis-debs-20261103')
DOC=ROOT/'docs/marketplace-reports/redis-package-20261103'
BUNDLE=Path('/home/hermes/workspace/msp-quota-redis.tar')


def sha(b):return hashlib.sha256(b).hexdigest()


def make():
    spec=importlib.util.spec_from_file_location('oldbundle',ROOT/'scripts/wb_bootstrap/package.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    lock=json.loads((Path(__file__).parent/'runtime-lock.json').read_text())
    files={};modes={}
    for pkg in lock['packages']:
        path=DEBS/pkg['deb']
        if sha(path.read_bytes())!=pkg['sha256']:raise ValueError('deb checksum')
        raw=subprocess.check_output(['/usr/bin/dpkg-deb','--fsys-tarfile',str(path)])
        with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
            for member,targets in pkg['selected'].items():
                entry=tar.getmember(member)
                if not entry.isfile():raise ValueError('nonregular binary source')
                for target in targets:
                    files[target]=tar.extractfile(entry).read();modes[target]=0o755 if target.startswith('bin/') else 0o644
    for name in ['install.py','common.py','guard.py','manage.py','runtime-lock.json','service.in']:
        files[name]=(Path(__file__).parent/name).read_bytes();modes[name]=0o644
    app=json.loads((ROOT/'docs/marketplace-reports/deployment/autonomous-wb/INSTALL_MANIFEST.json').read_text())
    app['readonly_probe_sha256']=sha((ROOT/'docs/marketplace-reports/admin-ready/redis_readonly_probe.py').read_bytes())
    files['app-manifest.json']=json.dumps(app,indent=2).encode()+b'\n';modes['app-manifest.json']=0o644
    manifest=json.dumps({'state':'PREPARED_NOT_INSTALLED','package':'MSP local quota Redis',
        'files':[{'path':name,'sha256':sha(data),'mode':modes[name],'bytes':len(data)} for name,data in sorted(files.items())]},indent=2).encode()+b'\n'
    files['BUNDLE_MANIFEST.json']=manifest
    out=io.BytesIO()
    with tarfile.open(fileobj=out,mode='w',format=tarfile.USTAR_FORMAT) as tar:
        for name,data in sorted(files.items()):
            info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644;info.uid=info.gid=info.mtime=0;tar.addfile(info,io.BytesIO(data))
    raw=out.getvalue();module.validate(raw,sha(manifest))
    return raw,manifest,module.LAUNCHER


def main():
    raw,manifest,launcher=make();again,m2,_=make()
    if raw!=again or manifest!=m2:raise ValueError('nonreproducible package')
    DOC.mkdir(exist_ok=True)
    BUNDLE.write_bytes(raw);(DOC/'redis-package.tar').write_bytes(raw);(DOC/'BUNDLE_MANIFEST.json').write_bytes(manifest)
    launcher=launcher.replace('msp-wb-bootstrap-package-','msp-quota-redis-package-')
    launcher=launcher.replace('raw=Path(p).read_bytes()',
        'fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)\nst=os.fstat(fd);assert stat.S_ISREG(st.st_mode) and st.st_size<16777216,"BUNDLE_TYPE_SIZE"\nwith os.fdopen(fd,"rb") as src:raw=src.read(16777217)')
    entry='import sys\nsys.argv=[__file__,'+repr(str(BUNDLE))+','+repr(sha(raw))+','+repr(sha(manifest))+']\nexec(compile('+repr(launcher)+',"<pinned-verifier>","exec"))\n'
    local=Path('/home/hermes/workspace/msp-quota-redis-entry.py');local.write_text(entry);(DOC/'entry.py').write_text(entry)
    h=sha(entry.encode())
    command='quota_stage=$(mktemp -d /var/lib/msp-quota-entry.XXXXXXXX) && install -o root -g root -m 600 '+str(local)+' "$quota_stage/entry.py" && printf \'%s  %s\\n\' '+h+' "$quota_stage/entry.py" | sha256sum -c - && /usr/bin/python3 -I -B "$quota_stage/entry.py"'
    assert len(command.splitlines())==1;subprocess.run(['/bin/bash','-n','-c',command],check=True)
    (DOC/'ROOT_ONE_LINE.txt').write_text(command+'\n')
    summary={'entry_sha256':h,'bundle_sha256':sha(raw),'manifest_sha256':sha(manifest),'bundle_bytes':len(raw),'payload_files':len(json.loads(manifest)['files']),
        'redis_version': '7.0.15 Ubuntu security patched','bundle_local':str(BUNDLE),'state':'PREPARED_NOT_INSTALLED','reproducible_build':'MATCH'}
    (DOC/'PACKAGE_SUMMARY.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary))


if __name__=='__main__':main()
