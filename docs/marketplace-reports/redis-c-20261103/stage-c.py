"""Root C only: bounded redacted config discovery, optional approved Redis READ_ONLY.

No installation, credential copying, config/ACL writes, provider or quota calls.
No automatic selection from a discovered candidate; only the designated approved
redis-readonly.env is eligible for the installed probe.
"""
import hashlib
import json
import os
from pathlib import Path
import shlex
import stat
import subprocess

RELEASE=Path('/opt/mcp/projects/msp-marketplace-reports-releases/c1fee070e9efa0c925a78f266fdf03cb12a173cf')
CONFIG=Path('/etc/msp-marketplace-reports/redis-readonly.env')
ROOTS=('/etc/msp-marketplace-reports','/etc/msp-marketplace-reports-executor',
       '/opt/mcp/secrets/msp-marketplace-reports','/opt/mcp/secrets/marketplaces')
UNITS=('mcp-marketplaces.service','msp-wb-pilot.service','redis-server.service','redis.service','valkey.service')
ALLOWED=frozenset({'MARKETPLACE_MCP_REDIS_URL','MARKETPLACE_MCP_REDIS_HOST','MARKETPLACE_MCP_REDIS_PORT',
    'MARKETPLACE_MCP_REDIS_PASSWORD','MARKETPLACE_MCP_REDIS_DB','MARKETPLACE_MCP_REDIS_TLS','MARKETPLACE_MCP_REDIS_CA_CERT'})
MANIFEST_SHA='61bcce54f4a28dd6384faddfd6ef4ec005362adfb8084a9d8a8485048cec4b90'
PROBE_SHA='4a3a70596e0a5ab1d198b18e862c3bc15319f19d568a6c11b0cf733c62b8e7a1'


def sha(data):return hashlib.sha256(data).hexdigest()


def trusted(p,*,uid=0,mode=None):
    s=p.lstat()
    if s.st_uid!=uid or s.st_mode&0o022 or stat.S_ISLNK(s.st_mode):raise ValueError('untrusted path')
    if mode is not None and stat.S_IMODE(s.st_mode)!=mode:raise ValueError('unexpected mode')
    if stat.S_ISREG(s.st_mode) and s.st_nlink!=1:raise ValueError('hardlink')
    if not stat.S_ISREG(s.st_mode) and not stat.S_ISDIR(s.st_mode):raise ValueError('unexpected inode')
    return s


def read_env(p,*,strict=False,uid=0):
    st=trusted(p,uid=uid)
    if not stat.S_ISREG(st.st_mode) or st.st_size>65536:raise ValueError('env bound/type')
    keys=[]
    for line in p.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#'):continue
        key,sep,value=line.partition('=')
        if strict and (not sep or key not in ALLOWED or key in keys or '\\' in value):
            raise ValueError('Redis-only simple config required')
        if key in ALLOWED and sep and value.strip():keys.append(key)
    if strict and not ({'MARKETPLACE_MCP_REDIS_URL','MARKETPLACE_MCP_REDIS_HOST'} & set(keys)):
        raise ValueError('Redis endpoint absent')
    return sorted(set(keys))  # Values NEVER leave this function.


def discover():
    result=[]
    for name in ROOTS:
        directory=Path(name)
        if not directory.exists():result.append({'directory':name,'status':'ABSENT'});continue
        trusted(directory)
        entries=[]
        paths=list(directory.iterdir())
        if len(paths)>64:raise ValueError('directory inventory bound')
        for p in sorted(paths):
            st=p.lstat()
            row={'name':p.name,'mode':oct(stat.S_IMODE(st.st_mode)),'uid':st.st_uid,
                 'type':'regular' if stat.S_ISREG(st.st_mode) else 'other'}
            # Do NOT open cabinets/tokens/JSON or arbitrary unrelated services.
            if stat.S_ISREG(st.st_mode) and (p.name.endswith('.env') or p.name=='.env'):
                row['redis_variable_names']=read_env(p)
            entries.append(row)
        result.append({'directory':name,'entries':entries})
    units=[]
    for name in UNITS:
        r=subprocess.run(['/usr/bin/systemctl','show',name,'--property=LoadState,Environment,EnvironmentFiles'],
            capture_output=True,text=True,timeout=15)
        row={'unit':name,'load_state':'UNKNOWN','redis_variable_names':[],'environment_file_refs':[]}
        for line in r.stdout.splitlines():
            key,sep,value=line.partition('=')
            if key=='LoadState':row['load_state']=value if value in ('loaded','not-found','masked','error','bad-setting') else 'OTHER'
            elif key=='Environment':
                row['redis_variable_names']=sorted({part.partition('=')[0] for part in shlex.split(value) if part.partition('=')[0] in ALLOWED})
            elif key=='EnvironmentFiles':
                # Paths only from systemd; never file contents/Environment values.
                row['environment_file_refs']=[part for part in shlex.split(value) if part.startswith('/')]
        units.append(row)
    return {'protected_config_inventory':result,'unit_config_inventory':units}


