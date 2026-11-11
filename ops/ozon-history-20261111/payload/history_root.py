"""Fixed Jan-Oct2026 campaign: same executor, controller lock and Redis admission."""
import fcntl,json,os,pwd,re,subprocess,sys,time,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_root as r

ROOT=Path(__file__).resolve().parent
ARCHIVE=Path('/opt/mcp/data/msp-marketplace-reports')
HISTORY=ARCHIVE/'ozon-final-2026'
PUBLIC=Path('/var/lib/msp-finance-control/results/ozon-history-2026.json')
LEDGER=Path('/var/lib/msp-ozon-history-20261111')
CABINETS=('ozon_dmitrieva','ozon_laser_master','ozon_novokshenov')
JOBS=[(cabinet,month) for cabinet in CABINETS for month in range(1,11)]
DROP=r.DROP
SERVICE=r.SERVICE

def replace(path,raw,mode=0o644):
    if path.exists():
        r.trust(path)
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    r.save(temp,raw,mode)
    os.replace(temp,path);r.syncdir(path.parent)

def progress(status,results,**extra):
    document={'status':status,'year':2026,'from_month':1,'to_month':10,
              'expected_monthly_reports':30,'completed_monthly_reports':len(results),
              'reports':results,'root_release':str(ROOT),'background_model_calls':0,
              'scope':'realization by posting only; not all Ozon expenses or bank payouts',**extra}
    replace(PUBLIC,r.doc(document))
    if json.loads(PUBLIC.read_bytes())!=document:
        raise ValueError('public status readback mismatch')

def mkdir_owned(path,mode,uid=0,gid=0):
    os.mkdir(path,mode);os.chown(path,uid,gid);os.chmod(path,mode);r.syncdir(path.parent)

def preflight():
    r.verify_payload();r.validate_platform()
    status=r.show()
    if status['ActiveState'] not in ('inactive','failed') or status['PrivateNetwork']!='yes' or status['DropInPaths']:
        raise ValueError('executor not inactive and isolated')
    account=pwd.getpwnam('msp-reports')
    if (account.pw_uid,account.pw_gid)!=(995,985):raise ValueError('executor identity')
    r.trust(ARCHIVE,0o711,995)
    for p in (HISTORY,LEDGER,PUBLIC,ROOT/'job.json',ROOT/'cabinets.json',DROP):
        if p.exists() or p.is_symlink():raise ValueError('existing campaign; no budget reset')
    if DROP.parent.exists():
        r.trust(DROP.parent,0o755)
        if any(DROP.parent.iterdir()):raise ValueError('foreign activation files')
    r.trust(r.MASTER,0o600)
    all_credentials=json.loads(r.MASTER.read_bytes())
    minimal={}
    for cabinet in CABINETS:
        cred=all_credentials.get(cabinet)
        if not isinstance(cred,dict) or any(not isinstance(cred.get(k),str) or not cred[k].strip() for k in ('client_id','api_key')):
            raise ValueError('Ozon cabinet credentials unavailable')
        if not cred['client_id'].isascii() or not cred['client_id'].isdecimal():raise ValueError('quota identity')
        minimal[cabinet]={k:cred[k] for k in ('client_id','api_key')}
    # Pinned actual accepted pilot; no second January Dmitrieva request.
    pilot=ARCHIVE/'ozon-pilot-20261110'
    if r.sha((pilot/'response.json').read_bytes())!='e2373acc17d2dedbbc8dacc8a072d8ecb9bc1b8b02e54bc24d3b434933cc5e49' or r.sha((pilot/'report.csv').read_bytes())!='3e95d6d28b8f54c0e4420abb82b57d0781b538164987b01323734102fe458134':
        raise ValueError('pilot provenance changed')
    import ipaddress,socket
    addresses={str(ipaddress.ip_address(x[4][0])) for x in socket.getaddrinfo('api-seller.ozon.ru',443,type=socket.SOCK_STREAM)}
    if not addresses or len(addresses)>32 or any(not ipaddress.ip_address(x).is_global for x in addresses):raise ValueError('DNS bounds')
    dns={str(ipaddress.ip_address(l.split()[1])) for l in Path('/etc/resolv.conf').read_text().splitlines() if l.split()[:1]==['nameserver']}
    if not dns or len(dns)>6:raise ValueError('resolver bounds')
    allow=[x+('/32' if ipaddress.ip_address(x).version==4 else '/128') for x in sorted(addresses|dns|{'127.0.0.1'})]
    return minimal,allow

