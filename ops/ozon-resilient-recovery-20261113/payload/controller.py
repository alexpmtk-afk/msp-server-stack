"""Fixed bounded recovery of the interrupted Nov1-13 Ozon campaign."""
import os,sys,json,time,uuid,fcntl,socket,ipaddress,pwd,subprocess,signal
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import root_common as r
from recovery import wait_worker,Paused,StartNotificationLost
ROOT=Path(__file__).resolve().parent
SOURCE_ROOT=Path('/var/lib/msp-ozon-current-accruals.ukayjhrw')
CABINETS=('ozon_dmitrieva','ozon_novokshenov','ozon_laser_master')
LEDGER=Path('/var/lib/msp-ozon-current-recovery-20261113')
PUBLIC=Path('/var/lib/msp-finance-control/results/ozon-current-recovery-20261113.json')
UNIT='msp-ozon-current-recovery-20261113.service'
TASK='ozon-current-recovery-20261113'
RULE=Path('/etc/polkit-1/rules.d/48-msp-ozon-current-recovery.rules')
DROP=Path('/run/systemd/system/msp-wb-pilot.service.d/95-ozon-resilient-recovery.conf')
PERIOD='2026-11'
SEED=Path('/opt/mcp/data/msp-marketplace-reports/ozon-accrual-month-pilot-20261111/types.seed.json')
TYPE_SHA='1d96c2089b339c9d8dbab370e671d6668cb93a2be3345ac17cde76543eab16ea'
STOP=False
class OwnershipUncertain(ValueError):pass
class ManagerUnavailable(Paused):pass

def replace(path,value,mode=0o644):
    if path.exists():r.trust(path,mode)
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp');r.save(tmp,r.doc(value),mode);os.replace(tmp,path);r.syncdir(path.parent)

def history(c):return r.ARCHIVE/('ozon-current-accruals-20261113-'+c)
def cab_public(c):return Path('/var/lib/msp-finance-control/results')/('ozon-current-recovery-'+c+'-20261113.json')
def child(c,script,*args):return ['/usr/bin/python3','-I','-B',str(ROOT/c/script),*args]

def progress(status,done,cabinet=None,**extra):
    value=dict(status=status,cabinets=list(CABINETS),completed_cabinets=done,current_cabinet=cabinet or 'verify',snapshot_through='2026-11-13',current_month_provisional=True,background_model_calls=0,root_release=str(ROOT),original_budget_per_cabinet=128,**extra)
    if not PUBLIC.exists() or json.loads(PUBLIC.read_bytes())!=value:replace(PUBLIC,value)

def state():
    try:raw=r.run(['/usr/bin/systemctl','show',r.SERVICE,'-p','ActiveState','-p','PrivateNetwork','-p','DropInPaths','-p','InvocationID','-p','ExecMainStatus'])
    except (RuntimeError,subprocess.TimeoutExpired):raise ManagerUnavailable('manager state temporarily unavailable')
    return dict(x.split('=',1) for x in raw.decode().splitlines() if '=' in x)

def reload_owned(deadline):
    while time.time()<deadline:
        if STOP:raise Paused('controller pause')
        try:r.run(['/usr/bin/systemctl','daemon-reload']);return
        except (RuntimeError,subprocess.TimeoutExpired):time.sleep(3)
    raise Paused('manager unavailable until fixed deadline')


def trusted_context():
    p=LEDGER/'activation.json'
    if not p.exists():return None
    r.trust(p,0o600);a=json.loads(p.read_bytes());c=a['cabinet']
    if c not in CABINETS:raise OwnershipUncertain('activation cabinet')
    if DROP.exists():
        r.trust(DROP,0o644)
        if r.sha(DROP.read_bytes())!=a['drop_sha256']:raise OwnershipUncertain('foreign drop')
    elif not a.get('phase','').startswith('closing'):raise OwnershipUncertain('owned drop missing')
    r.trust(ROOT/c/'job.json',0o644)
    if r.sha((ROOT/c/'job.json').read_bytes())!=a['job_sha256']:raise OwnershipUncertain('foreign job')
    s=state()
    if s['ActiveState'] in ('active','activating','reloading') and s.get('DropInPaths','').split()!=[str(DROP)]:raise OwnershipUncertain('foreign effective worker controls')
    if a.get('invocation_id') and s['ActiveState'] in ('active','activating','reloading') and s['InvocationID']!=a['invocation_id']:raise OwnershipUncertain('foreign invocation')
    return a

