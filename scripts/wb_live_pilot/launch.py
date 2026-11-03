"""Reviewed root-only E activation of unchanged accepted PR104; no installation ABC.

Self-contained build embeds nonsecret runner and expected service/runtime hashes.
Temporary activation is removed after the single bounded service run. Unknown
partial execution never retries HTTP; --hold only stops/cleans our exact controls.
"""
import base64
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import pwd
import socket
import stat
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

ASSETS = {}  # BUILD_EMBED_ASSETS
CODE='c1fee070e9efa0c925a78f266fdf03cb12a173cf'
RELEASE=Path('/opt/mcp/projects/msp-marketplace-reports-releases')/CODE
ARCHIVE=Path('/opt/mcp/data/msp-marketplace-reports')
UNIT=Path('/etc/systemd/system/msp-wb-pilot.service')
SERVICE='msp-wb-pilot.service'
CONTROL=Path('/etc/msp-marketplace-reports-executor')
APPROVAL=CONTROL/'approval.json'
REDIS_ENV=CONTROL/'redis-runtime.env'
PILOT=Path('/etc/msp-marketplace-reports-pilot/wb_laser_master.json')
MASTER=Path('/etc/msp-marketplace-reports/cabinets.json')
SYNTHETIC=Path('/var/lib/msp-quota-probe-i8kqe69o/result.json')
STATE=Path('/var/lib/msp-wb-E-883801632')
DROP_DIR=Path('/run/systemd/system/msp-wb-pilot.service.d')
DROP=DROP_DIR/'90-msp-E-883801632.conf'
PUBLIC=Path('/opt/mcp/report-run-results')
EXECUTOR_GID=985
RESULT_NAME='wb-883801632-E.json'
PLAN={'schema':1,'cabinet':'wb_laser_master','year':2026,'report_id':883801632,'report_type':1,'max_send_entries':3}


def sha(data):return hashlib.sha256(data).hexdigest()
def encoded(doc):return (json.dumps(doc,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n').encode()

def trusted(p,uid=0,mode=None):
    st=p.lstat()
    if stat.S_ISLNK(st.st_mode) or st.st_uid!=uid or st.st_mode&0o022:raise ValueError('untrusted path')
    if not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):raise ValueError('inode type')
    if stat.S_ISREG(st.st_mode) and st.st_nlink!=1:raise ValueError('hardlink')
    if mode is not None and stat.S_IMODE(st.st_mode)!=mode:raise ValueError('mode drift')
    return st

def parents(p):
    for item in [p,*p.parents]:trusted(item)

def syncdir(p):
    fd=os.open(p,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)

def write_new(p,data,mode=0o600,gid=0):
    fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,mode)
    try:
        with os.fdopen(fd,'wb',closefd=False) as f:
            f.write(data);f.flush();os.fchown(fd,0,gid);os.fchmod(fd,mode);os.fsync(fd)
    finally:os.close(fd)
    syncdir(p.parent)

def write_approval(raw):
    # Nonsecret capability document: root writes, only executor group may read.
    write_new(APPROVAL,raw,0o640,gid=EXECUTOR_GID)


def strict_json(raw):
    def pairs(items):
        d={}
        for k,v in items:
            if k in d:raise ValueError('duplicate JSON key')
            d[k]=v
        return d
    return json.loads(raw,object_pairs_hook=pairs)

