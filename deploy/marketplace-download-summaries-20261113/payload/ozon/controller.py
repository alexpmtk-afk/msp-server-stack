"""Fixed bounded recovery of the interrupted Nov1-13 Ozon campaign."""
import os,sys,json,time,uuid,fcntl,socket,ipaddress,pwd,subprocess,signal
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import root_common as r
from recovery import wait_worker,Paused,StartNotificationLost
ROOT=Path(__file__).resolve().parent
BASE=Path('/var/lib/msp-ozon-daily')
DAY=None
CABINETS=('ozon_dmitrieva','ozon_novokshenov','ozon_laser_master')
LEDGER=None
PUBLIC=Path('/var/lib/msp-finance-control/results/ozon-daily.json')
UNIT='msp-ozon-daily.service'
TASK='ozon-daily'
RULE=None
DROP=Path('/run/systemd/system/msp-wb-pilot.service.d/96-ozon-daily.conf')
PERIOD='2026-11'
SEED=Path('/opt/mcp/data/msp-marketplace-reports/ozon-accrual-month-pilot-20261111/types.seed.json')
TYPE_SHA='1d96c2089b339c9d8dbab370e671d6668cb93a2be3345ac17cde76543eab16ea'
STOP=False
class OwnershipUncertain(ValueError):pass
class ManagerUnavailable(Paused):pass

def replace(path,value,mode=0o644):
    if path.exists():r.trust(path,mode)
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp');r.save(tmp,r.doc(value),mode);os.replace(tmp,path);r.syncdir(path.parent)

def history(c):return r.ARCHIVE/'ozon-daily-accruals'/c
def cab_public(c):return Path('/var/lib/msp-finance-control/results')/('ozon-current-recovery-'+c+'-20261113.json')
def job_path(c):return LEDGER/(c+'.job.json')
def child(c,script,*args):return ['/usr/bin/env','MSP_OZON_JOB='+str(job_path(c)),'/usr/bin/python3','-I','-B',str(ROOT/c/script),*args]

def progress(status,done,cabinet=None,**extra):
    value=dict(status=status,day=DAY,cabinets=list(CABINETS),completed_cabinets=done,current_cabinet=cabinet or 'verify',current_month_provisional=True,background_model_calls=0,root_release=str(ROOT),**extra)
    if not PUBLIC.exists() or json.loads(PUBLIC.read_bytes())!=value:replace(PUBLIC,value)
    if LEDGER:
        replace(LEDGER/'progress.json',value)

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
    r.trust(job_path(c),0o644)
    if r.sha((job_path(c)).read_bytes())!=a['job_sha256']:raise OwnershipUncertain('foreign job')
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
    expected=[(job_path(c),r.doc(a['job']),0o644,0),(ROOT/c/'cabinets.json',rawcred,0o640,985),(DROP,a['drop_text'].encode(),0o644,0)]
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
    job=dict(cabinet=c,period=PERIOD,day=DAY,max_send_entries=10,nonce=claim['nonce'],expires_epoch=0,cycle_id=CYCLE_ID,attempt=ATTEMPT)
    rawcred=r.doc({c:{k:creds[k] for k in ('client_id','api_key')}})
    drop=(r.unit_condition_override(job_path(c))+'[Service]\nPrivateNetwork=no\nEnvironment=MSP_OZON_JOB='+str(job_path(c))+'\nEnvironmentFile='+str(r.ENV)+'\nEnvironment=MARKETPLACE_REQUIRE_REDIS=1 MSP_REPORTS_SHARED_QUEUE_VERIFIED=YES\nLoadCredential=\nLoadCredential=cabinets.json:'+str(ROOT/c/'cabinets.json')+'\nIPAddressAllow='+' '.join(allow)+'\nEnvironment=HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= http_proxy= https_proxy= all_proxy=\nExecStart=\nExecStart='+str(r.RUNTIME/'bin/python')+' -I -B '+str(ROOT/c/'capture_worker.py')+'\nRestart=no\nTimeoutStopSec=90\nTimeoutStartSec=100000\nStandardOutput=null\nStandardError=file:'+str(LEDGER/(c+'.stderr'))+'\n').encode()
    attempt=uuid.uuid4().hex
    # Write intent before any activation mutation; partial setup is explicit HOLD, never assumed absent.
    r.save(LEDGER/'activation-intent.json',r.doc(dict(cabinet=c,attempt=attempt,deadline=claim['deadline'],job=job,drop_text=drop.decode(),drop_sha256=r.sha(drop),job_sha256=r.sha(r.doc(job)),credential_sha256=r.sha(rawcred))),0o600)
    finish_intent()



