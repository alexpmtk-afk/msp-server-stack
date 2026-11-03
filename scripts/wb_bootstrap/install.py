"""Root-only, offline ABC bootstrap. No provider calls, gate, timer or restart.

Executed ONLY from a hash-verified root-owned bundle. Fail-stop: partial state
is retained in a root-only journal; never overwrite an unknown installation.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import shutil
import stat
import subprocess
import sys
import venv
import zipfile

CODE = 'c1fee070e9efa0c925a78f266fdf03cb12a173cf'
BASE = Path('/opt/mcp/projects/msp-marketplace-reports-releases')
RELEASE = BASE / CODE
ARCHIVE = Path('/opt/mcp/data/msp-marketplace-reports')
BACKUP = Path('/opt/mcp/backups/msp-marketplace-reports')
PILOT = Path('/etc/msp-marketplace-reports-pilot')
CONTROL = Path('/etc/msp-marketplace-reports-executor')
UNIT = Path('/etc/systemd/system/msp-wb-pilot.service')
STATE = Path('/var/lib/msp-wb-bootstrap')
SOURCE = Path('/etc/msp-marketplace-reports/cabinets.json')
PYTHON_SHA = 'e50d468e8b0adfb05733f5b87b3cff34829c4a8c1aea50c865aa8bdfe4bb150f'
NEIGHBORS = ('hermes-gateway.service', 'msp-devexec.service', 'msp-devexec-maint.service',
             'hermes-dashboard.service')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def trusted(path, *, uid=0, mode=None):
    st = path.lstat()
    if stat.S_ISLNK(st.st_mode) or st.st_uid != uid or st.st_mode & 0o022:
        raise ValueError('untrusted path')
    if mode is not None and stat.S_IMODE(st.st_mode) != mode:
        raise ValueError('unexpected mode')
    if stat.S_ISREG(st.st_mode) and st.st_nlink != 1:
        raise ValueError('unexpected links')
    if not stat.S_ISREG(st.st_mode) and not stat.S_ISDIR(st.st_mode):
        raise ValueError('unexpected inode')
    return st


def ancestors(path):
    for p in [path, *path.parents]:
        if p.exists() or p.is_symlink():
            trusted(p)


def rel(name):
    if type(name) is not str or name.startswith('/') or '\\' in name or any(
            x in ('', '.', '..') for x in name.split('/')):
        raise ValueError('unsafe payload path')
    return name


def verify_payload(root):
    ancestors(root)
    raw = (root / 'BUNDLE_MANIFEST.json').read_bytes()
    manifest = json.loads(raw)
    expected = {entry['path']: entry['sha256'] for entry in manifest['files']}
    if len(expected) != len(manifest['files']):
        raise ValueError('duplicate file')
    actual = set()
    for f in root.rglob('*'):
        trusted(f)
        if f.is_file():
            actual.add(str(f.relative_to(root)))
    if actual != set(expected) | {'BUNDLE_MANIFEST.json'}:
        raise ValueError('payload inventory mismatch')
    for name, checksum in expected.items():
        rel(name)
        if sha((root/name).read_bytes()) != checksum:
            raise ValueError('payload hash mismatch')
    return manifest, sha(raw)


def write_new(path, data, mode=0o600):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as f:
            f.write(data); f.flush(); os.fsync(fd)
    finally:
        os.close(fd)
    sync_dir(path.parent)


def sync_dir(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def mkdir_new(path, mode, uid=0, gid=0):
    path.mkdir(mode=mode)
    os.chown(path, uid, gid)
    os.chmod(path, mode)
    sync_dir(path.parent)


def run(argv):
    # Do not relay subprocess stdout/stderr: may contain private diagnostics.
    result = subprocess.run(argv, capture_output=True, timeout=180,
                            env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin', 'LANG':'C.UTF-8'})
    if result.returncode:
        raise RuntimeError('subprocess failed: '+Path(argv[0]).name)
    return result.stdout


def health():
    result = {}
    for unit in NEIGHBORS:
        result[unit] = run(['/usr/bin/systemctl','show',unit,
            '--property=LoadState,ActiveState,SubState,MainPID,NRestarts']).decode()
    return result


def wheel_files(path):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if len(names) != len(set(names)) or len(names) > 2000:
            raise ValueError('wheel inventory')
        data = {}
        for info in z.infolist():
            if info.is_dir():
                continue
            name = rel(info.filename)
            if not (name.startswith('redis/') or name.startswith('redis-8.1.0.dist-info/')):
                raise ValueError('unexpected wheel destination')
            if stat.S_ISLNK(info.external_attr >> 16) or info.file_size > 8*1024*1024:
                raise ValueError('unsafe wheel member')
            data[name] = z.read(info)
        return data


def readback(root, manifest_sha):
    receipt = json.loads((STATE/'complete.json').read_text())
    if receipt['manifest_sha256'] != manifest_sha:
        raise ValueError('different completed installation')
    for entry in receipt['installed_files']:
        p=Path(entry['path']); trusted(p, mode=entry['mode'])
        if sha(p.read_bytes()) != entry['sha256']:
            raise ValueError('installed hash mismatch')
    trusted(ARCHIVE, uid=receipt['uid'], mode=0o700)
    trusted(PILOT, mode=0o700); trusted(PILOT/'wb_laser_master.json', mode=0o600)
    if (CONTROL/'approval.json').exists():
        raise ValueError('API approval unexpectedly exists')
    for entry in receipt['runtime_links']:
        p=Path(entry['path'])
        if not p.is_symlink() or os.readlink(p)!=entry['target']:
            raise ValueError('runtime link drift')
    return receipt


def main():
    if os.geteuid() != 0:
        print('ROOT_REQUIRED;NO_CHANGES'); return 2
    os.umask(0o077)
    root=Path(__file__).resolve().parent
    phase='VERIFY'
    try:
        manifest, manifest_sha=verify_payload(root)
        if '--rollback-unit' in sys.argv[1:]:
            trusted(STATE,mode=0o700)
            receipt=readback(root,manifest_sha)
            state=run(['/usr/bin/systemctl','show','msp-wb-pilot.service','--property=ActiveState','--value']).strip()
            if state not in (b'inactive',b'failed'): raise ValueError('unit not stopped')
            # readback already proved the exact unit hash, no unknown unit deletion.
            UNIT.unlink();sync_dir(UNIT.parent)
            run(['/usr/bin/systemctl','daemon-reload'])
            write_new(STATE/'unit-removed.json',b'{"state":"STOPPED_DATA_AND_SECRETS_PRESERVED"}')
            print('ROLLBACK_UNIT_REMOVED;ACCOUNT_CODE_DATA_SECRETS_PRESERVED');return 0
        if STATE.exists():
            trusted(STATE, mode=0o700)
            if (STATE/'complete.json').exists():
                readback(root,manifest_sha)
                print('ALREADY_INSTALLED_VERIFIED;NO_REEXECUTION'); return 0
            raise ValueError('partial state: reconciliation required')
        # Entire preflight BEFORE changes, user creation or secret reads.
        phase='PREFLIGHT'
        if Path('/usr/bin/python3').resolve() != Path(sys.executable).resolve():
            raise ValueError('system Python required')
        if sha(Path(sys.executable).read_bytes()) != PYTHON_SHA or sys.version_info[:2] != (3,12):
            raise ValueError('interpreter drift')
        for p in [BASE, ARCHIVE, BACKUP, PILOT, CONTROL, STATE, UNIT]:
            ancestors(p.parent)
            if p.exists() or p.is_symlink():
                raise ValueError('target already exists')
        for base in ['/etc/systemd/system','/run/systemd/system','/usr/lib/systemd/system','/lib/systemd/system']:
            for suffix in ['msp-wb-pilot.service','msp-wb-pilot.service.d']:
                candidate=Path(base)/suffix
                if candidate.exists() or candidate.is_symlink():
                    raise ValueError('existing unit or drop-in')
        import grp
        try: pwd.getpwnam('msp-reports')
        except KeyError: pass
        else: raise ValueError('user already exists')
        try: grp.getgrnam('msp-reports')
        except KeyError: pass
        else: raise ValueError('group already exists')
        for parent in [Path('/opt/mcp/projects'),Path('/opt/mcp/data'),Path('/opt/mcp/backups'),Path('/var/lib')]:
            trusted(parent)
            if shutil.disk_usage(parent).free < 1024**3 or os.statvfs(parent).f_favail < 10000:
                raise ValueError('bootstrap storage reserve unavailable')
        trusted(Path('/etc/msp-marketplace-reports'),mode=0o700)
        # Source metadata only, no content before A. Original contract is fixed.
        trusted(SOURCE,mode=0o600)
        for p in ['/usr/sbin/useradd','/usr/sbin/groupadd','/usr/bin/systemctl','/usr/bin/systemd-run','/usr/bin/systemd-analyze']:
            if not Path(p).is_file(): raise ValueError('missing tool')
        code=json.loads((root/'INSTALL_MANIFEST.json').read_text())
        for name,h in code['files'].items():
            if sha((root/name).read_bytes()) != h: raise ValueError('code mismatch')
        wheel=wheel_files(root/'redis-8.1.0-py3-none-any.whl')
        before=health()
        mkdir_new(STATE,0o700)
        def checkpoint(name):
            write_new(STATE/(name+'.json'),json.dumps({'phase':name,'manifest_sha256':manifest_sha}).encode())
        checkpoint('BEGIN')
        phase='A_IDENTITY_STORAGE'
        run(['/usr/sbin/groupadd','--system','msp-reports'])
        run(['/usr/sbin/useradd','--system','--gid','msp-reports','--no-create-home',
             '--home-dir','/nonexistent','--shell','/usr/sbin/nologin','msp-reports'])
        user=pwd.getpwnam('msp-reports')
        mkdir_new(BASE,0o755); mkdir_new(RELEASE,0o755)
        mkdir_new(ARCHIVE,0o700,user.pw_uid,user.pw_gid)
        mkdir_new(BACKUP,0o700); mkdir_new(CONTROL,0o755); mkdir_new(PILOT,0o700)
        checkpoint('IDENTITY_STORAGE_CREATED')
        installed=[]
        def place(target,data,mode=0o644):
            write_new(target,data,mode)
            installed.append({'path':str(target),'sha256':sha(data),'mode':mode})
        for name in [*code['files'],'pilot-plan.json','smoke.py','redis_readonly_probe.py','INSTALL_MANIFEST.json']:
            target=RELEASE/name
            # All destination components lie within the fresh root-controlled release.
            missing=[]; parent=target.parent
            while not parent.exists(): missing.append(parent); parent=parent.parent
            for directory in reversed(missing): mkdir_new(directory,0o755)
            place(target,(root/name).read_bytes())
        phase='A_RUNTIME'
        venv.EnvBuilder(with_pip=False,symlinks=True).create(RELEASE/'.venv')
        site=RELEASE/'.venv/lib/python3.12/site-packages'
        for name,data in wheel.items():
            target=site/name
            target.parent.mkdir(parents=True,exist_ok=True)
            write_new(target,data,0o644)
        # venv is created under umask0077; make ONLY fresh runtime traversable.
        for p in (RELEASE/'.venv').rglob('*'):
            if p.is_symlink():
                if p == RELEASE/'.venv/lib64' and os.readlink(p)=='lib':
                    pass
                elif p.parent==RELEASE/'.venv/bin' and p.name in ('python','python3','python3.12') and p.resolve()==Path('/usr/bin/python3').resolve():
                    pass
                else:
                    raise ValueError('unexpected venv link')
            elif p.is_dir(): os.chmod(p,0o755)
            elif p.is_file(): os.chmod(p,0o644)
        os.chmod(RELEASE/'.venv',0o755)
        # No pip/scripts installed; python links point to pinned system runtime.
        run([str(RELEASE/'.venv/bin/python'),'-I','-B','-c',
             'import redis; assert redis.__version__=="8.1.0"'])
        checkpoint('A_RUNTIME_STAGED')
        phase='B_PILOT_COPY'
        selector=root/'select_pilot_credential.py'
        spec=importlib.util.spec_from_file_location('selector',selector)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        source=SOURCE
        st=source.stat(); original=sha(source.read_bytes())
        module.copy_one(source.parent,PILOT)
        if sha(source.read_bytes())!=original or source.stat().st_mode!=st.st_mode or source.stat().st_uid!=st.st_uid:
            raise ValueError('source changed during copy')
        checkpoint('B_PILOT_COPY_CREATED')
        phase='A_UNIT_SMOKE'
        unit=(root/'staged.service.in').read_text().replace('@RELEASE_SHA@',CODE)+'\nPrivateNetwork=yes\n'
        place(UNIT,unit.encode())
        run(['/usr/bin/systemd-analyze','verify',str(UNIT)])
        run(['/usr/bin/systemctl','daemon-reload'])
        # Dedicated transient NEW smoke only. Never start/enable downloader or neighbors.
        args=['/usr/bin/systemd-run','--quiet','--wait','--pipe','--collect',
              '--unit=msp-wb-bootstrap-smoke',
              '-p','User=msp-reports','-p','Group=msp-reports','-p','UMask=0077',
              '-p','PrivateNetwork=yes','-p','IPAddressDeny=any','-p','NoNewPrivileges=yes',
              '-p','CapabilityBoundingSet=','-p','ProtectSystem=strict','-p','ProtectHome=yes',
              '-p','PrivateTmp=yes','-p','ReadWritePaths='+str(ARCHIVE),
              '-p','LoadCredential=cabinets.json:'+str(PILOT/'wb_laser_master.json'),
              str(RELEASE/'.venv/bin/python'),'-B',str(RELEASE/'smoke.py')]
        smoke=json.loads(run(args))
        if smoke.get('status')!='PASS': raise ValueError('smoke failed')
        checkpoint('A_B_SMOKE_PASS')
        phase='A_BACKUP_RESTORE'
        # Archive is empty after smoke; snapshot refuses symlink/unknown entries.
        if list(ARCHIVE.iterdir()): raise ValueError('unexpected archive data')
        mkdir_new(BACKUP/'initial-empty-snapshot',0o700)
        mkdir_new(BACKUP/'restore-check',0o700)
        if list((BACKUP/'initial-empty-snapshot').iterdir()) or list((BACKUP/'restore-check').iterdir()):
            raise ValueError('initial restore verification failed')
        proof=b'SYNTHETIC backup restore check; not a provider report\n'
        write_new(BACKUP/'initial-empty-snapshot/proof',proof)
        write_new(BACKUP/'restore-check/proof',(BACKUP/'initial-empty-snapshot/proof').read_bytes())
        if sha((BACKUP/'restore-check/proof').read_bytes())!=sha(proof):
            raise ValueError('restore hash failed')
        (BACKUP/'initial-empty-snapshot/proof').unlink()
        (BACKUP/'restore-check/proof').unlink()
        sync_dir(BACKUP/'initial-empty-snapshot');sync_dir(BACKUP/'restore-check')
        sync_dir(BACKUP)
        phase='C_READONLY'
        config=Path('/etc/msp-marketplace-reports/redis-readonly.env')
        cstatus='NOT_CONFIGURED_APPROVED_BACKEND_REQUIRED'
        if config.exists():
            trusted(config,mode=0o600)
            # EnvironmentFile is root-owned but still accept only Redis variables;
            # no PYTHONPATH/LD_PRELOAD/gates or shell expansion from this source.
            allowed={'MARKETPLACE_MCP_REDIS_URL','MARKETPLACE_MCP_REDIS_HOST',
                'MARKETPLACE_MCP_REDIS_PORT','MARKETPLACE_MCP_REDIS_PASSWORD',
                'MARKETPLACE_MCP_REDIS_DB','MARKETPLACE_MCP_REDIS_TLS','MARKETPLACE_MCP_REDIS_CA_CERT'}
            seen=set()
            for line in config.read_text().splitlines():
                if not line.strip() or line.lstrip().startswith('#'): continue
                key,sep,value=line.partition('=')
                if not sep or key not in allowed or key in seen or '\\' in value:
                    raise ValueError('Redis config requires simple approved assignments')
                seen.add(key)
            if not seen: raise ValueError('empty Redis config')
            result=run(['/usr/bin/systemd-run','--quiet','--wait','--pipe','--collect',
                '--unit=msp-wb-redis-readonly','-p','User=msp-reports','-p','Group=msp-reports',
                '-p','EnvironmentFile='+str(config),'-p','NoNewPrivileges=yes',
                '-p','CapabilityBoundingSet=','-p','ProtectSystem=strict','-p','ProtectHome=yes',
                str(RELEASE/'.venv/bin/python'),'-B',str(RELEASE/'redis_readonly_probe.py'),
                '--release',str(RELEASE)])
            result=json.loads(result)
            if result.get('read_only_protocol_check')!='PASS': raise ValueError('Redis read-only failed')
            cstatus='READ_ONLY_PASS_LUA_NOT_TESTED'
        if health()!=before: raise ValueError('neighbor health changed: reconciliation required')
        if (CONTROL/'approval.json').exists(): raise ValueError('approval must remain absent')
        # Readback inventory covers generated venv files too, not only sources.
        for f in (RELEASE/'.venv').rglob('*'):
            if f.is_file() and not f.is_symlink():
                installed.append({'path':str(f),'sha256':sha(f.read_bytes()),
                                  'mode':stat.S_IMODE(f.stat().st_mode)})
        receipt={'state':'INSTALLED_API_BLOCKED','code_sha':CODE,'manifest_sha256':manifest_sha,
                 'uid':user.pw_uid,'gid':user.pw_gid,'A':'PASS','B':'PASS','C':cstatus,
                 'storage_smoke':smoke,'backup':'EMPTY_INITIAL_SNAPSHOT_ONLY_OFFHOST_PENDING',
                 'installed_files':installed,'runtime_links':[{'path':str(f),'target':os.readlink(f)} for f in (RELEASE/'.venv').rglob('*') if f.is_symlink()],'neighbor_health':'UNCHANGED',
                 'provider_calls':0,'api_enabled':False}
        write_new(STATE/'complete.json',json.dumps(receipt,indent=2).encode())
        # Public redacted readback excludes secret hashes/content, Redis address.
        public={k:v for k,v in receipt.items() if k not in ('installed_files','runtime_links')}
        place(RELEASE/'bootstrap-result.json',json.dumps(public,indent=2).encode())
        print(json.dumps(public))
        return 0
    except Exception as exc:
        print(json.dumps({'status':'STOP_OR_UNCERTAIN','phase':phase,'error_type':type(exc).__name__,
                          'auto_retry':False,'api_enabled':False}))
        return 1


if __name__=='__main__':
    raise SystemExit(main())
