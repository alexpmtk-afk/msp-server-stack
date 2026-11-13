"""WB daily/Monday-weekly coordinator; shared accepted executor, no models."""
import os,sys,json,time,uuid,fcntl,socket,ipaddress,pwd,subprocess,signal
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import root_common as r
from recovery import wait_worker,Paused,StartNotificationLost
ROOT=Path(__file__).resolve().parent
BASE=Path('/var/lib/msp-wb-daily-weekly')
DAY=None
CABINETS=('wb_dmitrieva','wb_laser_master','wb_novokshenov')
LEDGER=None
PUBLIC=Path('/var/lib/msp-finance-control/results/wb-daily-weekly.json')
UNIT='msp-wb-daily-weekly.service'
TASK='wb-daily-weekly'
RULE=None
DROP=Path('/run/systemd/system/msp-wb-pilot.service.d/97-wb-daily-weekly.conf')
PERIOD='2026-11'
SEED=Path('/opt/mcp/data/msp-marketplace-reports/ozon-accrual-month-pilot-20261111/types.seed.json')
TYPE_SHA='1d96c2089b339c9d8dbab370e671d6668cb93a2be3345ac17cde76543eab16ea'
STOP=False
class OwnershipUncertain(ValueError):pass
class ManagerUnavailable(Paused):pass

def replace(path,value,mode=0o644):
    if path.exists():r.trust(path,mode)
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp');r.save(tmp,r.doc(value),mode);os.replace(tmp,path);r.syncdir(path.parent)

def job_path(c):return LEDGER/(c+'.job.json')
def child(c,script,*args):return ['/usr/bin/env','MSP_REPORT_JOB='+str(job_path(c)),'/usr/bin/python3','-I','-B',str(ROOT/c/script),*args]

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
    p=ROOT/'cabinets.json'
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
    cred=json.loads(r.MASTER.read_bytes())[c];rawcred=r.doc({c:{k:cred[k] for k in ('token',)}})
    expected=[(job_path(c),r.doc(a['job']),0o644,0),(ROOT/'cabinets.json',rawcred,0o640,985),(DROP,a['drop_text'].encode(),0o644,0)]
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
    addresses={str(ipaddress.ip_address(x[4][0])) for x in socket.getaddrinfo('finance-api.wildberries.ru',443,type=socket.SOCK_STREAM)}
    if not addresses or len(addresses)>32 or any(not ipaddress.ip_address(x).is_global for x in addresses):raise ValueError('DNS bounds')
    dns={str(ipaddress.ip_address(x.split()[1])) for x in Path('/etc/resolv.conf').read_text().splitlines() if x.split()[:1]==['nameserver']}
    if not dns or len(dns)>6:raise ValueError('resolver bounds')
    return [x+('/32' if ipaddress.ip_address(x).version==4 else '/128') for x in sorted(addresses|dns|{'127.0.0.1'})]

def activation(c,claim):
    s=state()
    if s['ActiveState'] not in ('inactive','failed') or s['PrivateNetwork']!='yes' or s['DropInPaths']:raise OwnershipUncertain('executor not isolated')
    creds=json.loads(r.MASTER.read_bytes()).get(c)
    if not isinstance(creds,dict) or any(type(creds.get(k)) is not str or not creds[k].strip() for k in ('token',)):raise ValueError('credential scope')
    # DNS/Redis readiness happen before creating owned controls or consuming sender entries.
    allow=dns_allow()
    try:quota_active=r.run(['/usr/bin/systemctl','is-active','msp-quota-redis.service']).strip()==b'active'
    except (RuntimeError,subprocess.TimeoutExpired):raise Paused('quota service unavailable')
    if not quota_active:raise Paused('quota service unavailable')
    job=dict(cabinet=c,period=JOB['period'],date_from=JOB['from'],date_to=JOB['to'],nonce=claim['nonce'],cycle_id=CYCLE_ID,attempt=ATTEMPT,bootstrap=JOB.get('bootstrap',False))
    rawcred=r.doc({c:{k:creds[k] for k in ('token',)}})
    drop=(r.unit_condition_override(job_path(c))+'[Service]\nPrivateNetwork=no\nEnvironment=MSP_REPORT_JOB='+str(job_path(c))+'\nEnvironmentFile='+str(r.ENV)+'\nEnvironment=MARKETPLACE_REQUIRE_REDIS=1 MSP_REPORTS_SHARED_QUEUE_VERIFIED=YES\nLoadCredential=\nLoadCredential=cabinets.json:'+str(ROOT/'cabinets.json')+'\nIPAddressAllow='+' '.join(allow)+'\nEnvironment=HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= http_proxy= https_proxy= all_proxy=\nExecStart=\nExecStart='+str(r.RUNTIME/'bin/python')+' -I -B '+str(ROOT/'worker.py')+'\nRestart=no\nTimeoutStopSec=90\nTimeoutStartSec=100000\nStandardOutput=null\nStandardError=file:'+str(LEDGER/(c+'.stderr'))+'\n').encode()
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