def signal_pause(signum,frame):
    global STOP
    STOP=True


def reconcile_after_boot():
    path=LEDGER/'activation.json'
    if not path.exists() or DROP.exists():return
    r.trust(path,0o600);a=json.loads(path.read_bytes())
    if a.get('phase','').startswith('closing'):return
    s=state()
    if s['ActiveState'] not in ('inactive','failed') or s['PrivateNetwork']!='yes' or s['DropInPaths']:raise OwnershipUncertain('runtime controls vanished while worker alive/foreign')
    if a['cabinet'] not in CABINETS:raise OwnershipUncertain('activation cabinet')
    p=job_path(a['cabinet']);r.trust(p,0o644)
    if r.sha(p.read_bytes())!=a['job_sha256']:raise OwnershipUncertain('reboot job drift')
    # /run is volatile across a real reboot. Close only this proven inactive
    # activation; source pages/budget and root job survive, fresh DNS next start.
    a['phase']='closing_after_boot';replace(path,a,0o600)
    close_inactive()


import datetime,stat
import plan
TZ=plan.TZ
FIRST=plan.FIRST
CYCLE_ID=None
ATTEMPT=None
ACTIVE_CYCLE=None
REQUESTS=Path('/home/hermes/.local/state/msp-ozon-daily-requests')

def mkdir(path,uid=0):
    if path.exists():r.trust(path,0o755,uid)
    else:
        os.mkdir(path,0o755);os.chown(path,uid,985 if uid==995 else 0);os.chmod(path,0o755);r.syncdir(path.parent)

def context(cycle,job):
    global DAY,PERIOD,LEDGER,CYCLE_ID,ATTEMPT
    DAY=job['day'];PERIOD=DAY[:7];CYCLE_ID=cycle['cycle_id'];ATTEMPT=job['attempts']
    directory=BASE/'runs';mkdir(directory);directory=directory/CYCLE_ID;mkdir(directory)
    directory=directory/DAY;mkdir(directory);directory=directory/job['cabinet'];mkdir(directory)
    LEDGER=directory/('attempt-%02d'%ATTEMPT);mkdir(LEDGER)
    p=LEDGER/'claim.json'
    if not p.exists():r.save(p,r.doc({'nonce':uuid.uuid4().hex}),0o600)
    r.trust(p,0o600);claim=json.loads(p.read_bytes())
    h=history(job['cabinet'])
    for path in (h,h/DAY,h/DAY/CYCLE_ID,h/DAY/CYCLE_ID/('attempt-%02d'%ATTEMPT)):mkdir(path,995)
    seed=h/'types.seed.json'
    if not seed.exists():r.save(seed,SEED.read_bytes(),0o644)
    elif r.sha(seed.read_bytes())!=TYPE_SHA:raise ValueError('type seed drift')
    return claim

def source_state(c):return history(c)/DAY/CYCLE_ID/('attempt-%02d'%ATTEMPT)

def interrupted_reconcile(c):
    if not any(source_state(c).iterdir()):return {'completed':False,'rows':0}
    job=json.loads(job_path(c).read_bytes())
    if (job.get('day'),job.get('cabinet'),job.get('cycle_id'),job.get('attempt'))!=(DAY,c,CYCLE_ID,ATTEMPT):raise OwnershipUncertain('saved job identity mismatch')
    return json.loads(r.run(child(c,'capture_worker.py','--probe'),timeout=60))

def checked_result(c,claim,path):
    r.trust(path,0o644,995);result=json.loads(path.read_bytes())
    if result.get('cabinet')!=c or result.get('day')!=DAY:raise ValueError('worker result scope')
    if result.get('status')=='HOLD':return {'status':'HOLD','cabinet':c,'day':DAY,'error_type':result.get('error_type'),'frames':result.get('frames',[])}
    if (result.get('nonce'),result.get('cycle_id'),result.get('attempt'))!=(claim['nonce'],CYCLE_ID,ATTEMPT):raise ValueError('worker result identity')
    if result.get('status')=='WAITING_DATA':
        if interrupted_reconcile(c)!={'completed':True,'rows':0}:raise ValueError('empty-day source not verified')
    elif result.get('status')=='VERIFIED':
        actual=json.loads(r.run(child(c,'capture_worker.py','--verify'),timeout=600))
        if actual!=result:raise ValueError('independent readback differs')
    else:raise ValueError('unknown worker result')
    return result