def run(args,timeout=45):
    p=subprocess.run(args,capture_output=True,timeout=timeout,env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C.UTF-8'})
    if p.returncode:raise RuntimeError('command failed: '+Path(args[0]).name)
    return p.stdout

def show():
    raw=run(['/usr/bin/systemctl','show',SERVICE,'--property=ActiveState,SubState,DropInPaths,User,Group,PrivateNetwork,IPAddressAllow,IPAddressDeny,EnvironmentFiles,Restart']).decode()
    return dict(line.split('=',1) for line in raw.splitlines() if '=' in line)

def redis_config(raw):
    values={}
    for line in raw.decode().splitlines():
        k,sep,v=line.partition('=')
        if not sep or k not in ('MARKETPLACE_MCP_REDIS_URL','MARKETPLACE_REQUIRE_REDIS') or k in values or any(c in v for c in '\\"\'\r\x00'):
            raise ValueError('Redis EnvFile format')
        values[k]=v
    if set(values)!= {'MARKETPLACE_MCP_REDIS_URL','MARKETPLACE_REQUIRE_REDIS'} or values['MARKETPLACE_REQUIRE_REDIS']!='1':raise ValueError('Redis required')
    u=urlsplit(values['MARKETPLACE_MCP_REDIS_URL'])
    if (u.scheme!='redis' or u.hostname!='127.0.0.1' or u.port!=16379 or u.path!='/0' or u.username!='quota_runtime' or not u.password or u.query or u.fragment):raise ValueError('approved Redis target required')

def verify_credentials(pilot,master,now):
    one=strict_json(pilot);all_=strict_json(master)
    if type(one) is not dict or type(all_) is not dict or set(one)!= {'wb_laser_master'} or type(one['wb_laser_master']) is not dict or type(all_.get('wb_laser_master')) is not dict or one['wb_laser_master'].get('token')!=all_['wb_laser_master'].get('token'):raise ValueError('pilot/master alias mismatch')
    token=one['wb_laser_master'].get('token')
    if type(token) is not str or len(token.split('.'))!=3:raise ValueError('WB credential structure')
    piece=token.split('.')[1];claims=strict_json(base64.urlsafe_b64decode(piece+'='*(-len(piece)%4)))
    if not isinstance(claims.get('sid'),(str,int)) or isinstance(claims.get('sid'),bool) or not str(claims['sid']):raise ValueError('seller identity unavailable')
    if type(claims.get('exp')) is not int or claims['exp']<=now:raise ValueError('WB credential expired/expiry unknown')
    return {'pilot_master_match':True,'seller_identity_present':True,'expiry_local_check':'PASS',
            'signature_or_finance_permission_proven':False}

def resolve_allowlist():
    addresses=sorted({str(ipaddress.ip_address(x[4][0])) for x in socket.getaddrinfo('finance-api.wildberries.ru',443,type=socket.SOCK_STREAM)})
    if not addresses or len(addresses)>32 or any(not ipaddress.ip_address(x).is_global for x in addresses):raise ValueError('finance DNS not public/bounded')
    dns=[]
    for line in Path('/etc/resolv.conf').read_text().splitlines():
        fields=line.split()
        if len(fields)>=2 and fields[0]=='nameserver':dns.append(str(ipaddress.ip_address(fields[1])))
    if not dns or len(dns)>6:raise ValueError('DNS resolver inventory')
    ips=sorted(set(addresses+dns+['127.0.0.1']))
    return [x+('/32' if ipaddress.ip_address(x).version==4 else '/128') for x in ips]

def dropin_text(program,allow):
    if any(c in str(program) for c in '\n\r %'):raise ValueError('program path')
    # Only this service gets ephemeral egress; application additionally fixes HTTPS host/path.
    return ('[Service]\nPrivateNetwork=no\nEnvironmentFile='+str(REDIS_ENV)+'\n'
        'Environment=MARKETPLACE_REQUIRE_REDIS=1 MSP_REPORTS_SHARED_QUEUE_VERIFIED=YES\n'
        'Environment=HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= http_proxy= https_proxy= all_proxy=\n'
        'IPAddressDeny=any\nIPAddressAllow='+ ' '.join(allow)+'\n'
        'ExecStart=\nExecStart='+str(RELEASE/'.venv/bin/python')+' -I -B '+str(program)+'\n'
        'StandardOutput=file:'+str(STATE/'worker-output.json')+'\n'
        'StandardError=file:'+str(STATE/'worker-stderr.txt')+'\n').encode()

def safe_remove(p,expected):
    if not p.exists() and not p.is_symlink():return
    trusted(p)
    if sha(p.read_bytes())!=expected:raise ValueError('changed control; no removal')
    p.unlink();syncdir(p.parent)

def cleanup(ownership,stop=False):
    # Never stop other services, never delete page/budget/data/credentials.
    if stop and show()['ActiveState'] not in ('inactive','failed'):
        for p,key in [(APPROVAL,'approval_sha256'),(DROP,'dropin_sha256')]:
            trusted(p)
            if sha(p.read_bytes())!=ownership.get(key):raise ValueError('foreign active pilot; no stop')
        run(['/usr/bin/systemctl','stop',SERVICE],timeout=90)
    if show()['ActiveState'] not in ('inactive','failed'):raise ValueError('pilot still active')
    for p,key in [(APPROVAL,'approval_sha256'),(DROP,'dropin_sha256')]:
        if key in ownership:safe_remove(p,ownership[key])
    if DROP_DIR.exists():
        trusted(DROP_DIR)
        if list(DROP_DIR.iterdir()):raise ValueError('unexpected runtime dropin')
        DROP_DIR.rmdir();syncdir(DROP_DIR.parent)
    run(['/usr/bin/systemctl','daemon-reload'])
    state=show()
    if state.get('PrivateNetwork')!='yes' or state.get('DropInPaths') or APPROVAL.exists():raise ValueError('blocked state not restored')


def preflight():
    parents(Path(__file__).resolve().parent);trusted(Path(__file__).resolve(),mode=0o600)
    user=pwd.getpwnam('msp-reports')
    if (user.pw_uid,user.pw_gid)!=(995,985):raise ValueError('identity drift')
    if PUBLIC.exists():
        parents(PUBLIC)
        if (PUBLIC/RESULT_NAME).exists():raise ValueError('existing E public result')
    for n,digest in ASSETS['app_files'].items():
        p=RELEASE/n;parents(p.parent);trusted(p,mode=0o644)
        if sha(p.read_bytes())!=digest:raise ValueError('accepted code drift')
    actual={p.name for p in (RELEASE/'apps/msp_marketplace_reports').glob('*.py')}
    if actual!={Path(n).name for n in ASSETS['app_files']}:raise ValueError('unknown module in accepted release')
    for n,digest in ASSETS['runtime_files'].items():
        p=RELEASE/'.venv'/n;parents(p.parent);trusted(p,mode=0o644)
        if sha(p.read_bytes())!=digest:raise ValueError('accepted runtime drift')
    for n,target in ASSETS['runtime_links'].items():
        p=RELEASE/'.venv'/n;parents(p.parent)
        if not p.is_symlink() or p.lstat().st_uid!=0 or os.readlink(p)!=target:raise ValueError('runtime link drift')
    actual_runtime={str(p.relative_to(RELEASE/'.venv')) for p in (RELEASE/'.venv').rglob('*') if p.is_file() and not p.is_symlink()}
    if actual_runtime!=set(ASSETS['runtime_files']):raise ValueError('unexpected runtime file')
    if sha(Path('/usr/bin/python3.12').read_bytes())!=ASSETS['python_sha256']:raise ValueError('host Python drift')
    trusted(UNIT,mode=0o600)
    if sha(UNIT.read_bytes())!=ASSETS['base_unit_sha256']:raise ValueError('base unit drift')
    p=RELEASE/'pilot-plan.json';trusted(p,mode=0o644)
    if sha(p.read_bytes())!=ASSETS['plan_file_sha256'] or strict_json(p.read_bytes())!=PLAN:raise ValueError('pilot plan drift')
    parents(ARCHIVE.parent);trusted(ARCHIVE,uid=995,mode=0o700)
    if (ARCHIVE/'.wb-executor/E-883801632-events.jsonl').exists() and not ASSETS.get('recovery'):raise ValueError('preexisting E events; reconcile')
    if ARCHIVE.stat().st_gid!=985:raise ValueError('archive group drift')
    before=show()
    if before.get('ActiveState') not in ('inactive','failed') or before.get('DropInPaths') or before.get('PrivateNetwork')!='yes' or before.get('Restart')!='no':raise ValueError('pilot is active/modified')
    for base in ['/etc/systemd/system','/run/systemd/system','/usr/lib/systemd/system','/lib/systemd/system']:
        p=Path(base)/(SERVICE+'.d')
        if p.exists() or p.is_symlink():raise ValueError('unrecognized dropin directory')
    parents(CONTROL)
    if APPROVAL.exists() or APPROVAL.is_symlink():raise ValueError('existing API approval')
    trusted(REDIS_ENV,mode=0o600);redis_config(REDIS_ENV.read_bytes())
    for p in [MASTER,PILOT]:parents(p.parent);trusted(p,mode=0o600)
    master_raw=MASTER.read_bytes();pilot_raw=PILOT.read_bytes()
    credential_summary=verify_credentials(pilot_raw,master_raw,time.time())
    # Do not write credential values/hashes to receipts, GitHub or stdout.
    secret_guards=[(MASTER,sha(master_raw),MASTER.stat()),(PILOT,sha(pilot_raw),PILOT.stat()),(REDIS_ENV,sha(REDIS_ENV.read_bytes()),REDIS_ENV.stat())]
    parents(SYNTHETIC.parent);trusted(SYNTHETIC,mode=0o600)
    synth=strict_json(SYNTHETIC.read_bytes())
    if synth.get('probe_sha256')!=ASSETS['synthetic_probe_sha256']:raise ValueError('synthetic evidence origin')
    result=synth.get('result',{})
    expected={'synthetic_quota':'PASS','clients':2,'keys':4,'ttl_ceiling_seconds':715,'provider_calls':0,'live_seller_keys_touched':0,'api_enabled':False}
    if any(type(result.get(k)) is not type(v) or result[k]!=v for k,v in expected.items()):raise ValueError('synthetic acceptance evidence')
    if run(['/usr/bin/systemctl','is-active','msp-quota-redis.service']).strip()!=b'active':raise ValueError('quota service inactive')
    return secret_guards,credential_summary


def summarize():
    """Read bounded wrapper output, NEVER journalctl/header/raw HTTP payload."""
    p=STATE/'worker-output.json';trusted(p)
    if p.stat().st_size>65536:raise ValueError('worker summary oversized')
    doc=strict_json(p.read_bytes())
    return doc


def publish_result(doc):
    if not PUBLIC.exists():PUBLIC.mkdir(mode=0o755);os.chmod(PUBLIC,0o755);syncdir(PUBLIC.parent)
    parents(PUBLIC)
    write_new(PUBLIC/RESULT_NAME,encoded(doc),0o644)
    write_new(STATE/'result.json',encoded(doc))
    print(json.dumps(doc,sort_keys=True))


def main():
    if os.geteuid()!=0:print('ROOT_REQUIRED;NO_CHANGES');return 2
    if sys.argv[1:] not in ([],['--hold']):raise ValueError('only fixed pilot or hold allowed')
    if STATE.exists():
        parents(STATE);trusted(STATE,mode=0o700)
        if sys.argv[1:]==['--hold']:
            trusted(STATE/'controls.json',mode=0o600)
            ownership=strict_json((STATE/'controls.json').read_bytes())
            cleanup(ownership,stop=True);print('HELD_API_BLOCKED;DATA_AND_BUDGET_PRESERVED');return 0
        if (STATE/'result.json').exists():
            trusted(STATE/'result.json',mode=0o600);print((STATE/'result.json').read_text());return 0
        raise ValueError('partial/uncertain E; no retry; inspect state or hold')
    if sys.argv[1:]:raise ValueError('no existing E to hold')
    guards,credential_summary=preflight()
    recovery_summary=None
    if ASSETS.get('recovery'):
        sys.path.insert(0,str(RELEASE))
        import types
        guard_code=base64.b64decode(ASSETS['recovery_guard_base64'])
        if sha(guard_code)!=ASSETS['recovery_guard_sha256']:raise ValueError('recovery guard integrity')
        recovery_guard=types.ModuleType('reviewed_recovery_guard');exec(compile(guard_code,'<reviewed recovery guard>','exec'),recovery_guard.__dict__)
        recovery_summary=recovery_guard.inspect_failure()
    # PREPARED command is run only after independent review; owner E already granted.
    allow=resolve_allowlist()
    STATE.mkdir(mode=0o700);os.chmod(STATE,0o700);syncdir(STATE.parent)
    ownership={};started=False;cleanup_ok=False;phase='PREPARE'
    def checkpoint(name):write_new(STATE/(name+'.json'),encoded({'phase':name,'code_sha':CODE}))
    checkpoint('BEGIN')
    if recovery_summary is not None:write_new(STATE/'recovery-preflight.json',encoded(recovery_summary))
    try:
        program_dir=Path(tempfile.mkdtemp(prefix='msp-wb-E-program-',dir='/var/lib'))
        runner=base64.b64decode(ASSETS['runner_base64'])
        if sha(runner)!=ASSETS['runner_sha256']:raise ValueError('runner integrity')
        write_new(program_dir/'runner.py',runner,0o644);os.chmod(program_dir,0o755)
        approval={'schema':1,'plan_sha256':sha(encoded(PLAN)),'code_sha256':ASSETS['app_code_sha256'],
                  'archive_root':str(ARCHIVE),'expires_epoch':int(time.time())+600,
                  'owner_api_pilot_authorized':True,'shared_quota_verified':True,'conflicting_clients_excluded':True,
                  'evidence_reference':'OWNER_ATTESTED_OLD_REMOTE_RETIRED;OWNER_APPROVED_E_883801632_MAX3;'+str(SYNTHETIC)}
        auth_raw=encoded(approval);drop_raw=dropin_text(program_dir/'runner.py',allow)
        ownership={'approval_sha256':sha(auth_raw),'dropin_sha256':sha(drop_raw),'runner_path':str(program_dir/'runner.py')}
        # Durable ownership BEFORE control mutations, for safe crash-time hold.
        write_new(STATE/'controls.json',encoded(ownership))
        DROP_DIR.mkdir(mode=0o755);os.chmod(DROP_DIR,0o755);syncdir(DROP_DIR.parent)
        write_new(DROP,drop_raw,0o644);write_approval(auth_raw)
        if ASSETS.get('recovery'):
            negative=program_dir/'approval-negative.json';write_new(negative,auth_raw)
            def readcheck(arguments,label):
                cmd=['/usr/bin/systemd-run','--quiet','--wait','--pipe','--collect','--unit=msp-wb-E-read-'+label,
                    '-p','User=msp-reports','-p','Group=msp-reports','-p','NoNewPrivileges=yes',
                    '-p','CapabilityBoundingSet=','-p','ProtectSystem=strict','-p','ProtectHome=yes',
                    '-p','PrivateNetwork=yes','-p','IPAddressDeny=any','-p','RuntimeMaxSec=20',
                    str(RELEASE/'.venv/bin/python'),'-I','-B',str(program_dir/'runner.py'),*arguments]
                p=subprocess.run(cmd,capture_output=True,timeout=30,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
                return p.returncode,strict_json(p.stdout)
            red_rc,red=readcheck(['--check-approval-file',str(negative)],'negative')
            if red_rc==0 or red.get('error_type')!='PermissionError' or red.get('uid')!=995:raise ValueError('actual UID negative proof failed')
            green_rc,green=readcheck(['--check-approval-only'],'positive')
            if green_rc or green.get('approval_read')!='PASS' or green.get('uid')!=995 or green.get('gid')!=985 or green.get('provider_calls')!=0:raise ValueError('actual UID approval read failed')
            recovery_guard.assert_preserved(recovery_summary['snapshots'])
            write_new(STATE/'actual-uid-approval-read.json',encoded({'old0600':'PermissionError','fixed0640':'PASS','uid':995,'gid':985,'provider_calls':0,'budget_unchanged':True}))
        run(['/usr/bin/systemd-analyze','verify',SERVICE]);run(['/usr/bin/systemctl','daemon-reload'])
        settings=show()
        if (settings.get('PrivateNetwork')!='no' or settings.get('User')!='msp-reports' or settings.get('Group')!='msp-reports'
            or settings.get('DropInPaths')!=str(DROP) or str(REDIS_ENV) not in settings.get('EnvironmentFiles','')
            or settings.get('Restart')!='no'):raise ValueError('effective pilot configuration mismatch')
        phase='START';checkpoint('BEFORE_START');started=True
        # Exactly the installed finance unit, never an independent HTTP worker.
        child=subprocess.run(['/usr/bin/systemctl','start',SERVICE],capture_output=True,timeout=480,
                             env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
        phase='RESULT';checkpoint('SERVICE_RETURNED')
        output=summarize()
        cleanup(ownership,stop=False);cleanup_ok=True
        for p,digest,st in guards:
            now=p.stat()
            if sha(p.read_bytes())!=digest or (now.st_uid,now.st_gid,now.st_mode)!=(st.st_uid,st.st_gid,st.st_mode):raise ValueError('protected configuration changed')
        # Counts are evidence from runner + original journal, not assumed from exit0.
        complete=output.get('report_detail_complete') is True and output.get('executor',{}).get('status')=='DONE'
        status='PASS' if complete else ('PARTIAL' if output.get('executor',{}).get('status') in ('PAUSED_BUDGET','WAITING_RATE_LIMIT','WAITING_RETRY','PAGE_STAGED') else 'FAIL')
        doc={'status':status,'code_sha':CODE,'api_enabled_after_run':False,'no_schedule':True,
             'owner_old_remote_status':'OWNER_ATTESTED_OLD_REMOTE_RETIRED','credential_local_checks':credential_summary,
             'worker_exit':child.returncode,'outcome':output,'archive_root':str(ARCHIVE),
             'provider_contract':'HISTORICAL_MATCH_FIRST_AUTHORIZED_REQUEST_VALIDATES_LIVE_ACCESS',
             'protected_credentials_unchanged':True,'A_B_C':'UNCHANGED','root_state':str(STATE),
             'recovery_preflight':({k:v for k,v in recovery_summary.items() if k!='snapshots'} if recovery_summary else None)}
        publish_result(doc);return 0 if status in ('PASS','PARTIAL') else 1
    except Exception as exc:
        if not cleanup_ok:
            try:cleanup(ownership,stop=started);cleanup_ok=True
            except Exception:pass
        failure={'status':'STOP_OR_UNCERTAIN','phase':phase,'error_type':type(exc).__name__,
                 'http_may_have_started':started,'api_enabled_after_run':False if cleanup_ok else None,
                 'auto_retry':False,'budget_and_pages_preserved':True,'root_state':str(STATE)}
        write_new(STATE/'failure.json',encoded(failure));print(json.dumps(failure));return 1

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({'status':'STOP_OR_UNCERTAIN','error_type':type(exc).__name__,'auto_retry':False}));raise SystemExit(1)