import datetime,importlib.util
import plan,catalog
CYCLE_ID=None
ATTEMPT=None
JOB=None
ACTIVE_CYCLE=None
FINANCE_LOCK=Path('/var/lib/msp-finance-control/controller.lock')

def mkdir(path,uid=0):
    if path.exists():r.trust(path,0o755,uid)
    else:os.mkdir(path,0o755);os.chown(path,uid,985 if uid==995 else 0);os.chmod(path,0o755);r.syncdir(path.parent)

def context(cycle,job):
    global LEDGER,CYCLE_ID,ATTEMPT,JOB
    CYCLE_ID=cycle['cycle_id'];ATTEMPT=job['attempts'];JOB=job
    directory=BASE/'runs';mkdir(directory)
    for name in (CYCLE_ID,job['cabinet'],job['period'],job['from']+'-'+job['to'],'attempt-%02d'%ATTEMPT):directory=directory/name;mkdir(directory)
    LEDGER=directory;claim=LEDGER/'claim.json'
    if not claim.exists():r.save(claim,r.doc({'nonce':uuid.uuid4().hex}),0o600)
    r.trust(claim,0o600)
    directory=r.ARCHIVE/'wb-scheduled-capture'
    for name in (job['cabinet'],CYCLE_ID,job['period']+'-'+job['from']+'-'+job['to'],'attempt-%02d'%ATTEMPT):directory=directory/name;mkdir(directory,995)
    return json.loads(claim.read_bytes())

def source_state(job):return r.ARCHIVE/'wb-scheduled-capture'/job['cabinet']/CYCLE_ID/(job['period']+'-'+job['from']+'-'+job['to'])/('attempt-%02d'%ATTEMPT)

def checked_result(job,claim,path):
    r.trust(path,0o644,995);value=json.loads(path.read_bytes())
    if (value.get('cabinet'),value.get('period'),value.get('date_from'),value.get('date_to'))!=(job['cabinet'],job['period'],job['from'],job['to']):raise ValueError('worker result scope')
    if value['status']=='HOLD':return value
    if value['status'] not in ('VERIFIED','WAITING_DATA') or (value.get('nonce'),value.get('cycle_id'),value.get('attempt'))!=(claim['nonce'],CYCLE_ID,ATTEMPT) or value.get('source_verified') is not True:raise ValueError('worker identity/verification')
    current=json.loads((catalog.root(job['cabinet'])/'CURRENT.json').read_bytes())
    if (current['generation'],current['sha256'])!=(value['view_generation'],value['view_sha256']):raise ValueError('view changed since result')
    for typ in (1,2):
        snap=catalog.snapshot(job['cabinet'],typ,None)
        for _ in catalog.iter_view(snap):pass
    return value