def run_one(cycle,job):
    c=job['cabinet'];claim=context(cycle,job);resultpath=source_state(c)/'worker-result.json'
    finish_intent();reconcile_after_boot()
    old=trusted_context()
    if old and old.get('phase','').startswith('closing'):close_inactive()
    while True:
        if STOP:raise Paused('controller paused')
        a=trusted_context()
        if resultpath.exists() and not a:return checked_result(c,claim,resultpath)
        if a and a['cabinet']!=c:raise OwnershipUncertain('foreign cabinet activation')
        if not a:
            interrupted_reconcile(c)
            try:activation(c,dict(claim,deadline=time.time()+300))
            except (socket.gaierror,ConnectionError,Paused,subprocess.TimeoutExpired):
                if (LEDGER/'activation-intent.json').exists() or (LEDGER/'activation.json').exists():raise
                raise Paused('dependency unavailable before sender')
            continue
        def ownstate():
            if STOP:raise Paused('controller pause')
            current=trusted_context();s=state()
            if current and current.get('phase')=='start_requested' and s['ActiveState'] in ('active','activating','reloading') and s['InvocationID']:
                current.update(phase='working',invocation_id=s['InvocationID']);replace(LEDGER/'activation.json',current,0o600)
            return s['ActiveState']
        def request_start():
            if ownstate() not in ('active','activating','reloading'):
                interrupted_reconcile(c);reload_owned(time.time()+120)
                a.update(phase='start_requested',invocation_id=None);replace(LEDGER/'activation.json',a,0o600)
                try:r.run(['/usr/bin/systemctl','start','--no-block',r.SERVICE])
                except (RuntimeError,subprocess.TimeoutExpired):raise StartNotificationLost('notification unavailable')
            s=state()
            if s['ActiveState'] in ('active','activating','reloading') and s['InvocationID']:
                a.update(phase='working',invocation_id=s['InvocationID']);replace(LEDGER/'activation.json',a,0o600)
        wait_worker(start=request_start,state=ownstate,has_result=resultpath.exists,pause=lambda _:None,deadline=time.time()+3600)
        while state()['ActiveState'] not in ('inactive','failed'):
            if STOP:raise Paused('controller pause')
            time.sleep(1)
        close_inactive()
        if not resultpath.exists():interrupted_reconcile(c);raise Paused('worker interrupted; same attempt resumes')

def cycle_path(cycle):return BASE/'cycles'/(cycle['key']+'.json')
def cycle_public(cycle):return BASE/'cycles'/(cycle['key']+'.public.json')
def persist(cycle):replace(cycle_path(cycle),cycle,0o600)

def publish_cycle(cycle,status=None,**extra):
    status=status or plan.cycle_status(cycle)
    jobs=[{k:j[k] for k in ('cabinet','day','status','attempts','next_due')} for j in cycle['jobs']]
    pending=[j for j in cycle['jobs'] if j['status'] not in plan.TERMINAL]
    value={'status':status,'cycle_id':cycle['cycle_id'],'business_through':cycle['business_through'],'jobs':jobs,'verified_reports':sum(j['status']=='VERIFIED' for j in cycle['jobs']),'waiting_reports':sum(j['status'].startswith('WAITING') for j in cycle['jobs']),'next_check_epoch':min(j['next_due'] for j in pending) if pending else None,'root_release':str(ROOT),'background_model_calls':0,**extra}
    replace(cycle_public(cycle),value);replace(PUBLIC,value)

def attach_cycle(cycle):
    spec={'unit':{'name':UNIT,'scope':'system'},'receipt':{'path':str(cycle_public(cycle)),'require':{'cycle_id':cycle['cycle_id'],'root_release':str(ROOT)},'allow_pending':True,'rules':[{'when':{'status':'VERIFIED'},'code':'done','label':'Все готовые отчёты сверены и сохранены.'},{'when':{'status':'WAITING_NEXT_DAY'},'code':'waiting_system','label':'Отчёт пока не получен. Ожидание следующего дня или ручного запроса.'},{'when':{'status':'WAITING_REPORTS'},'code':'waiting_system','label':'Ожидание данных Ozon; повтор через 20 минут.'},{'when':{'status':'HOLD'},'code':'blocked','label':'Техническая неопределённость требует сверки, это не отсутствие отчёта.'}]}}
    spec['receipt']['rules'].append({'when':{'status':'PAUSED_RECOVERABLE'},'code':'waiting_system','label':'Пауза до восстановления исполнителя; попытка не обнуляется.'})
    path=BASE/'cycles'/(cycle['key']+'.observer.json');replace(path,spec)
    env=['/usr/sbin/runuser','-u','hermes','--','/usr/bin/env','--ignore-environment','HOME=/home/hermes','USER=hermes','PATH=/usr/sbin:/usr/bin:/sbin:/bin','XDG_RUNTIME_DIR=/run/user/1001','DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1001/bus']
    r.run(env+['/usr/bin/python3','-I','-B','/home/hermes/workspace/task-visibility/task.py','ozon-daily-'+cycle['key'],'running','--title','Ozon: ежедневные отчёты','--origin-name','Загрузчик Ozon','--summary','Получить готовые отчёты до '+cycle['business_through'],'--stage','Загрузка и ожидание готовности','--status','Проверка готовности отчётов','--unit',UNIT,'--system','--observer',str(path)])