def verify_release():
    for p in [RELEASE,*RELEASE.parents]:trusted(p)
    p=RELEASE/'INSTALL_MANIFEST.json';trusted(p)
    if sha(p.read_bytes())!=MANIFEST_SHA:raise ValueError('installed manifest drift')
    code=json.loads(p.read_text())
    for name,digest in code['files'].items():
        # Pinned manifest establishes the allowed set, no factory import.
        file=RELEASE/name;trusted(file,mode=0o644)
        if sha(file.read_bytes())!=digest:raise ValueError('installed code drift')
    probe=RELEASE/'redis_readonly_probe.py';trusted(probe,mode=0o644)
    if sha(probe.read_bytes())!=PROBE_SHA:raise ValueError('installed probe drift')
    # Existing complete receipt inventories the runtime; verify before invoking it.
    receipt=Path('/var/lib/msp-wb-bootstrap/complete.json');trusted(receipt,mode=0o600)
    doc=json.loads(receipt.read_text())
    for entry in doc['installed_files']:
        p=Path(entry['path'])
        if not str(p).startswith(str(RELEASE)+'/') and p!=Path('/etc/systemd/system/msp-wb-pilot.service'):
            raise ValueError('receipt path outside release')
        if '..' in p.parts:raise ValueError('receipt escape')
        trusted(p,mode=entry['mode'])
        if sha(p.read_bytes())!=entry['sha256']:raise ValueError('installed runtime drift')
    for entry in doc['runtime_links']:
        p=Path(entry['path'])
        if not str(p).startswith(str(RELEASE/'.venv')+'/') or '..' in p.parts:
            raise ValueError('link outside venv')
        if not p.is_symlink() or os.readlink(p)!=entry['target']:raise ValueError('runtime link drift')


def main():
    if os.geteuid()!=0:print('ROOT_REQUIRED;NO_CHANGES');return 2
    try:
        result=discover()
        result.update({'provider_calls':0,'quota_writes':0,'config_writes':0,
                       'shared_with_other_clients':'NOT_VERIFIED','api_enabled':False})
        if not CONFIG.exists():
            result['C']='NOT_CONFIGURED_APPROVED_BACKEND_REQUIRED'
            print(json.dumps(result,sort_keys=True));return 0
        for p in [CONFIG.parent,*CONFIG.parent.parents]:trusted(p)
        trusted(CONFIG,mode=0o600);read_env(CONFIG,strict=True)
        verify_release()
        # WB credentials are NOT supplied. The pinned probe speaks only Redis.
        args=['/usr/bin/systemd-run','--quiet','--wait','--pipe','--collect',
            '--unit=msp-wb-stage-c-readonly','-p','User=msp-reports','-p','Group=msp-reports',
            '-p','EnvironmentFile='+str(CONFIG),'-p','NoNewPrivileges=yes','-p','CapabilityBoundingSet=',
            '-p','ProtectSystem=strict','-p','ProtectHome=yes','-p','PrivateTmp=yes',
            str(RELEASE/'.venv/bin/python'),'-B',str(RELEASE/'redis_readonly_probe.py'),'--release',str(RELEASE)]
        run=subprocess.run(args,capture_output=True,text=True,timeout=120,
            env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
        if run.returncode:raise RuntimeError('read-only probe unavailable')
        probe=json.loads(run.stdout)
        if probe.get('read_only_protocol_check')!='PASS':raise ValueError('Redis not verified')
        result.update({'C':'READ_ONLY_PASS_LUA_NOT_TESTED','probe':probe})
        print(json.dumps(result,sort_keys=True));return 0
    except Exception as exc:
        print(json.dumps({'C':'STOP_OR_NOT_VERIFIED','error_type':type(exc).__name__,
            'provider_calls':0,'quota_writes':0,'config_writes':0,'api_enabled':False}));return 1


if __name__=='__main__':raise SystemExit(main())