def run_one_inner(cycle,job):
    c=job['cabinet'];claim=context(cycle,job);resultpath=source_state(job)/'result.json'
    finish_intent();reconcile_after_boot()
    old=trusted_context()
    if old and old.get('phase','').startswith('closing'):close_inactive()
    while True:
        if STOP:raise Paused('controller pause')
        a=trusted_context()
        if resultpath.exists() and not a:return checked_result(job,claim,resultpath)
        if a and a['cabinet']!=c:raise OwnershipUncertain('foreign cabinet')
        if not a:
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
        def start():
            if ownstate() not in ('active','activating','reloading'):
                reload_owned(time.time()+120);a.update(phase='start_requested',invocation_id=None);replace(LEDGER/'activation.json',a,0o600)
                try:r.run(['/usr/bin/systemctl','start','--no-block',r.SERVICE])
                except (RuntimeError,subprocess.TimeoutExpired):raise StartNotificationLost('notification unavailable')
            s=state()
            if s['ActiveState'] in ('active','activating','reloading') and s['InvocationID']:a.update(phase='working',invocation_id=s['InvocationID']);replace(LEDGER/'activation.json',a,0o600)
        wait_worker(start=start,state=ownstate,has_result=resultpath.exists,pause=lambda _:None,deadline=time.time()+3600)
        while state()['ActiveState'] not in ('inactive','failed'):
            if STOP:raise Paused('controller pause')
            time.sleep(1)
        close_inactive()
        if not resultpath.exists():raise Paused('same attempt resumes after worker/quota pause')