def close_inactive():
    a=trusted_context()
    if not a:return
    if state()['ActiveState'] not in ('inactive','failed'):raise OwnershipUncertain('never stop live executor during cleanup')
    a['phase']='closing';replace(LEDGER/'activation.json',a,0o600)
    if DROP.exists():DROP.unlink();r.syncdir(DROP.parent)
    reload_owned(max(a['deadline'],time.time()+120))
    p=ROOT/a['cabinet']/'cabinets.json'
    if p.exists():
        r.trust(p,0o640)
        if r.sha(p.read_bytes())!=a['credential_sha256']:raise OwnershipUncertain('foreign credentials')
        p.unlink();r.syncdir(p.parent)
    (LEDGER/'activation.json').rename(LEDGER/('activation-'+a['attempt']+'.closed.json'));r.syncdir(LEDGER)
    s=state()
    if s['PrivateNetwork']!='yes' or s['DropInPaths']:raise OwnershipUncertain('base isolation not restored')

def finish_intent():
    p=LEDGER/'activation-intent.json'
    if not p.exists():return
    r.trust(p,0o600);a=json.loads(p.read_bytes());c=a['cabinet']
    if (LEDGER/'activation.json').exists() or state()['ActiveState'] not in ('inactive','failed'):raise OwnershipUncertain('partial activation conflicts with live worker')
    if c not in CABINETS:raise OwnershipUncertain('intent scope')
    cred=json.loads(r.MASTER.read_bytes())[c];rawcred=r.doc({c:{k:cred[k] for k in ('client_id','api_key')}})
    expected=[(ROOT/c/'job.json',r.doc(a['job']),0o644,0),(ROOT/c/'cabinets.json',rawcred,0o640,985),(DROP,a['drop_text'].encode(),0o644,0)]
    if r.sha(rawcred)!=a['credential_sha256'] or r.sha(expected[0][1])!=a['job_sha256'] or r.sha(expected[2][1])!=a['drop_sha256']:raise OwnershipUncertain('intent source changed')
    for path,raw,mode,gid in expected:
        if path.exists():
            r.trust(path,mode)
            if r.sha(path.read_bytes())!=r.sha(raw):raise OwnershipUncertain('intent target drift')
        else:
            if path==DROP:r.prepare_drop_directory(DROP.parent,recovering=False)
            r.save(path,raw,mode,gid)
    a['phase']='needs_reload';replace(p,a,0o600);p.rename(LEDGER/'activation.json');r.syncdir(LEDGER)


def dns_allow():
    addresses={str(ipaddress.ip_address(x[4][0])) for x in socket.getaddrinfo('api-seller.ozon.ru',443,type=socket.SOCK_STREAM)}
    if not addresses or len(addresses)>32 or any(not ipaddress.ip_address(x).is_global for x in addresses):raise ValueError('DNS bounds')
    dns={str(ipaddress.ip_address(x.split()[1])) for x in Path('/etc/resolv.conf').read_text().splitlines() if x.split()[:1]==['nameserver']}
    if not dns or len(dns)>6:raise ValueError('resolver bounds')
    return [x+('/32' if ipaddress.ip_address(x).version==4 else '/128') for x in sorted(addresses|dns|{'127.0.0.1'})]

def activation(c,claim):
    s=state()
    if s['ActiveState'] not in ('inactive','failed') or s['PrivateNetwork']!='yes' or s['DropInPaths']:raise OwnershipUncertain('executor not isolated')
    creds=json.loads(r.MASTER.read_bytes()).get(c)
    if not isinstance(creds,dict) or any(type(creds.get(k)) is not str or not creds[k].strip() for k in ('client_id','api_key')):raise ValueError('credential scope')
    if not creds['client_id'].isascii() or not creds['client_id'].isdecimal():raise ValueError('client id')
    # DNS/Redis readiness happen before creating owned controls or consuming sender entries.
    allow=dns_allow()
    try:quota_active=r.run(['/usr/bin/systemctl','is-active','msp-quota-redis.service']).strip()==b'active'
    except (RuntimeError,subprocess.TimeoutExpired):raise Paused('quota service unavailable')
    if not quota_active:raise Paused('quota service unavailable')
    job=dict(cabinet=c,period=PERIOD,max_send_entries=128,nonce=claim['nonce'],expires_epoch=claim['deadline'])
    rawcred=r.doc({c:{k:creds[k] for k in ('client_id','api_key')}})
    drop=(r.unit_condition_override(ROOT/c/'job.json')+'[Service]\nPrivateNetwork=no\nEnvironmentFile='+str(r.ENV)+'\nEnvironment=MARKETPLACE_REQUIRE_REDIS=1 MSP_REPORTS_SHARED_QUEUE_VERIFIED=YES\nLoadCredential=\nLoadCredential=cabinets.json:'+str(ROOT/c/'cabinets.json')+'\nIPAddressAllow='+' '.join(allow)+'\nEnvironment=HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= http_proxy= https_proxy= all_proxy=\nExecStart=\nExecStart='+str(r.RUNTIME/'bin/python')+' -I -B '+str(ROOT/c/'capture_worker.py')+'\nRestart=no\nTimeoutStopSec=90\nTimeoutStartSec=100000\nStandardOutput=null\nStandardError=file:'+str(LEDGER/(c+'.stderr'))+'\n').encode()
    attempt=uuid.uuid4().hex
    # Write intent before any activation mutation; partial setup is explicit HOLD, never assumed absent.
    r.save(LEDGER/'activation-intent.json',r.doc(dict(cabinet=c,attempt=attempt,deadline=claim['deadline'],job=job,drop_text=drop.decode(),drop_sha256=r.sha(drop),job_sha256=r.sha(r.doc(job)),credential_sha256=r.sha(rawcred))),0o600)
    finish_intent()


