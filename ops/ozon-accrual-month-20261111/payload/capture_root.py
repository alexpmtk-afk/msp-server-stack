"""January accrual capture through same executor; no verified-coverage claim."""
import fcntl,ipaddress,json,os,pwd,socket,sys,time,uuid,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import root_common as r
ROOT=Path(__file__).resolve().parent
STATE=r.ARCHIVE/'ozon-accrual-month-pilot-20261111'
PUBLIC=Path('/var/lib/msp-finance-control/results/ozon-accrual-month-pilot-20261111.json')
LEDGER=Path('/var/lib/msp-ozon-accrual-month-pilot-20261111')
SERVICE='msp-ozon-accrual-month-20261111.service'
CABINET='ozon_dmitrieva'
PERIOD='2026-01'

SEED_ROOT=Path('/opt/mcp/data/msp-marketplace-reports/ozon-accrual-pilot-20261111')
SEEDS={'types':'1d96c2089b339c9d8dbab370e671d6668cb93a2be3345ac17cde76543eab16ea','day-first-page':'519e96177e0786d2d49f6eedc53fe0d10e0d0f7c4c90c72e9fc42a66c2ddf747'}

def replace(path,raw,mode=0o644):
    if path.exists():r.trust(path)
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    r.save(tmp,raw,mode);os.replace(tmp,path);r.syncdir(path.parent)

def mkdir(path,mode,uid=0,gid=0):
    os.mkdir(path,mode);os.chown(path,uid,gid);os.chmod(path,mode);r.syncdir(path.parent)

def preflight():
    r.verify_payload();r.validate_platform()
    status=r.show()
    if status['ActiveState'] not in ('inactive','failed') or status['PrivateNetwork']!='yes' or status['DropInPaths']:
        raise ValueError('existing executor busy or not isolated')
    account=pwd.getpwnam('msp-reports')
    if (account.pw_uid,account.pw_gid)!=(995,985):raise ValueError('executor identity drift')
    r.trust(r.ARCHIVE,0o711,995)
    for p in (STATE,PUBLIC,LEDGER,ROOT/'job.json',ROOT/'cabinets.json',r.DROP):
        if p.exists() or p.is_symlink():raise ValueError('prior attempt; no reset or duplicate start')
    if r.DROP.parent.exists():
        r.trust(r.DROP.parent,0o755)
        if any(r.DROP.parent.iterdir()):raise ValueError('foreign controls')
    r.trust(r.MASTER,0o600)
    cred=json.loads(r.MASTER.read_bytes()).get(CABINET)
    if not isinstance(cred,dict) or any(type(cred.get(k)) is not str or not cred[k].strip() for k in ('client_id','api_key')):
        raise ValueError('cabinet credentials unavailable')
    if not cred['client_id'].isascii() or not cred['client_id'].isdecimal():raise ValueError('Client-Id invalid')
    addresses={str(ipaddress.ip_address(x[4][0])) for x in socket.getaddrinfo('api-seller.ozon.ru',443,type=socket.SOCK_STREAM)}
    if not addresses or len(addresses)>32 or any(not ipaddress.ip_address(x).is_global for x in addresses):raise ValueError('provider DNS bounds')
    dns={str(ipaddress.ip_address(l.split()[1])) for l in Path('/etc/resolv.conf').read_text().splitlines() if l.split()[:1]==['nameserver']}
    if not dns or len(dns)>6:raise ValueError('resolver bounds')
    allow=[x+('/32' if ipaddress.ip_address(x).version==4 else '/128') for x in sorted(addresses|dns|{'127.0.0.1'})]
    for label,digest in SEEDS.items():
        path=SEED_ROOT/(label+'.response.json');r.trust(path,0o644,995)
        if r.sha(path.read_bytes())!=digest:raise ValueError('accepted seed changed')
    return {k:cred[k] for k in ('client_id','api_key')},allow

def unit_text(allow):
    return (r.unit_condition_override(ROOT/'job.json')+'[Service]\nPrivateNetwork=no\n'
      'EnvironmentFile='+str(r.ENV)+'\nEnvironment=MARKETPLACE_REQUIRE_REDIS=1 MSP_REPORTS_SHARED_QUEUE_VERIFIED=YES\n'
      'Environment=HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= http_proxy= https_proxy= all_proxy=\n'
      'LoadCredential=\nLoadCredential=cabinets.json:'+str(ROOT/'cabinets.json')+'\n'
      'IPAddressAllow='+' '.join(allow)+'\nExecStart=\nExecStart='+str(r.RUNTIME/'bin/python')+' -I -B '+str(ROOT/'capture_worker.py')+'\n'
      'Restart=no\nRuntimeMaxSec=10800\nTimeoutStartSec=10800\nStandardOutput=null\nStandardError=file:'+str(LEDGER/'worker.stderr')+'\n').encode()