def unit_text(allow,state):
    return (r.unit_condition_override(ROOT/'job.json')+'[Service]\nPrivateNetwork=no\n'
        'EnvironmentFile='+str(r.ENV)+'\nEnvironment=MARKETPLACE_REQUIRE_REDIS=1 MSP_REPORTS_SHARED_QUEUE_VERIFIED=YES\n'
        'Environment=HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= http_proxy= https_proxy= all_proxy=\n'
        'LoadCredential=\nLoadCredential=cabinets.json:'+str(ROOT/'cabinets.json')+'\n'
        'IPAddressAllow='+' '.join(allow)+'\nExecStart=\nExecStart='+str(r.RUNTIME/'bin/python')+' -I -B '+str(ROOT/'history_worker.py')+'\n'
        'Restart=no\nRuntimeMaxSec=180\nTimeoutStartSec=180\nStandardOutput=null\n'
        'StandardError=file:'+str(state)+'\n').encode()

def activate(job,cred,allow,state):
    nonce=job['nonce']
    credential_raw=r.doc({job['cabinet']:cred})
    drop=unit_text(allow,state/'runs'/(nonce+'.stderr'))
    ownership={'nonce':nonce,'drop_sha256':r.sha(drop),'credential_sha256':r.sha(credential_raw)}
    # Private ownership checkpoint, before activation; never publish credential digest.
    r.save(LEDGER/'activation.json',r.doc(ownership),0o600)
    try:
        r.save(ROOT/'cabinets.json',credential_raw,0o640,985)
        replace(ROOT/'job.json',r.doc(job))
        r.prepare_drop_directory(DROP.parent,recovering=False)
        r.save(DROP,drop,0o644)
        r.run(['/usr/bin/systemctl','daemon-reload'])
        try:r.run(['/usr/bin/systemctl','start',SERVICE],timeout=200)
        except RuntimeError:pass
    finally:
        cleanup_owned()
    receipt=state/'runs'/(nonce+'.json')
    if not receipt.exists():
        status=r.show()
        return {'status':'HOLD_NO_WORKER_RECEIPT','cabinet':job['cabinet'],'period':f"2026-{job['month']:02d}",
                'entry_consumed':(state/'entry.json').exists(),
                'executor_state':{k:status.get(k) for k in ('ConditionResult','Result','ExecMainStatus','ExecMainStartTimestamp')}}
    r.trust(receipt,0o644,995)
    result=json.loads(receipt.read_bytes())
    if result.get('nonce')!=nonce or result.get('cabinet')!=job['cabinet'] or result.get('period')!=f"2026-{job['month']:02d}":
        raise ValueError('worker receipt identity')
    # Financial values, arbitrary messages and credentials never enter progress.
    allowed={'status','cabinet','period','nonce','rows','csv_sha256','response_sha256','generation',
             'published_sha256','published_manifest_sha256','provider_coverage','provider_http_status',
             'max_send_entries','annual_coverage_complete','wait_seconds','entry_consumed',
             'response_retained','error_type','frames'}
    return {k:v for k,v in result.items() if k in allowed}