def run_one(cycle,job):
    context(cycle,job);r.trust(FINANCE_LOCK,0o600)
    with FINANCE_LOCK.open('rb') as slot:
        fcntl.flock(slot,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if state()['ActiveState'] in ('active','activating','reloading') and not (LEDGER/'activation.json').exists() and not (LEDGER/'activation-intent.json').exists():raise Paused('shared executor busy')
        return run_one_inner(cycle,job)

def cycle_path(cycle):return BASE/'cycles'/(cycle['key']+'.json')
def public_path(cycle):return BASE/'cycles'/(cycle['key']+'.public.json')
def persist(cycle):replace(cycle_path(cycle),cycle,0o600)
def publish_cycle(cycle,status=None):
    jobs=[{k:j[k] for k in ('cabinet','period','from','to','attempts','max_attempts','status','next_due')} for j in cycle['jobs']]
    value={'status':status or plan.status(cycle),'cycle_id':cycle['cycle_id'],'marketplace':'wb','through':cycle['through'],'jobs':jobs,'root_release':str(ROOT),'background_model_calls':0}
    replace(public_path(cycle),value);replace(PUBLIC,value)
def attach(cycle):
    spec={'unit':{'name':UNIT,'scope':'system'},'receipt':{'path':str(public_path(cycle)),'require':{'cycle_id':cycle['cycle_id'],'root_release':str(ROOT)},'allow_pending':True,'rules':[{'when':{'status':'VERIFIED'},'code':'done','label':'WB: источники проверены, каталог обновлён.'},{'when':{'status':'WAITING_NEXT_RUN'},'code':'waiting_system','label':'WB: отчёт пока не найден; ожидание следующего запуска.'},{'when':{'status':'WAITING_REPORTS'},'code':'waiting_system','label':'WB: следующая проверка через 20 минут.'},{'when':{'status':'PAUSED_RECOVERABLE'},'code':'waiting_system','label':'WB: ожидание исполнителя или квоты, попытка сохранена.'},{'when':{'status':'HOLD'},'code':'blocked','label':'WB: нужна сверка технически неопределённого ответа.'}]}}
    p=BASE/'cycles'/(cycle['key']+'.observer.json');replace(p,spec)
    r.run(['/usr/sbin/runuser','-u','hermes','--','/usr/bin/env','--ignore-environment','HOME=/home/hermes','USER=hermes','PATH=/usr/sbin:/usr/bin:/sbin:/bin','XDG_RUNTIME_DIR=/run/user/1001','DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1001/bus','/usr/bin/python3','-I','-B','/home/hermes/workspace/task-visibility/task.py','wb-current-'+cycle['key'],'running','--title','WB: финансовые отчёты','--origin-name','Загрузчик Wildberries','--summary','Недельная база и дневные отчёты до '+cycle['through'],'--stage','Загрузка и сверка покрытия','--status','Проверка источников','--unit',UNIT,'--system','--observer',str(p)])
def notice(cycle,job):
    if job['status']!='WAITING_NEXT_RUN' or job['bootstrap']:return
    directory=BASE/'notices';mkdir(directory);p=directory/(cycle['key']+'-'+r.sha(job['key'].encode())[:20]+'.json')
    if p.exists():return
    replace(p,{'status':'SENDING','job':job['key']},0o600)
    missing=','.join(str(x['type']) for x in job.get('result',{}).get('parts',[]) if x['status']!='VERIFIED') or '1,2'
    try:
        value=json.loads(r.run(['/usr/sbin/runuser','-u','hermes','--','/usr/bin/python3','-I','-B',str(ROOT/'notify.py'),job['period'],job['cabinet'],job['from'],job['to'],str(job['attempts']),missing],timeout=35))
        if value.get('status')!='SENT' or value.get('chat_id')!=-1002485321031 or value.get('thread_id')!=758:raise ValueError('notice acknowledgement')
    except Exception as exc:value={'status':'DELIVERY_UNCERTAIN','error_type':type(exc).__name__}
    replace(p,value,0o600)
def run_cycle(cycle):
    global ACTIVE_CYCLE
    ACTIVE_CYCLE=cycle;attach(cycle)
    while True:
        if STOP:raise Paused('controller pause')
        job=plan.due_job(cycle,time.time())
        if job:
            if job['status']!='IN_FLIGHT':job.update(status='IN_FLIGHT',attempts=job['attempts']+1);persist(cycle)
            publish_cycle(cycle,'RUNNING');result=run_one(cycle,job)
            known=json.loads((BASE/'jobs.json').read_bytes());known[job['key']]=result;replace(BASE/'jobs.json',known,0o600)
            plan.settle(job,result,time.time());persist(cycle);notice(cycle,job);continue
        for job in cycle['jobs']:notice(cycle,job)
        status=plan.status(cycle);publish_cycle(cycle,status)
        if status in plan.TERMINAL:cycle['status']=status;persist(cycle);return
        due=min(j['next_due'] for j in cycle['jobs'] if j['status'] not in plan.TERMINAL)
        time.sleep(min(20,max(1,due-time.time())))
def make_cycle(key,bootstrap=False):
    p=BASE/'cycles'/(key+'.json')
    if p.exists():r.trust(p,0o600);return json.loads(p.read_bytes())
    now=datetime.datetime.now(plan.TZ);known=json.loads((BASE/'jobs.json').read_bytes());baseline=json.loads((ROOT/'baseline-coverage.json').read_bytes());coverage=baseline['reports']
    for c in CABINETS:
        index=catalog.load_index(c)
        if index.get('baseline_seeded'):coverage[c]=[r for r in index['reports'].values() if r['period']=='weekly']
    value=plan.make_cycle(now,known,coverage,bootstrap=bootstrap);value.update(key=key,cycle_id=uuid.uuid4().hex);persist(value);return value
def main():
    if os.geteuid()!=0:raise PermissionError('root required')
    r.verify_payload();r.validate_platform();lock=BASE/'controller.lock';r.trust(lock,0o600)
    with lock.open('rb') as life:
        fcntl.flock(life,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for path in sorted((BASE/'cycles').glob('*.json')):
            if path.name.endswith(('.public.json','.observer.json')):continue
            cycle=json.loads(path.read_bytes())
            if cycle['status'] not in plan.TERMINAL:run_cycle(cycle)
        for key,bootstrap in (('bootstrap',True),('initial',False)):
            cycle=make_cycle(key,bootstrap)
            if cycle['status'] not in plan.TERMINAL:run_cycle(cycle)
        config=json.loads((BASE/'schedule.json').read_bytes());now=datetime.datetime.now(plan.TZ)
        if now.timestamp()>=config['not_before_epoch'] and (now.hour,now.minute)>=(8,45):
            cycle=make_cycle(now.date().isoformat())
            if cycle['status'] not in plan.TERMINAL:run_cycle(cycle)
    return 0
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
        replace(PUBLIC,{'status':'HOLD','error_type':type(exc).__name__,'frames':[{'file':Path(f.filename).name,'line':f.lineno,'function':f.name} for f in traceback.extract_tb(exc.__traceback__)[-6:]],'root_release':str(ROOT)})
        raise SystemExit(2)
