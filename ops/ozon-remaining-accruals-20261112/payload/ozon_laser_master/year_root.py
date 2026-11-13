"""Fixed Dmitrieva2026 closed-month campaign via existing finance executor."""
import fcntl,json,os,pwd,socket,ipaddress,sys,time,uuid,traceback,calendar,csv,io
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import root_common as r
ROOT=Path(__file__).resolve().parent
CABINET='ozon_laser_master'
HISTORY=r.ARCHIVE/'ozon-laser-master-accruals-2026-remaining'
LEDGER=Path('/var/lib/msp-ozon-laser-master-accruals-2026-remaining1111')
PUBLIC=Path('/var/lib/msp-finance-control/results/ozon-laser-master-accruals-2026-remaining.json')
UNIT='msp-ozon-laser-master-accruals-2026-remaining.service'
UNIT_FILE=Path('/etc/systemd/system')/UNIT
RULE=Path('/etc/polkit-1/rules.d/48-msp-ozon-laser-master-accruals-2026-remaining.rules')
TASK='ozon-laser-master-accruals-2026-remaining-20261111'
SEED=Path('/opt/mcp/data/msp-marketplace-reports/ozon-accrual-month-pilot-20261111')
JAN_SHA='7089e1dca18b155e8f9e5e4155d8bbd9c86849f18e391cab1db6f2c6ae42d68e'
TYPE_SHA='1d96c2089b339c9d8dbab370e671d6668cb93a2be3345ac17cde76543eab16ea'

def replace(path,raw,mode=0o644):
    if path.exists():r.trust(path)
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    r.save(tmp,raw,mode);os.replace(tmp,path);r.syncdir(path.parent)

def mkdir(path,mode,uid=0,gid=0):
    os.mkdir(path,mode);os.chown(path,uid,gid);os.chmod(path,mode);r.syncdir(path.parent)

def progress(status,months,**extra):
    value={'status':status,'cabinet':CABINET,'year':2026,'from_month':1,'to_month':10,'expected_months':10,'completed_months':len(months),'rows':sum(m['rows'] for m in months),'months':months,'max_new_send_entries':1280,'expected_calendar_days':304,'background_model_calls':0,'root_release':str(ROOT),**extra}
    replace(PUBLIC,r.doc(value));assert json.loads(PUBLIC.read_bytes())==value

def preflight():
    r.verify_payload();r.validate_platform()
    status=r.show()
    if status['ActiveState'] not in ('inactive','failed') or status['PrivateNetwork']!='yes' or status['DropInPaths']:raise ValueError('executor busy/not isolated')
    account=pwd.getpwnam('msp-reports')
    if (account.pw_uid,account.pw_gid)!=(995,985):raise ValueError('executor identity drift')
    r.trust(r.ARCHIVE,0o711,995)
    for p in (HISTORY,LEDGER,PUBLIC,ROOT/'job.json',ROOT/'cabinets.json',r.DROP):
        if p.exists() or p.is_symlink():raise ValueError('existing attempt; no reset/restart')
    if r.DROP.parent.exists():
        r.trust(r.DROP.parent,0o755)
        if any(r.DROP.parent.iterdir()):raise ValueError('foreign controls')
    p=SEED/'types.seed.json';r.trust(p,0o644)
    if r.sha(p.read_bytes())!=TYPE_SHA:raise ValueError('type seed changed')
    r.trust(r.MASTER,0o600);cred=json.loads(r.MASTER.read_bytes()).get(CABINET)
    if not isinstance(cred,dict) or any(type(cred.get(k)) is not str or not cred[k].strip() for k in ('client_id','api_key')):raise ValueError('selected credentials unavailable')
    if not cred['client_id'].isascii() or not cred['client_id'].isdecimal():raise ValueError('Client-Id invalid')
    addresses={str(ipaddress.ip_address(x[4][0])) for x in socket.getaddrinfo('api-seller.ozon.ru',443,type=socket.SOCK_STREAM)}
    if not addresses or len(addresses)>32 or any(not ipaddress.ip_address(x).is_global for x in addresses):raise ValueError('DNS bounds')
    dns={str(ipaddress.ip_address(l.split()[1])) for l in Path('/etc/resolv.conf').read_text().splitlines() if l.split()[:1]==['nameserver']}
    if not dns or len(dns)>6:raise ValueError('resolver bounds')
    allow=[x+('/32' if ipaddress.ip_address(x).version==4 else '/128') for x in sorted(addresses|dns|{'127.0.0.1'})]
    return {k:cred[k] for k in ('client_id','api_key')},allow

def unit_text(allow,state,online):
    text=r.unit_condition_override(ROOT/'job.json')+'[Service]\nPrivateNetwork='+('no' if online else 'yes')+'\nLoadCredential=\n'
    if online:text+='EnvironmentFile='+str(r.ENV)+'\nEnvironment=MARKETPLACE_REQUIRE_REDIS=1 MSP_REPORTS_SHARED_QUEUE_VERIFIED=YES\nLoadCredential=cabinets.json:'+str(ROOT/'cabinets.json')+'\nIPAddressAllow='+' '.join(allow)+'\n'
    return (text+'Environment=HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= http_proxy= https_proxy= all_proxy=\nExecStart=\nExecStart='+str(r.RUNTIME/'bin/python')+' -I -B '+str(ROOT/'capture_worker.py')+'\nRestart=no\nRuntimeMaxSec=10800\nTimeoutStartSec=10800\nStandardOutput=null\nStandardError=file:'+str(LEDGER/(state.name+'.stderr'))+'\n').encode()