def cleanup_owned():
    ownership=LEDGER/'activation.json'
    if not ownership.exists():return
    r.trust(ownership,0o600)
    saved=json.loads(ownership.read_bytes())
    if not re.fullmatch('[0-9a-f]{32}',saved.get('nonce','')):raise ValueError('ownership nonce')
    if DROP.exists():
        r.trust(DROP)
        if r.sha(DROP.read_bytes())!=saved['drop_sha256']:raise ValueError('foreign activation; do not stop')
        if r.show()['ActiveState'] not in ('inactive','failed'):
            r.run(['/usr/bin/systemctl','stop',SERVICE])
        if r.show()['ActiveState'] not in ('inactive','failed'):raise ValueError('worker still active')
        DROP.unlink();r.syncdir(DROP.parent)
        r.run(['/usr/bin/systemctl','daemon-reload'])
    restored=r.show()
    if restored['PrivateNetwork']!='yes' or restored['DropInPaths']:raise ValueError('network restoration not proven')
    credential=ROOT/'cabinets.json'
    if credential.exists():
        r.trust(credential,0o640)
        if r.sha(credential.read_bytes())!=saved['credential_sha256']:raise ValueError('foreign credential copy')
        credential.unlink();r.syncdir(ROOT)
    ownership.rename(LEDGER/('activation-'+saved['nonce']+'.json'));r.syncdir(LEDGER)

def execute():
    if os.geteuid()!=0:raise PermissionError('root only')
    lock=Path('/var/lib/msp-finance-control/controller.lock');r.trust(lock,0o600)
    results=[]
    with lock.open('rb') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        minimal,allow=preflight()
        mkdir_owned(LEDGER,0o700)
        r.save(LEDGER/'plan.json',r.doc({'jobs':JOBS,'max_send_entries_per_month':1,'existing_pilot':'reuse without transport'}))
        mkdir_owned(HISTORY,0o755,995,985)
        for cabinet in CABINETS:mkdir_owned(HISTORY/cabinet,0o755,995,985)
        progress('RUNNING',results)
        try:
            for cabinet,month in JOBS:
                state=HISTORY/cabinet/f'2026-{month:02d}'
                mkdir_owned(state,0o755,995,985);mkdir_owned(state/'runs',0o755,995,985)
                waits=0
                while True:
                    job={'cabinet':cabinet,'month':month,'year':2026,'nonce':uuid.uuid4().hex,'expires_epoch':time.time()+300}
                    r.save(LEDGER/(job['nonce']+'.json'),r.doc(job))
                    progress('RUNNING',results,current={'cabinet':cabinet,'period':f'2026-{month:02d}'})
                    result=activate(job,minimal[cabinet],allow,state)
                    if result['status']=='WAIT_QUOTA' and result.get('entry_consumed') is False and waits<10:
                        waits+=1
                        progress('WAIT_QUOTA',results,current=result)
                        time.sleep(min(60,max(1,result.get('wait_seconds',60))))
                        continue
                    if result['status']!='COMPLETE':
                        progress('HOLD',results,current=result);return 1
                    results.append(result)
                    progress('RUNNING',results)
                    break
                # Separate from shared admission: additional conservative campaign pacing.
                if len(results)<30:time.sleep(65)
            if {(x['cabinet'],x['period']) for x in results}!={(c,f'2026-{m:02d}') for c,m in JOBS}:
                raise ValueError('campaign coverage identity mismatch')
            progress('COMPLETE',results,closed_month_realization_coverage_complete=True,
                     temporary_activation_removed=True,new_provider_send_entries_max=29)
            return 0
        except Exception as exc:
            import traceback
            progress('HOLD',results,error_type=type(exc).__name__,
                     frames=[{'file':Path(f.filename).name,'function':f.name,'line':f.lineno} for f in traceback.extract_tb(exc.__traceback__)[-6:]])
            raise

if __name__=='__main__':
    if sys.argv[1:]==['--cleanup']:
        cleanup_owned()
    elif not sys.argv[1:]:
        raise SystemExit(execute())
    else:
        raise SystemExit('fixed campaign accepts no arguments')
