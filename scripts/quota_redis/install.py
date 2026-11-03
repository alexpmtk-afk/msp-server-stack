"""Root-only Redis infrastructure installer. No WB/Ozon calls, A/B or report timers.

Run ONLY from a complete hash-verified root-owned snapshot after review. Refuse
unknown existing installation/partial state, never replace generated credentials.
"""
import importlib.util
import json
import os
from pathlib import Path
import pwd
import grp
import secrets
import socket
import stat
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import *
UNIT=Path('/etc/systemd/system')/SERVICE
APPROVAL=Path('/etc/msp-marketplace-reports-executor/approval.json')
NEIGHBORS=('hermes-gateway.service','msp-devexec.service','msp-devexec-maint.service','hermes-dashboard.service','msp-wb-pilot.service')


def run(args):
    p=subprocess.run(args,capture_output=True,timeout=120,env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C.UTF-8'})
    if p.returncode:raise RuntimeError('command failed: '+Path(args[0]).name)
    return p.stdout


def parents(p):
    for x in [p,*p.parents]:
        if x.exists() or x.is_symlink():trusted(x)


def mkdir(p,mode,uid=0,gid=0):
    p.mkdir(mode=mode);os.chown(p,uid,gid);os.chmod(p,mode);syncdir(p.parent)


def health():
    return {n:run(['/usr/bin/systemctl','show',n,'--property=LoadState,ActiveState,SubState,MainPID,NRestarts']).decode() for n in NEIGHBORS}


def verify_bundle(root):
    parents(root)
    raw=(root/'BUNDLE_MANIFEST.json').read_bytes();doc=json.loads(raw)
    expected={x['path']:x for x in doc['files']}
    if len(expected)!=len(doc['files']):raise ValueError('duplicate manifest')
    actual=set()
    for p in root.rglob('*'):
        trusted(p)
        if p.is_file():actual.add(str(p.relative_to(root)))
    if actual!=set(expected)|{'BUNDLE_MANIFEST.json'}:raise ValueError('snapshot inventory')
    for name,entry in expected.items():
        if name.startswith('/') or any(x in ('','..','.') for x in name.split('/')):raise ValueError('manifest path')
        if sha((root/name).read_bytes())!=entry['sha256']:raise ValueError('snapshot checksum')
    return doc,sha(raw)


def verify_app(root):
    # Metadata and accepted code only; never open master/pilot WB credentials.
    doc=json.loads((root/'app-manifest.json').read_text())
    for name,digest in doc['files'].items():
        p=RELEASE/name;parents(p.parent);trusted(p,mode=0o644)
        if sha(p.read_bytes())!=digest:raise ValueError('A/B installed code drift')
    p=RELEASE/'redis_readonly_probe.py';trusted(p,mode=0o644)
    if sha(p.read_bytes())!=doc['readonly_probe_sha256']:raise ValueError('probe drift')
    trusted(RELEASE/'bootstrap-result.json',mode=0o644)
    result=json.loads((RELEASE/'bootstrap-result.json').read_text())
    if result.get('A')!='PASS' or result.get('B') not in ('PASS','REUSED_NOT_RECOPIED') or result.get('api_enabled') is not False:
        raise ValueError('A/B prerequisite not accepted')
    if APPROVAL.exists():raise ValueError('API approval must remain absent')
    user=pwd.getpwnam('msp-reports')
    if user.pw_uid!=995 or user.pw_gid!=985:raise ValueError('executor identity drift')


def readonly_probe():
    data=run(['/usr/bin/systemd-run','--quiet','--wait','--pipe','--collect',
        '--unit=msp-quota-redis-readonly-check','-p','User=msp-reports','-p','Group=msp-reports',
        '-p','EnvironmentFile='+str(READONLY),'-p','NoNewPrivileges=yes','-p','CapabilityBoundingSet=',
        '-p','ProtectSystem=strict','-p','ProtectHome=yes','-p','PrivateTmp=yes',
        str(RELEASE/'.venv/bin/python'),'-B',str(RELEASE/'redis_readonly_probe.py'),'--release',str(RELEASE)])
    result=json.loads(data)
    if result.get('read_only_protocol_check')!='PASS':raise ValueError('readonly check failed')
    if result.get('client_version')!='8.1.0' or any(case.get('server_version')!='7.0.15' for case in result.get('cases',[])):
        raise ValueError('reviewed client/server version drift')
    return result


def check_existing(manifest_sha):
    trusted(STATE,mode=0o700);r=STATE/'complete.json';trusted(r,mode=0o600);doc=json.loads(r.read_text())
    if doc['bundle_manifest_sha256']!=manifest_sha:raise ValueError('other installation')
    for entry in doc['files']:
        p=Path(entry['path']);trusted(p,uid=entry['uid'],mode=entry['mode'])
        if sha(p.read_bytes())!=entry['sha256'] or p.stat().st_gid!=entry['gid']:raise ValueError('installed drift')
    for entry in doc['directories']:
        p=Path(entry['path']);trusted(p,uid=entry['uid'],mode=entry['mode'])
        if p.stat().st_gid!=entry['gid']:raise ValueError('directory group drift')
    if (CONFIG/'bootstrap-permit').exists():raise ValueError('bootstrap permit not closed')
    trusted(CONFIG/'initialized',mode=0o640)
    guard(DATA,CONFIG/'initialized',CONFIG/'bootstrap-permit',pwd.getpwnam(USER).pw_uid,hold=CONFIG/'HOLD')
    if APPROVAL.exists():raise ValueError('API gate changed; no automated action')
    return doc


def main():
    if os.geteuid()!=0:print('ROOT_REQUIRED;NO_CHANGES');return 2
    phase='VERIFY'
    try:
        os.umask(0o077)
        root=Path(__file__).resolve().parent
        manifest,manifest_sha=verify_bundle(root)
        if STATE.exists():
            if (STATE/'complete.json').exists():
                check_existing(manifest_sha)
                print('ALREADY_INSTALLED_CHECKSUMS_MATCH;NO_RESTART_OR_PASSWORD_CHANGE');return 0
            raise ValueError('partial install; reconcile, no automatic retry')
        phase='PREFLIGHT'
        verify_app(root)
        lock=json.loads((root/'runtime-lock.json').read_text())
        for name,digest in lock['host_libraries'].items():
            p=Path(name);parents(p.parent);trusted(p)
            if sha(p.read_bytes())!=digest:raise ValueError('host library drift')
        targets=[PREFIX,CONFIG,DATA,STATE,BACKUP,READONLY,RUNTIME,UNIT]
        for p in targets:
            parents(p.parent)
            if p.exists() or p.is_symlink():raise ValueError('existing target')
        for base in ['/etc/systemd/system','/run/systemd/system','/usr/lib/systemd/system','/lib/systemd/system']:
            for suffix in [SERVICE,SERVICE+'.d']:
                p=Path(base)/suffix
                if p.exists() or p.is_symlink():raise ValueError('existing Redis unit/dropin')
        for lookup in [pwd.getpwnam,grp.getgrnam]:
            try:lookup(USER)
            except KeyError:pass
            else:raise ValueError('Redis account already exists')
        probe=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        try:probe.bind(('127.0.0.1',PORT))
        finally:probe.close()
        import shutil
        for parent in [PREFIX.parent,DATA.parent,BACKUP.parent]:
            if shutil.disk_usage(parent).free<256*1024*1024 or os.statvfs(parent).f_favail<5000:
                raise ValueError('insufficient provisioning storage reserve')
        available=next(int(line.split()[1]) for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:'))
        if available<512*1024:raise ValueError('insufficient memory headroom')
        before=health()
        mkdir(STATE,0o700)
        def checkpoint(name):write_new(STATE/(name+'.json'),json.dumps({'phase':name,'bundle_manifest_sha256':manifest_sha}).encode())
        checkpoint('BEGIN')
        phase='INSTALL_NEW_REDIS_ONLY'
        run(['/usr/sbin/groupadd','--system',USER])
        run(['/usr/sbin/useradd','--system','--gid',USER,'--no-create-home','--home-dir','/nonexistent','--shell','/usr/sbin/nologin',USER])
        server=pwd.getpwnam(USER)
        mkdir(PREFIX,0o755);mkdir(PREFIX/'bin',0o755);mkdir(PREFIX/'lib',0o755);mkdir(PREFIX/'licenses',0o755)
        mkdir(CONFIG,0o750,0,server.pw_gid);mkdir(DATA,0o700,server.pw_uid,server.pw_gid);mkdir(BACKUP,0o700)
        installed=[]
        def put(p,data,mode=0o600,uid=0,gid=0):
            write_new(p,data,mode,uid,gid)
            installed.append({'path':str(p),'sha256':sha(data),'mode':mode,'uid':uid,'gid':gid})
        for entry in manifest['files']:
            name=entry['path']
            if name.startswith(('bin/','lib/','licenses/')) or name in ('common.py','guard.py','manage.py'):
                put(PREFIX/name,(root/name).read_bytes(),entry['mode'])
        checkpoint('RUNTIME_CREATED')
        phase='GENERATE_PRIVATE_CONFIG'
        runtime_password=secrets.token_hex(32);ro_password=secrets.token_hex(32)
        put(CONFIG/'users.acl',acl_text(runtime_password,ro_password).encode(),0o640,0,server.pw_gid)
        put(CONFIG/'redis.conf',config_text(DATA,CONFIG/'users.acl').encode(),0o640,0,server.pw_gid)
        put(READONLY,('MARKETPLACE_MCP_REDIS_URL=redis://quota_readonly:'+ro_password+'@127.0.0.1:'+str(PORT)+'/0\n').encode())
        put(RUNTIME,('MARKETPLACE_MCP_REDIS_URL=redis://quota_runtime:'+runtime_password+'@127.0.0.1:'+str(PORT)+'/0\nMARKETPLACE_REQUIRE_REDIS=1\n').encode())
        # Temporary root-owned permit; service user cannot recreate it.
        write_new(CONFIG/'bootstrap-permit',b'FIRST_EMPTY_START_ONLY\n',0o640,0,server.pw_gid)
        put(UNIT,(root/'service.in').read_bytes(),0o644)
        run(['/usr/bin/systemd-analyze','verify',str(UNIT)])
        checkpoint('CONFIG_CREATED')
        phase='START_NEW_REDIS'
        run(['/usr/bin/systemctl','daemon-reload'])
        run(['/usr/bin/systemctl','start',SERVICE])
        # Redis first AOF initialization is local infrastructure state, not quota reservations.
        aof=DATA/'appendonlydir/appendonly.aof.manifest'
        deadline=time.monotonic()+10
        while not aof.exists() and time.monotonic()<deadline:time.sleep(.05)
        trusted(aof,uid=server.pw_uid)
        if not aof.read_bytes():raise ValueError('AOF not initialized')
        put(CONFIG/'initialized',b'REQUIRE_EXISTING_AOF_ON_ALL_FUTURE_STARTS\n',0o640,0,server.pw_gid)
        (CONFIG/'bootstrap-permit').unlink();syncdir(CONFIG)
        guard(DATA,CONFIG/'initialized',CONFIG/'bootstrap-permit',server.pw_uid,hold=CONFIG/'HOLD')
        checkpoint('PERSISTENCE_INITIALIZED')
        phase='READ_ONLY_C'
        assert_local_listener(run(['/usr/bin/ss','-ltnH']).decode())
        result=readonly_probe()
        checkpoint('READONLY_PASS')
        # Enable only this Redis service at boot; no report timer/start/flag.
        run(['/usr/bin/systemctl','enable',SERVICE])
        if health()!=before:raise ValueError('neighbor health drift')
        if APPROVAL.exists():raise ValueError('API must remain blocked')
        receipt={'state':'REDIS_INSTALLED_PROVIDER_BLOCKED','bundle_manifest_sha256':manifest_sha,
            'C':'READ_ONLY_PASS_LUA_TESTED_ONLY_OFFLINE','redis_version':result['cases'][0]['server_version'],
            'files':installed,'directories':[{'path':str(p),'uid':p.stat().st_uid,'gid':p.stat().st_gid,'mode':stat.S_IMODE(p.stat().st_mode)} for p in [PREFIX,PREFIX/'bin',PREFIX/'lib',PREFIX/'licenses',CONFIG,DATA,STATE,BACKUP]],'provider_calls':0,'live_quota_reservations':0,'A_B':'UNCHANGED',
            'shared_with_old_clients':'NOT_VERIFIED','api_enabled':False,'redis_service':SERVICE}
        write_new(STATE/'complete.json',json.dumps(receipt,indent=2).encode())
        public={k:v for k,v in receipt.items() if k not in ('files','directories')}
        write_new(PREFIX/'installation.json',json.dumps(public,indent=2).encode(),0o644)
        print(json.dumps(public));return 0
    except Exception as e:
        print(json.dumps({'status':'STOP_OR_UNCERTAIN','phase':phase,'error_type':type(e).__name__,
            'auto_retry':False,'api_enabled':False}));return 1


if __name__=='__main__':raise SystemExit(main())
