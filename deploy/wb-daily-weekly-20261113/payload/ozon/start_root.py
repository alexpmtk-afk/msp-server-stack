"""Install only new Ozon daily scheduling; never rerun historical capture."""
import os,sys,json,datetime,fcntl
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parent))
import controller as c
import root_common as r
TIMER='msp-ozon-daily.timer'
WATCH='msp-ozon-daily-requests.path'
RULE=Path('/etc/polkit-1/rules.d/48-msp-ozon-daily.rules')
CLIENT=Path('/usr/local/libexec/msp-ozon-daily-request.py')

def service_text():
    return ('[Unit]\nDescription=Ozon yesterday accruals, three cabinets, durable continuation\nAfter=network-online.target msp-quota-redis.service\nWants=network-online.target\nStartLimitIntervalSec=0\n[Service]\nType=exec\nUser=root\nUMask=0077\nNoNewPrivileges=yes\nRestart=on-failure\nRestartPreventExitStatus=2\nRestartSec=30\nTimeoutStartSec=30\nTimeoutStopSec=90\nStandardOutput=null\nStandardError=file:'+str(c.BASE/'controller.stderr')+'\nExecStart=/usr/bin/python3 -I -B '+str(c.ROOT/'controller.py')+'\n').encode()

def timer_text():
    return ('[Unit]\nDescription=Ozon daily yesterday at 08:40 Moscow\n[Timer]\nOnCalendar=*-*-* 08:40:00 Europe/Moscow\nOnBootSec=5min\nPersistent=false\nAccuracySec=1s\nRandomizedDelaySec=0\nUnit='+c.UNIT+'\n[Install]\nWantedBy=timers.target\n').encode()

def path_text():
    return ('[Unit]\nDescription=Owner manual Ozon past-date queue\n[Path]\nPathExistsGlob='+str(c.REQUESTS)+'/*.json\nUnit='+c.UNIT+'\n[Install]\nWantedBy=multi-user.target\n').encode()