def verify_cabinet(c,result):
    if result.get('status')!='PUBLISHED_SOURCE_VERIFIED' or result.get('cabinet')!=c or result.get('period')!=PERIOD or result.get('days_collected')!=13:raise ValueError('worker receipt scope')
    doc=dict(status='SOURCE_COLLECTION_COMPLETE',cabinet=c,from_month=11,to_month=11,year=2026,months=[result],completed_months=1,rows=result['rows'],temporary_activation_removed=True,activation_policy_removed=True)
    replace(cab_public(c),doc)
    report=json.loads(r.run(child(c,'verify_results.py'),timeout=3600))
    if report.get('verification')!='PASS':raise ValueError('cabinet not verified')
    return dict(cabinet=c,**report)

def interrupted_reconcile(c):
    # The probe reads all retained pages and the original cumulative budget, no HTTP/credentials.
    return json.loads(r.run(child(c,'probe_retained.py'),timeout=60))

def run_campaign():
    if os.geteuid()!=0:raise PermissionError('root required')
    r.verify_payload();r.trust(LEDGER/'claims.json',0o600);claims=json.loads((LEDGER/'claims.json').read_bytes())
    lock=Path('/var/lib/msp-finance-control/controller.lock');r.trust(lock,0o600)
    with lock.open('rb') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        done=[]
        finish_intent()
        existing=trusted_context()
        if existing and existing.get('phase','').startswith('closing'):close_inactive()
        for c in CABINETS:
            claim=claims[c];statepath=history(c)/PERIOD;resultpath=statepath/'worker-result.json'
            while time.time()<claim['deadline']:
                if STOP:raise Paused('controller paused by service manager')
                a=trusted_context()
                if resultpath.exists() and (not a or a['cabinet']!=c):
                    r.trust(resultpath,0o644,995);result=json.loads(resultpath.read_bytes())
                    if result.get('nonce')!=claim['nonce']:raise ValueError('worker nonce mismatch')
                    done.append(verify_cabinet(c,result));progress('RUNNING',done,c);break
                if a and a['cabinet']!=c:raise OwnershipUncertain('foreign cabinet activation')
                if a:
                    def ownstate():
                        if STOP:raise Paused('controller pause')
                        context=trusted_context();s=state()
                        if context and context.get('phase')=='start_requested' and s['ActiveState'] in ('active','activating','reloading') and s['InvocationID']:
                            context.update(phase='working',invocation_id=s['InvocationID']);replace(LEDGER/'activation.json',context,0o600)
                        return s['ActiveState']
                    def request_start():
                        # Reattach after root controller restart. Never start a second live worker.
                        if ownstate() not in ('active','activating','reloading'):
                            interrupted_reconcile(c)
                            reload_owned(claim['deadline'])
                            a.update(phase='start_requested',invocation_id=None);replace(LEDGER/'activation.json',a,0o600)
                            try:r.run(['/usr/bin/systemctl','start','--no-block',r.SERVICE])
                            except (RuntimeError,subprocess.TimeoutExpired):raise StartNotificationLost('start notification unavailable')
                        s=state()
                        if s['ActiveState'] in ('active','activating','reloading') and s['InvocationID']:
                            a.update(phase='working',invocation_id=s['InvocationID']);replace(LEDGER/'activation.json',a,0o600)
                    outcome=wait_worker(start=request_start,state=ownstate,has_result=resultpath.exists,pause=lambda reason:progress(reason,done,c),deadline=claim['deadline'])
                    # A receipt can precede process exit; wait without sending SIGTERM.
                    while state()['ActiveState'] not in ('inactive','failed'):
                        if STOP:raise Paused('controller pause')
                        time.sleep(1)
                    close_inactive()
                if resultpath.exists():
                    r.trust(resultpath,0o644,995);result=json.loads(resultpath.read_bytes())
                    if result.get('nonce')!=claim['nonce']:raise ValueError('worker nonce mismatch')
                    done.append(verify_cabinet(c,result));progress('RUNNING',done,c);break
                if c=='ozon_dmitrieva':raise ValueError('accepted completed cabinet receipt disappeared')
                evidence=interrupted_reconcile(c)
                progress('PAUSED_RECOVERABLE',done,c,retained_days=evidence['completed_days'],retained_entries=evidence['entries'])
                if STOP:raise Paused('controller pause')
                try:activation(c,claim)
                except (socket.gaierror,ConnectionError,Paused,subprocess.TimeoutExpired):
                    # Only safe before activation intent exists. Other setup states remain HOLD.
                    if (LEDGER/'activation-intent.json').exists() or (LEDGER/'activation.json').exists():raise
                    progress('PAUSED_NETWORK_OR_SERVICE',done,c);time.sleep(15);continue
                progress('RUNNING',done,c)
            else:
                a=trusted_context()
                if a:
                    if state()['ActiveState'] not in ('inactive','failed'):
                        # Only fixed authorization expiry may stop the exact owned worker.
                        try:r.run(['/usr/bin/systemctl','stop',r.SERVICE],timeout=100)
                        except (RuntimeError,subprocess.TimeoutExpired):raise Paused('awaiting expiry cleanup')
                    close_inactive()
                raise ValueError('fixed recovery authorization expired')
        rule=RULE
        own=json.loads((ROOT/'setup-ownership.json').read_bytes())
        if rule.exists():
            r.trust(rule,0o644)
            if r.sha(rule.read_bytes())!=own['rule_sha256']:raise OwnershipUncertain('foreign start policy')
            rule.unlink();r.syncdir(rule.parent)
        progress('VERIFIED',done)
        if not (LEDGER/'DONE').exists():r.save(LEDGER/'DONE',b'VERIFIED\n',0o600)
        return 0