def cleanup_owned():
    ownership=LEDGER/'activation.json'
    if not ownership.exists():return
    r.trust(ownership,0o600);saved=json.loads(ownership.read_bytes())
    if r.DROP.exists():
        r.trust(r.DROP,0o644)
        if r.sha(r.DROP.read_bytes())!=saved['drop_sha256']:raise ValueError('foreign activation; not stopping')
        if r.show()['ActiveState'] not in ('inactive','failed'):r.run(['/usr/bin/systemctl','stop',r.SERVICE])
        if r.show()['ActiveState'] not in ('inactive','failed'):raise ValueError('executor still active')
        r.DROP.unlink();r.syncdir(r.DROP.parent);r.run(['/usr/bin/systemctl','daemon-reload'])
    restored=r.show()
    if restored['PrivateNetwork']!='yes' or restored['DropInPaths'] or restored['ActiveState'] not in ('inactive','failed'):
        raise ValueError('isolation restoration not proven')
    credential=ROOT/'cabinets.json'
    if credential.exists():
        r.trust(credential,0o640)
        if r.sha(credential.read_bytes())!=saved['credential_sha256']:raise ValueError('foreign credential copy')
        credential.unlink();r.syncdir(ROOT)
    ownership.rename(LEDGER/'activation-removed.json');r.syncdir(LEDGER)

def execute():
    if os.geteuid()!=0:raise PermissionError('root console required')
    r.verify_payload();lock=Path('/var/lib/msp-finance-control/controller.lock');r.trust(lock,0o600)
    with lock.open('rb') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        cred,allow=preflight();mkdir(LEDGER,0o700);mkdir(STATE,0o755,995,985)
        for label in SEEDS:r.save(STATE/(label+'.seed.json'),(SEED_ROOT/(label+'.response.json')).read_bytes(),0o644)
        result={'status':'STARTING','cabinet':CABINET,'period':PERIOD,'max_send_entries':128,'provider_coverage_verified':False}
        replace(PUBLIC,r.doc(result))
        credential_raw=r.doc({CABINET:cred});drop=unit_text(allow)
        job={'cabinet':CABINET,'period':PERIOD,'max_send_entries':128,'nonce':uuid.uuid4().hex,'expires_epoch':time.time()+10800}
        r.save(LEDGER/'activation.json',r.doc({'drop_sha256':r.sha(drop),'credential_sha256':r.sha(credential_raw)}),0o600)
        try:
            r.save(ROOT/'cabinets.json',credential_raw,0o640,985);r.save(ROOT/'job.json',r.doc(job),0o644)
            r.prepare_drop_directory(r.DROP.parent,recovering=False);r.save(r.DROP,drop,0o644)
            r.run(['/usr/bin/systemctl','daemon-reload'])
            try:r.run(['/usr/bin/systemctl','start',r.SERVICE],timeout=10830)
            except Exception:pass # receipt/isolation below decide; no automatic repeat.
            receipt=STATE/'worker-result.json'
            if not receipt.exists():raise ValueError('no worker receipt; preserve unknown outcome')
            r.trust(receipt,0o644,995);result=json.loads(receipt.read_bytes())
            if result.get('status')=='MONTH_COLLECTED_NOT_RECONCILED' and (result.get('nonce')!=job['nonce'] or result.get('cabinet')!=CABINET or result.get('period')!=PERIOD):raise ValueError('receipt scope')
        except Exception as exc:
            result={'status':'HOLD','error_type':type(exc).__name__,'frames':[{'file':Path(f.filename).name,'function':f.name,'line':f.lineno} for f in traceback.extract_tb(exc.__traceback__)[-6:]],'provider_coverage_verified':False}
        finally:
            try:cleanup_owned();result['temporary_activation_removed']=True
            except Exception as exc:result={'status':'HOLD_CLEANUP_UNCONFIRMED','error_type':type(exc).__name__,'provider_coverage_verified':False}
            result['root_release']=str(ROOT);replace(PUBLIC,r.doc(result))
        return 0 if result['status']=='MONTH_COLLECTED_NOT_RECONCILED' else 1

if __name__=='__main__':
    if sys.argv[1:]==['--cleanup']:cleanup_owned()
    elif not sys.argv[1:]:raise SystemExit(execute())
    else:raise ValueError('fixed capture only')