def main():
    if os.geteuid()!=0:raise PermissionError('root console required')
    r.verify_payload();r.validate_platform()
    baseline=json.loads((c.ROOT/'baseline.json').read_bytes())
    public=Path('/var/lib/msp-finance-control/results/ozon-current-recovery-20261113.json')
    r.trust(public,0o644)
    if r.sha(public.read_bytes())!=baseline['recovery_receipt_sha256']:raise ValueError('baseline receipt changed')
    doc=json.loads(public.read_bytes())
    if doc.get('status')!='VERIFIED' or [x['cabinet'] for x in doc['completed_cabinets']]!=list(c.CABINETS):raise ValueError('baseline not verified')
    oldroot=Path(doc['root_release']);r.trust(oldroot)
    if str(oldroot)!=baseline['recovery_root']:raise ValueError('unexpected recovery release')
    rootmanifest=oldroot/'MANIFEST.json';r.trust(rootmanifest,0o644)
    if r.sha(rootmanifest.read_bytes())!=baseline['recovery_manifest_sha256']:raise ValueError('recovery manifest changed')
    # Installed accepted verifier reads all raw pages and committed generations.
    check=json.loads(r.run(['/usr/bin/python3','-I','-B',str(oldroot/'controller.py'),'--verify'],timeout=3600))
    if check.get('verification')!='PASS' or check.get('verified_days')!=39:raise ValueError('baseline archive verification failed')
    unit=Path('/etc/systemd/system')/c.UNIT;timer=unit.with_name(TIMER);watch=unit.with_name(WATCH)
    archive=r.ARCHIVE/'ozon-daily-accruals'
    for p in (unit,timer,watch,c.BASE,archive,c.PUBLIC,RULE,CLIENT,c.REQUESTS):
        if p.exists() or p.is_symlink():raise ValueError('existing or partial daily installation; reconcile first')
    for name in (c.UNIT,TIMER,WATCH):
        if r.run(['/usr/bin/systemctl','show',name,'-p','LoadState']).strip()!=b'LoadState=not-found':raise ValueError('existing unit')
    for parent in (unit.parent,c.BASE.parent,c.PUBLIC.parent,RULE.parent,CLIENT.parent):r.trust(parent)
    r.trust(c.REQUESTS.parent,uid=1001)
    r.trust(r.ARCHIVE,0o711,995)
    r.trust(c.SEED,0o644)
    if r.sha(c.SEED.read_bytes())!=c.TYPE_SHA:raise ValueError('type seed changed')
    notice_check=json.loads(r.run(['/usr/sbin/runuser','-u','hermes','--','/usr/bin/python3','-I','-B',str(c.ROOT/'notify.py'),'--check']))
    if notice_check!={'credentials_available':True,'chat_id':-1002485321031,'thread_id':758}:raise ValueError('notice prerequisites unavailable')
    r.trust(Path('/var/lib/msp-finance-control/controller.lock'),0o600)
    with Path('/var/lib/msp-finance-control/controller.lock').open('rb') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        state=c.state()
        if state['ActiveState'] not in ('inactive','failed') or state['PrivateNetwork']!='yes' or state['DropInPaths']:raise ValueError('executor not idle/isolated')
        for name in ('msp-ozon-current-accruals-2026.service','msp-ozon-current-recovery-20261113.service'):
            if r.run(['/usr/bin/systemctl','show',name,'-p','ActiveState']).strip() not in (b'ActiveState=inactive',b'ActiveState=failed'):raise ValueError('old controller alive')
        backups={}
        for cabinet,pin in baseline['pointers'].items():
            path=r.ARCHIVE/'.b7-generations'/'ozon_current_accruals'/cabinet/'2026-11'/'CURRENT.json'
            r.trust(path,0o644,995);raw=path.read_bytes()
            if r.sha(raw)!=pin:raise ValueError('baseline publication changed')
            backups[cabinet]=raw
        # Every prerequisite above is read-only. Refuse drift before first write.
        os.mkdir(c.BASE,0o755);os.chmod(c.BASE,0o755);r.syncdir(c.BASE.parent)
        r.save(c.BASE/'installation.json',r.doc({'status':'INSTALLING','root_release':str(c.ROOT)}),0o644)
        os.mkdir(archive,0o755);os.chmod(archive,0o755);r.syncdir(archive.parent)
        for cabinet,raw in backups.items():r.save(c.BASE/(cabinet+'-baseline-CURRENT.json'),raw,0o600)
        now=datetime.datetime.now(ZoneInfo('Europe/Moscow'))
        first=datetime.datetime.combine(now.date()+datetime.timedelta(days=1),datetime.time(8,40),tzinfo=ZoneInfo('Europe/Moscow'))
        os.mkdir(c.BASE/'cycles',0o755);os.chmod(c.BASE/'cycles',0o755);r.syncdir(c.BASE)
        r.save(c.BASE/'catalog.json',r.doc({}),0o600)
        os.mkdir(c.REQUESTS,0o700);os.chown(c.REQUESTS,1001,1001);os.chmod(c.REQUESTS,0o700);r.syncdir(c.REQUESTS.parent)
        os.mkdir(c.REQUESTS/'processed',0o700);os.chown(c.REQUESTS/'processed',1001,1001);os.chmod(c.REQUESTS/'processed',0o700);r.syncdir(c.REQUESTS)
        r.save(CLIENT,(c.ROOT/'manual.py').read_bytes(),0o644)
        rule=('polkit.addRule(function(action, subject) { if (subject.user === "hermes" && action.id === "org.freedesktop.systemd1.manage-units" && action.lookup("unit") === "msp-ozon-daily.service" && action.lookup("verb") === "start") return polkit.Result.YES; });\n').encode()
        r.save(RULE,rule,0o644)
        r.save(c.BASE/'schedule.json',r.doc({'timezone':'Europe/Moscow','time':'08:40','not_before_epoch':first.timestamp(),'first_business_date':'2026-11-13','policy':'yesterday-only; three availability checks 20min apart; missing wait-next-day; confirmed-ready cabinets skipped; no blind unknown retry','root_release':str(c.ROOT)}),0o644)
        r.save(unit,service_text(),0o644);r.save(timer,timer_text(),0o644);r.save(watch,path_text(),0o644)
        r.save(c.BASE/'installed-wiring.json',r.doc({'unit_sha256':r.sha(unit.read_bytes()),'timer_sha256':r.sha(timer.read_bytes()),'path_sha256':r.sha(watch.read_bytes()),'manual_client_sha256':r.sha(CLIENT.read_bytes()),'manual_rule_sha256':r.sha(RULE.read_bytes())}),0o644)
        r.run(['/usr/bin/systemctl','daemon-reload'])
        r.run(['/usr/bin/systemctl','enable','--now',TIMER])
        r.run(['/usr/bin/systemctl','enable','--now',WATCH])
        installed={'status':'SCHEDULED_NOT_YET_RUN','time_moscow':'08:40','first_scheduled_at':first.isoformat(),'first_business_date':'2026-11-13','root_release':str(c.ROOT),'background_model_calls':0}
        c.replace(c.BASE/'installation.json',installed)
        c.replace(c.PUBLIC,installed)
        print(json.dumps(installed));print(r.run(['/usr/bin/systemctl','show',TIMER,'-p','ActiveState','-p','UnitFileState','-p','NextElapseUSecRealtime']).decode().strip())

if __name__=='__main__':main()