def cleanup_worker():
    p=LEDGER/'activation.json'
    if not p.exists():return
    r.trust(p,0o600);owned=json.loads(p.read_bytes())
    if r.DROP.exists():
        r.trust(r.DROP,0o644)
        if r.sha(r.DROP.read_bytes())!=owned['drop_sha256']:raise ValueError('foreign worker controls')
        if r.show()['ActiveState'] not in ('inactive','failed'):r.run(['/usr/bin/systemctl','stop',r.SERVICE])
        if r.show()['ActiveState'] not in ('inactive','failed'):raise ValueError('worker still active')
        r.DROP.unlink();r.syncdir(r.DROP.parent);r.run(['/usr/bin/systemctl','daemon-reload'])
    status=r.show()
    if status['ActiveState'] not in ('inactive','failed') or status['PrivateNetwork']!='yes' or status['DropInPaths']:raise ValueError('isolation not restored')
    credential=ROOT/'cabinets.json'
    if credential.exists():
        r.trust(credential,0o640)
        if r.sha(credential.read_bytes())!=owned['credential_sha256']:raise ValueError('foreign credential copy')
        credential.unlink();r.syncdir(ROOT)
    p.rename(LEDGER/('activation-'+owned['nonce']+'.removed.json'));r.syncdir(LEDGER)

def cleanup_campaign():
    if os.geteuid()!=0:raise PermissionError('root only')
    try:
        cleanup_worker()
        own=ROOT/'setup-ownership.json'
        if own.exists():
            r.trust(own,0o600);owned=json.loads(own.read_bytes())
            if RULE.exists():
                r.trust(RULE,0o644)
                if r.sha(RULE.read_bytes())!=owned['rule_sha256']:raise ValueError('foreign policy; not removing')
                RULE.unlink();r.syncdir(RULE.parent)
        if PUBLIC.exists():
            value=json.loads(PUBLIC.read_bytes());value['activation_policy_removed']=not RULE.exists();replace(PUBLIC,r.doc(value))
    except Exception as exc:
        if PUBLIC.exists():
            value=json.loads(PUBLIC.read_bytes());value.update(status='HOLD_CLEANUP_UNCONFIRMED',error_type=type(exc).__name__);replace(PUBLIC,r.doc(value))
        raise

def activate(month,cred,allow):
    period=f'2026-{month:02d}';state=HISTORY/period;mkdir(state,0o755,995,985)
    job={'cabinet':CABINET,'period':period,'max_send_entries':128,'nonce':uuid.uuid4().hex,'expires_epoch':time.time()+10800}
    rawcred=r.doc({CABINET:cred})
    drop=unit_text(allow,state,True)
    r.save(LEDGER/'activation.json',r.doc({'nonce':job['nonce'],'drop_sha256':r.sha(drop),'credential_sha256':r.sha(rawcred) if rawcred else None}),0o600)
    try:
        if rawcred:r.save(ROOT/'cabinets.json',rawcred,0o640,985)
        replace(ROOT/'job.json',r.doc(job));r.save(LEDGER/(job['nonce']+'.job.json'),r.doc(job),0o600)
        r.prepare_drop_directory(r.DROP.parent,recovering=False);r.save(r.DROP,drop,0o644);r.run(['/usr/bin/systemctl','daemon-reload'])
        try:r.run(['/usr/bin/systemctl','start',r.SERVICE],timeout=10830)
        except Exception:pass
        receipt=state/'worker-result.json'
        if not receipt.exists():raise ValueError('missing worker receipt; no retry')
        r.trust(receipt,0o644,995);result=json.loads(receipt.read_bytes())
        if result.get('status')=='PUBLISHED_SOURCE_VERIFIED':
            if result['nonce']!=job['nonce'] or result['cabinet']!=CABINET or result['period']!=period or result['days_collected']!=calendar.monthrange(2026,month)[1]:raise ValueError('worker receipt scope')
        return result
    finally:cleanup_worker()

def execute():
    if os.geteuid()!=0:raise PermissionError('root only')
    r.verify_payload();r.trust(ROOT/'approval.json',0o644)
    approval=json.loads((ROOT/'approval.json').read_bytes())
    if approval['cabinet']!=CABINET or not time.time()<approval['start_before_epoch']<=time.time()+1200:raise ValueError('startup approval expired/scope')
    lock=Path('/var/lib/msp-finance-control/controller.lock');r.trust(lock,0o600)
    with lock.open('rb') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        cred,allow=preflight();mkdir(LEDGER,0o700);mkdir(HISTORY,0o755,995,985)
        r.save(HISTORY/'types.seed.json',(SEED/'types.seed.json').read_bytes(),0o644)
        months=[];progress('RUNNING',months)
        try:
            for month in range(1,11):
                progress('RUNNING',months,current_period=f'2026-{month:02d}')
                result=activate(month,cred,allow)
                if result.get('status')!='PUBLISHED_SOURCE_VERIFIED':
                    progress('HOLD',months,current=result);return 1
                months.append(result);progress('RUNNING',months)
                if month<10:time.sleep(65)
            from verify_results import verify_months
            verification=verify_months(json.loads(PUBLIC.read_bytes()))
            progress('SOURCE_COLLECTION_COMPLETE',months,**verification,temporary_activation_removed=True,
                     coverage_description='Jan-Oct calendar days traversed according to API cursors; all months source/publication verified; no independent cabinet Excel reconciliation')
            return 0
        except Exception as exc:
            progress('HOLD',months,error_type=type(exc).__name__,frames=[{'file':Path(f.filename).name,'function':f.name,'line':f.lineno} for f in traceback.extract_tb(exc.__traceback__)[-6:]])
            return 1

if __name__=='__main__':
    if sys.argv[1:]==['--cleanup']:cleanup_campaign()
    elif sys.argv[1:]==['--preflight']:preflight()
    elif not sys.argv[1:]:raise SystemExit(execute())
    else:raise ValueError('no arbitrary arguments')