def notice(cycle,job):
    config=BASE/'schedule.json'
    if config.exists() and json.loads(config.read_bytes()).get('consolidated_notices') is True:return
    if cycle['manual'] or job['status']!='WAITING_NEXT_DAY':return
    directory=BASE/'notices';mkdir(directory)
    path=directory/(cycle['key']+'-'+job['cabinet']+'-'+job['day']+'.json')
    if path.exists():
        r.trust(path,0o600);previous=json.loads(path.read_bytes())
        job['notice_status']='SENT' if previous.get('status')=='SENT' else 'DELIVERY_UNCERTAIN'
        persist(cycle);return # Never resend an uncertain sending intent.
    replace(path,{'status':'SENDING','cycle_id':cycle['cycle_id'],'cabinet':job['cabinet'],'day':job['day']},0o600)
    try:
        raw=r.run(['/usr/sbin/runuser','-u','hermes','--','/usr/bin/python3','-I','-B',str(ROOT/'notify.py'),job['day'],job['cabinet'],'3'],timeout=35)
        answer=json.loads(raw)
        if answer.get('status')!='SENT' or answer.get('chat_id')!=-1002485321031 or answer.get('thread_id')!=758 or type(answer.get('message_id')) is not int:raise ValueError('notice acknowledgement')
    except Exception as exc:answer={'status':'DELIVERY_UNCERTAIN','error_type':type(exc).__name__}
    replace(path,answer,0o600);job['notice_status']=answer['status'];persist(cycle)

def run_cycle(cycle):
    global ACTIVE_CYCLE
    ACTIVE_CYCLE=cycle
    attach_cycle(cycle)
    while True:
        if STOP:raise Paused('service pause')
        job=plan.due_job(cycle,time.time())
        if job is not None:
            if job['status']!='IN_FLIGHT':job['attempts']+=1;job['status']='IN_FLIGHT';persist(cycle)
            publish_cycle(cycle,'RUNNING')
            result=run_one(cycle,job)
            # Catalog checkpoint precedes cycle settlement; replay sees the same
            # attempt receipt if the controller dies between these two commits.
            catalog=json.loads((BASE/'catalog.json').read_bytes())
            catalog[job['key']]={'status':result['status'],'result':result,'cycle_id':cycle['cycle_id'],'receipt':str(source_state(job['cabinet'])/'worker-result.json')}
            replace(BASE/'catalog.json',catalog,0o600)
            plan.settle(job,result,time.time(),cycle['max_attempts']);persist(cycle);notice(cycle,job)
            continue
        for j in cycle['jobs']:notice(cycle,j)
        status=plan.cycle_status(cycle);publish_cycle(cycle,status,notification_uncertain=any(j.get('notice_status')=='DELIVERY_UNCERTAIN' for j in cycle['jobs']))
        if status in plan.TERMINAL:
            cycle['status']=status;persist(cycle);return
        due=min(j['next_due'] for j in cycle['jobs'] if j['status'] not in plan.TERMINAL)
        time.sleep(min(20,max(1,due-time.time())))

def new_cycle(key,manual=None):
    path=BASE/'cycles'/(key+'.json')
    if path.exists():r.trust(path,0o600);return json.loads(path.read_bytes())
    catalog=json.loads((BASE/'catalog.json').read_bytes())
    cycle=plan.make_cycle(datetime.datetime.now(TZ),catalog,manual=manual)
    cycle.update(key=key,cycle_id=uuid.uuid4().hex)
    persist(cycle);return cycle

