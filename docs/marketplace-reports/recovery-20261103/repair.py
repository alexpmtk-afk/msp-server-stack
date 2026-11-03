"""Root-only recovery of the exact PR108 partial install at B_PILOT_COPY_CREATED.

No account creation, credential-source reads/copy, recursive chmod, API or gates.
Uses helpers from the independently hash-verified ORIGINAL root snapshot, never
its main(). Expected venv generated-file hashes are embedded by build_recovery.py.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import stat
import sys

OLD_MANIFEST = 'a6d556ae5aa28b8d07893cc9808dbc599d26641b1eeea586c69cc0bd80c2b059'
STAGE = Path('/var/lib/msp-wb-bootstrap-package-eb2ac87f8ad6221c')
RECOVERY = Path('/var/lib/msp-wb-bootstrap-recovery')
GENERATED = {'pyvenv.cfg': '100eb84011f5f5f6a050c283dadd77113c87194fb64e7a3b3cdd04aa0fa77059', 'bin/activate.fish': 'd8d92997dacb3e63f89c051e25f170cbe38ad9c0b71bd5388b2a0b3b75e29e74', 'bin/Activate.ps1': '3795a060dea7d621320d6d841deb37591fadf7f5592c5cb2286f9867af0e91df', 'bin/activate': '5787a1972b6b05e85cc90b047dd611e57211a61d129311bc3e696e4c8e2e15c2', 'bin/activate.csh': '76c9d75d239617f8d5fb1bd227394c86789701144dc2f64022535aab96ced3a1'}
OLD_INSTALL_SHA = '1e4647029674752333a13bebd4d598bce41c51849238ebf8a96f26c905f371e9'


def sha(data): return hashlib.sha256(data).hexdigest()


def verify_and_repair(entries, *, expected_uid=0):
    """Verify ALL regular files before changing ANY. Only listed program modes.

    Keep descriptors open across validation+fchmod; never follow links or chown.
    Caller validates parent directories; expected_uid is only a unit-test seam.
    """
    opened=[]
    try:
        for path, checksum, change in entries:
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            opened.append((Path(path),fd,change))
            st=os.fstat(fd)
            if (not stat.S_ISREG(st.st_mode) or st.st_nlink!=1 or st.st_uid!=expected_uid
                or st.st_gid!=expected_uid or stat.S_IMODE(st.st_mode) not in (0o600,0o644)):
                raise ValueError('unexpected file metadata')
            digest=hashlib.sha256()
            while True:
                chunk=os.read(fd,1024*1024)
                if not chunk:break
                digest.update(chunk)
            if digest.hexdigest()!=checksum:raise ValueError('installed checksum drift')
        # Second full inode/path pass BEFORE the first chmod.
        for path,fd,change in opened:
            st=path.lstat();fst=os.fstat(fd)
            if (st.st_dev,st.st_ino)!=(fst.st_dev,fst.st_ino):raise ValueError('file replacement')
        changed=0
        for path,fd,change in opened:
            if change and stat.S_IMODE(os.fstat(fd).st_mode)!=0o644:
                os.fchmod(fd,0o644);os.fsync(fd);changed+=1
        return changed
    finally:
        for path,fd,change in opened:os.close(fd)


def main():
    if os.geteuid()!=0:
        print('ROOT_REQUIRED;NO_CHANGES');return 2
    phase='VERIFY_SNAPSHOT'
    try:
        # Verify trusted root snapshot BEFORE importing any of its Python helpers.
        for path in [STAGE,*STAGE.parents]:
            st=path.lstat()
            if not stat.S_ISDIR(st.st_mode) or st.st_uid!=0 or st.st_mode&0o022:
                raise ValueError('untrusted snapshot parent')
        source=STAGE/'install.py';st=source.lstat()
        if not stat.S_ISREG(st.st_mode) or st.st_uid!=0 or st.st_nlink!=1 or st.st_mode&0o022:
            raise ValueError('untrusted original installer')
        if sha(source.read_bytes())!=OLD_INSTALL_SHA:raise ValueError('original installer drift')
        spec=importlib.util.spec_from_file_location('original_bootstrap_helpers',source)
        old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
        manifest,mh=old.verify_payload(STAGE)
        if mh!=OLD_MANIFEST:raise ValueError('original manifest drift')
        if sha(Path('/usr/bin/python3').read_bytes())!=old.PYTHON_SHA:
            raise ValueError('system interpreter drift')
        os.umask(0o077)
        # This is the only write helper; explicit mode defeats umask077 for PUBLIC files.
        def write(path,data,mode=0o600):
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
            try:
                with os.fdopen(fd,'wb',closefd=False) as f:
                    f.write(data);f.flush();os.fchmod(fd,mode);os.fsync(fd)
            finally:os.close(fd)
            old.sync_dir(path.parent)
        phase='VERIFY_PARTIAL_STATE'
        if RECOVERY.exists():
            old.trusted(RECOVERY,mode=0o700)
            if (RECOVERY/'DONE.json').exists():
                old.readback(STAGE,OLD_MANIFEST)
                print('ALREADY_RECOVERED_VERIFIED;NO_REEXECUTION');return 0
            raise ValueError('partial recovery: reconciliation required')
        old.ancestors(RECOVERY.parent)
        user=pwd.getpwnam('msp-reports')
        if user.pw_uid==0 or user.pw_gid==0 or user.pw_shell!='/usr/sbin/nologin':
            raise ValueError('unexpected executor identity')
        for directory,uid,mode in [(old.STATE,0,0o700),(old.ARCHIVE,user.pw_uid,0o700),
            (old.BACKUP,0,0o700),(old.PILOT,0,0o700),(old.CONTROL,0,0o755)]:
            old.ancestors(directory.parent);old.trusted(directory,uid=uid,mode=mode)
        # Metadata only. Do not open master or pilot token, do not hash their content.
        old.trusted(old.PILOT/'wb_laser_master.json',mode=0o600)
        old.trusted(old.SOURCE.parent,mode=0o700);old.trusted(old.SOURCE,mode=0o600)
        if (old.CONTROL/'approval.json').exists():raise ValueError('API approval must be absent')
        phases=['BEGIN','IDENTITY_STORAGE_CREATED','A_RUNTIME_STAGED','B_PILOT_COPY_CREATED']
        expected_names={name+'.json' for name in phases}
        if {p.name for p in old.STATE.iterdir()}!=expected_names:
            raise ValueError('unexpected original journal inventory')
        journals={}
        for name in phases:
            p=old.STATE/(name+'.json');old.trusted(p,mode=0o600);raw=p.read_bytes()
            if json.loads(raw)!={'phase':name,'manifest_sha256':OLD_MANIFEST}:
                raise ValueError('unexpected original checkpoint')
            journals[name]=sha(raw)
        if list(old.ARCHIVE.iterdir()) or list(old.BACKUP.iterdir()):
            raise ValueError('unexpected archive/backup content')
        for directory in [old.BASE,old.RELEASE,*[p for p in old.RELEASE.rglob('*') if p.is_dir() and not p.is_symlink()]]:
            old.trusted(directory,mode=0o755)
        code=json.loads((STAGE/'INSTALL_MANIFEST.json').read_text())
        # Exact list:19 Python programs + pilot-plan.json become644.
        names=[*code['files'],'smoke.py','redis_readonly_probe.py','pilot-plan.json','INSTALL_MANIFEST.json']
        entries=[(old.RELEASE/n,sha((STAGE/n).read_bytes()),n!='INSTALL_MANIFEST.json') for n in names]
        unit=(STAGE/'staged.service.in').read_text().replace('@RELEASE_SHA@',old.CODE)+'\nPrivateNetwork=yes\n'
        entries.append((old.UNIT,sha(unit.encode()),False))  # systemd reads root0600; no chmod needed.
        for name,data in old.wheel_files(STAGE/'redis-8.1.0-py3-none-any.whl').items():
            entries.append((old.RELEASE/'.venv/lib/python3.12/site-packages'/name,sha(data),False))
        for name,digest in GENERATED.items():entries.append((old.RELEASE/'.venv'/name,digest,False))
        expected_files={Path(p) for p,_,_ in entries if str(p).startswith(str(old.RELEASE)+'/')}
        expected_links={old.RELEASE/'.venv/lib64':'lib',old.RELEASE/'.venv/bin/python':'python3',
            old.RELEASE/'.venv/bin/python3':'/usr/bin/python3',old.RELEASE/'.venv/bin/python3.12':'python3'}
        actual=set()
        for p in old.RELEASE.rglob('*'):
            if p.is_symlink():
                if p not in expected_links or os.readlink(p)!=expected_links[p]:raise ValueError('runtime link drift')
            elif p.is_file():actual.add(p)
            elif not p.is_dir():raise ValueError('unexpected inode')
        if actual!=expected_files or any(not p.is_symlink() for p in expected_links):
            raise ValueError('release file inventory drift')
        # Open/validate before any mutation, then repairs only the literal list.
        before=old.health()
        phase='VERIFY_AND_REPAIR_PROGRAM_MODES'
        changed=verify_and_repair(entries)
        old.mkdir_new(RECOVERY,0o700)
        write(RECOVERY/'MODES_REPAIRED.json',json.dumps({'changed':changed,'original_manifest':OLD_MANIFEST}).encode())
        phase='A_UNIT_SMOKE'
        old.run(['/usr/bin/systemd-analyze','verify',str(old.UNIT)])
        # Unit bytes were already verified and unchanged. No daemon reload is needed.
        args=['/usr/bin/systemd-run','--quiet','--wait','--pipe','--collect',
            '--unit=msp-wb-recovery-smoke','-p','User=msp-reports','-p','Group=msp-reports',
            '-p','UMask=0077','-p','PrivateNetwork=yes','-p','IPAddressDeny=any',
            '-p','NoNewPrivileges=yes','-p','CapabilityBoundingSet=','-p','ProtectSystem=strict',
            '-p','ProtectHome=yes','-p','PrivateTmp=yes','-p','ReadWritePaths='+str(old.ARCHIVE),
            '-p','LoadCredential=cabinets.json:'+str(old.PILOT/'wb_laser_master.json'),
            str(old.RELEASE/'.venv/bin/python'),'-B',str(old.RELEASE/'smoke.py')]
        smoke=json.loads(old.run(args))
        if smoke.get('status')!='PASS':raise ValueError('smoke did not pass')
        write(RECOVERY/'SMOKE_PASS.json',json.dumps(smoke).encode())
        phase='A_BACKUP_RESTORE'
        if list(old.ARCHIVE.iterdir()):raise ValueError('unexpected smoke leftovers')
        for name in ['initial-empty-snapshot','restore-check']:old.mkdir_new(old.BACKUP/name,0o700)
        proof=b'SYNTHETIC recovery backup restore check; not a WB report\n'
        write(old.BACKUP/'initial-empty-snapshot/proof',proof)
        write(old.BACKUP/'restore-check/proof',(old.BACKUP/'initial-empty-snapshot/proof').read_bytes())
        if (old.BACKUP/'restore-check/proof').read_bytes()!=proof:raise ValueError('restore mismatch')
        for name in ['initial-empty-snapshot','restore-check']:
            (old.BACKUP/name/'proof').unlink();old.sync_dir(old.BACKUP/name)
        old.sync_dir(old.BACKUP)
        write(RECOVERY/'BACKUP_PASS.json',b'{"scope":"synthetic roundtrip; initial empty archive; offhost pending"}')
        phase='C_READONLY'
        config=old.SOURCE.parent/'redis-readonly.env'
        cstatus='NOT_CONFIGURED_APPROVED_BACKEND_REQUIRED'
        if config.exists():
            old.trusted(config,mode=0o600)
            allowed={'MARKETPLACE_MCP_REDIS_URL','MARKETPLACE_MCP_REDIS_HOST','MARKETPLACE_MCP_REDIS_PORT',
                'MARKETPLACE_MCP_REDIS_PASSWORD','MARKETPLACE_MCP_REDIS_DB','MARKETPLACE_MCP_REDIS_TLS','MARKETPLACE_MCP_REDIS_CA_CERT'}
            seen=set()
            for line in config.read_text().splitlines():
                if not line.strip() or line.lstrip().startswith('#'):continue
                key,sep,value=line.partition('=')
                if not sep or key not in allowed or key in seen or '\\' in value:raise ValueError('unexpected Redis config')
                seen.add(key)
            if not seen:raise ValueError('empty approved Redis config')
            result=json.loads(old.run(['/usr/bin/systemd-run','--quiet','--wait','--pipe','--collect',
                '--unit=msp-wb-recovery-redis-readonly','-p','User=msp-reports','-p','Group=msp-reports',
                '-p','EnvironmentFile='+str(config),'-p','NoNewPrivileges=yes','-p','CapabilityBoundingSet=',
                '-p','ProtectSystem=strict','-p','ProtectHome=yes',str(old.RELEASE/'.venv/bin/python'),
                '-B',str(old.RELEASE/'redis_readonly_probe.py'),'--release',str(old.RELEASE)]))
            if result.get('read_only_protocol_check')!='PASS':raise ValueError('Redis check failed')
            cstatus='READ_ONLY_PASS_LUA_NOT_TESTED'
        phase='VERIFY_AND_COMPLETE'
        if old.health()!=before:raise ValueError('neighbor health drift')
        # Existing journal byte content and private modes stay unchanged.
        for name,h in journals.items():
            p=old.STATE/(name+'.json');old.trusted(p,mode=0o600)
            if sha(p.read_bytes())!=h:raise ValueError('original journal changed')
        old.trusted(old.PILOT/'wb_laser_master.json',mode=0o600)
        installed=[{'path':str(p),'sha256':h,'mode':stat.S_IMODE(p.stat().st_mode)} for p,h,_ in entries]
        receipt={'state':'INSTALLED_API_BLOCKED','manifest_sha256':OLD_MANIFEST,
            'uid':user.pw_uid,'gid':user.pw_gid,'A':'PASS','B':'REUSED_NOT_RECOPIED','C':cstatus,
            'storage_smoke':smoke,'backup':'SYNTHETIC_ROUNDTRIP_INITIAL_EMPTY_ARCHIVE_OFFHOST_PENDING',
            'installed_files':installed,'runtime_links':[{'path':str(p),'target':v} for p,v in expected_links.items()],
            'provider_calls':0,'api_enabled':False,'recovery':'PROGRAM_MODE_REPAIR'}
        # New completion only; never replaces pre-existing receipts/counters.
        write(old.STATE/'complete.json',json.dumps(receipt,indent=2).encode())
        public={k:v for k,v in receipt.items() if k not in ('installed_files','runtime_links')}
        write(old.RELEASE/'bootstrap-result.json',json.dumps(public,indent=2).encode(),0o644)
        write(RECOVERY/'DONE.json',json.dumps(public).encode())
        old.readback(STAGE,OLD_MANIFEST)
        print(json.dumps(public));return 0
    except Exception as exc:
        print(json.dumps({'status':'STOP_OR_UNCERTAIN','phase':phase,'error_type':type(exc).__name__,
                          'api_enabled':False,'auto_retry':False}));return 1


if __name__=='__main__':raise SystemExit(main())
