"""Build inert synthetic-stage and E handoff artifacts; never installs/runs them."""
import base64
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/marketplace-reports/execution-20261103'

def build():
    OUT.mkdir(exist_ok=True)
    probe=(ROOT/'docs/marketplace-reports/pilot-next-20261103/synthetic_quota.py').read_bytes()
    payload=base64.b64encode(probe).decode();digest=hashlib.sha256(probe).hexdigest()
    launcher=('''"""Root-only bounded synthetic acceptance launcher. No provider credentials/API."""
import base64,hashlib,json,os,pwd,stat,subprocess,sys,tempfile
from pathlib import Path
PAYLOAD="'''+payload+'''"
DIGEST="'''+digest+'''"
RELEASE=Path('/opt/mcp/projects/msp-marketplace-reports-releases/c1fee070e9efa0c925a78f266fdf03cb12a173cf')
def main():
    if os.geteuid()!=0 or sys.argv[1:]!=['--synthetic-write-approved']:
        print('BLOCKED: root and explicit synthetic-only approval required');return 2
    user=pwd.getpwnam('msp-reports')
    if (user.pw_uid,user.pw_gid)!=(995,985):raise ValueError('existing identity drift')
    if Path('/etc/msp-marketplace-reports-executor/approval.json').exists():raise ValueError('provider approval must remain absent')
    env=Path('/etc/msp-marketplace-reports-executor/redis-runtime.env')
    for p in [env,*env.parents]:
        st=p.lstat()
        if stat.S_ISLNK(st.st_mode) or st.st_uid!=0 or st.st_mode&0o022:raise ValueError('unsafe Redis EnvFile path')
    if stat.S_IMODE(env.stat().st_mode)!=0o600:raise ValueError('Redis EnvFile mode')
    # Never open/read/print/copy the EnvFile: PID1 injects it into nonroot service.
    data=base64.b64decode(PAYLOAD)
    if hashlib.sha256(data).hexdigest()!=DIGEST:raise ValueError('probe digest')
    folder=Path(tempfile.mkdtemp(prefix='msp-quota-probe-',dir='/var/lib'))
    script=folder/'probe.py'
    fd=os.open(script,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:
        f.write(data);f.flush();os.fchown(f.fileno(),0,0);os.fchmod(f.fileno(),0o644);os.fsync(f.fileno())
    os.chmod(folder,0o755)
    cmd=['/usr/bin/systemd-run','--quiet','--wait','--collect','--pipe','--unit='+folder.name,
         '-p','User=msp-reports','-p','Group=msp-reports','-p','UMask=0077',
         '-p','EnvironmentFile='+str(env),'-p','NoNewPrivileges=yes',
         '-p','ProtectSystem=strict','-p','ProtectHome=yes','-p','PrivateTmp=yes',
         '-p','IPAddressDeny=any','-p','IPAddressAllow=127.0.0.1/32','-p','RuntimeMaxSec=30',
         str(RELEASE/'.venv/bin/python'),'-I','-B',str(script),'--synthetic-write-approved']
    run=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45,check=False)
    # stdout is the fixed redacted probe result. Never relay arbitrary stderr.
    try:
        result=json.loads(run.stdout)
        if run.returncode or result.get('synthetic_quota')!='PASS' or result.get('provider_calls')!=0:raise ValueError()
    except (ValueError,UnicodeError):
        result={'synthetic_quota':'FAIL','systemd_exit':run.returncode,'provider_calls':0,'api_enabled':False}
    receipt={'probe_sha256':DIGEST,'result':result,'report_approval_created':False}
    p=folder/'result.json';fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as f:
        json.dump(receipt,f,sort_keys=True);f.flush();os.fchmod(f.fileno(),0o600);os.fsync(f.fileno())
    print(json.dumps({'receipt':str(p),**result},sort_keys=True))
    return 0 if result['synthetic_quota']=='PASS' else 1
if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:
        print(json.dumps({'synthetic_quota':'FAIL','error_type':type(exc).__name__,'provider_calls':0}));sys.exit(1)
''').encode()
    (OUT/'run-synthetic.py').write_bytes(launcher)
    sha=hashlib.sha256(launcher).hexdigest()
    cmd='probe_stage=$(mktemp -d /var/lib/msp-synthetic-entry.XXXXXXXX) && install -o root -g root -m 600 /home/hermes/workspace/msp-run-synthetic.py "$probe_stage/run.py" && printf \'%s  %s\\n\' '+sha+' "$probe_stage/run.py" | sha256sum -c - && /usr/bin/python3 -I -B "$probe_stage/run.py" --synthetic-write-approved\n'
    (OUT/'ROOT_SYNTHETIC_ONE_LINE.txt').write_text(cmd)
    # Existing accepted release and plan remain byte-identical. E stays inert.
    src=ROOT/'docs/marketplace-reports/deployment/autonomous-wb'
    for source,target in [('pilot-plan.json','pilot-plan.json'),('authorization.BLOCKED.template.json','authorization.BLOCKED.json')]:
        (OUT/target).write_bytes((src/source).read_bytes())
    files=['run-synthetic.py','pilot-plan.json','authorization.BLOCKED.json']
    (OUT/'MANIFEST.json').write_text(json.dumps({'state':'PREPARED_NOT_EXECUTED','files':{n:hashlib.sha256((OUT/n).read_bytes()).hexdigest() for n in files}},indent=2)+'\n')
    helpers=['finance_refresh_plan.py','finance_receipts.py','wb_discovery_resume.py','wb_report_revision.py','ozon_connection_plan.py']
    (OUT/'SOURCE_MANIFEST.json').write_text(json.dumps({'schema':1,'accepted_release':'c1fee070e9efa0c925a78f266fdf03cb12a173cf','production_install_executed':False,'new_helpers_not_installed':{n:hashlib.sha256((ROOT/'apps/msp_marketplace_reports'/n).read_bytes()).hexdigest() for n in helpers}},indent=2)+'\n')
    return sha
if __name__=='__main__':print(build())