def checked_request(path):
    descriptor=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        st=os.fstat(descriptor)
        if not stat.S_ISREG(st.st_mode) or st.st_uid!=1001 or stat.S_IMODE(st.st_mode)!=0o600 or st.st_nlink!=1 or st.st_size>2048:raise ValueError('manual request trust')
        raw=os.read(descriptor,2049)
        if len(raw)>2048:raise ValueError('manual request size')
    finally:os.close(descriptor)
    value=json.loads(raw)
    if set(value)!={'request_id','day','cabinets'} or not __import__('re').fullmatch('[0-9a-f]{32}',value['request_id']) or path.name!=value['request_id']+'.json':raise ValueError('request identity')
    plan.make_cycle(datetime.datetime.now(TZ),{},manual=value)
    return value

def archive_request(path,value):
    # Root keeps its own admitted copy; moving the user queue entry never
    # follows a user-controlled symlink into another directory.
    directory=BASE/'manual-admitted';mkdir(directory)
    target=directory/(value['request_id']+'.json')
    if not target.exists():r.save(target,r.doc(value),0o600)
    source=os.open(REQUESTS,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    destination=None
    try:
        st=os.fstat(source)
        if st.st_uid!=1001 or stat.S_IMODE(st.st_mode)!=0o700:raise ValueError('request directory trust')
        destination=os.open('processed',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=source)
        st=os.fstat(destination)
        if st.st_uid!=1001 or stat.S_IMODE(st.st_mode)!=0o700:raise ValueError('processed directory trust')
        os.rename(path.name,path.name,src_dir_fd=source,dst_dir_fd=destination)
        os.fsync(source);os.fsync(destination)
    finally:
        if destination is not None:os.close(destination)
        os.close(source)

def admit_manual():
    for path in sorted(REQUESTS.glob('*.json')):
        value=checked_request(path);key='manual-'+value['request_id']
        cycle=new_cycle(key,manual=value)
        archive_request(path,value)
        if cycle['status'] not in plan.TERMINAL:run_cycle(cycle)

def main():
    if os.geteuid()!=0:raise PermissionError('root required')
    r.verify_payload();r.validate_platform()
    lock=BASE/'controller.lock';r.trust(lock,0o600)
    with lock.open('rb') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        # Complete an interrupted known cycle before admitting another one.
        for path in sorted((BASE/'cycles').glob('*.json')):
            if path.name.endswith(('.public.json','.observer.json')):continue
            cycle=json.loads(path.read_bytes())
            if cycle['status'] not in plan.TERMINAL:run_cycle(cycle)
        admit_manual()
        config=json.loads((BASE/'schedule.json').read_bytes());now=datetime.datetime.now(TZ)
        if now.timestamp()>=config['not_before_epoch'] and (now.hour,now.minute)>=(8,40):
            cycle=new_cycle(now.date().isoformat())
            if cycle['status'] not in plan.TERMINAL:run_cycle(cycle)
        admit_manual()
    return 0

def signal_pause(signum,frame):
    global STOP
    STOP=True

# Hold the shared executor slot only while a worker is actually owned.
# Twenty-minute report-availability waits do not reserve the WB/Ozon executor.
FINANCE_LOCK=Path('/var/lib/msp-finance-control/controller.lock')
_run_one_inner=run_one
def run_one(cycle,job):
    context(cycle,job)
    r.trust(FINANCE_LOCK,0o600)
    with FINANCE_LOCK.open('rb') as slot:
        fcntl.flock(slot,fcntl.LOCK_EX|fcntl.LOCK_NB)
        active=state()['ActiveState'] in ('active','activating','reloading')
        if active and not (LEDGER/'activation.json').exists() and not (LEDGER/'activation-intent.json').exists():raise Paused('shared executor currently busy')
        return _run_one_inner(cycle,job)

if __name__=='__main__':
    signal.signal(signal.SIGTERM,signal_pause);signal.signal(signal.SIGINT,signal_pause)
    try:raise SystemExit(main())
    except (Paused,BlockingIOError):
        if ACTIVE_CYCLE:publish_cycle(ACTIVE_CYCLE,'PAUSED_RECOVERABLE')
        raise SystemExit(75)
    except Exception as exc:
        if STOP:
            if ACTIVE_CYCLE:publish_cycle(ACTIVE_CYCLE,'PAUSED_RECOVERABLE')
            raise SystemExit(75)
        import traceback
        frames=[dict(file=Path(f.filename).name,function=f.name,line=f.lineno) for f in traceback.extract_tb(exc.__traceback__)[-6:]]
        replace(PUBLIC,{'status':'HOLD','error_type':type(exc).__name__,'frames':frames,'root_release':str(ROOT)})
        raise SystemExit(2)