def verify():
    d=json.loads(PUBLIC.read_bytes())
    if d.get('status')!='VERIFIED' or [x['cabinet'] for x in d['completed_cabinets']]!=list(CABINETS):raise ValueError('recovery incomplete')
    reports=[json.loads(r.run(child(c,'verify_results.py'),timeout=3600)) for c in CABINETS]
    s=state()
    if s['ActiveState'] not in ('inactive','failed') or s['PrivateNetwork']!='yes' or s['DropInPaths'] or (LEDGER/'activation.json').exists():raise ValueError('cleanup not verified')
    print(json.dumps(dict(verification='PASS',verified_days=sum(x['verified_days'] for x in reports),verified_rows=sum(x['verified_rows'] for x in reports),cabinets=list(CABINETS))))

def fail_recovery(exc):
    prior=json.loads(PUBLIC.read_bytes()) if PUBLIC.exists() else {}
    if STOP:
        progress('PAUSED_CONTROLLER_LINK',prior.get('completed_cabinets',[]),prior.get('current_cabinet'))
        return 75
    if not (LEDGER/'HOLD').exists():r.save(LEDGER/'HOLD',b'RECONCILIATION_REQUIRED\n',0o600)
    import traceback
    frames=[dict(file=Path(f.filename).name,function=f.name,line=f.lineno) for f in traceback.extract_tb(exc.__traceback__)[-6:]]
    progress('HOLD',prior.get('completed_cabinets',[]),prior.get('current_cabinet'),error_type=type(exc).__name__,frames=frames)
    return 2


def signal_pause(signum,frame):
    global STOP
    STOP=True
if __name__=='__main__':
    if sys.argv[1:]==['--verify']:verify()
    elif not sys.argv[1:]:
        signal.signal(signal.SIGTERM,signal_pause);signal.signal(signal.SIGINT,signal_pause)
        try:raise SystemExit(run_campaign())
        except (Paused,BlockingIOError):
            # Keep owned worker and controls intact; systemd restarts and reattaches.
            prior=json.loads(PUBLIC.read_bytes()) if PUBLIC.exists() else {}
            progress('PAUSED_CONTROLLER_LINK',prior.get('completed_cabinets',[]),prior.get('current_cabinet'))
            raise SystemExit(75)
        except OwnershipUncertain as exc:
            # No cleanup or stop is safe when identity is uncertain.
            prior=json.loads(PUBLIC.read_bytes()) if PUBLIC.exists() else {}
            if not (LEDGER/'HOLD').exists():r.save(LEDGER/'HOLD',b'OWNERSHIP_UNCERTAIN\n',0o600)
            progress('HOLD_OWNERSHIP',prior.get('completed_cabinets',[]),prior.get('current_cabinet'),error_type=type(exc).__name__);raise SystemExit(2)
        except Exception as exc:raise SystemExit(fail_recovery(exc))
    else:raise ValueError('fixed command only')
