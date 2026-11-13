"""Pinned WB scheduler install and narrowly related shared-slot Ozon upgrade.

No tokens are copied by installer. Source downloads start only in the existing
accepted executor after immutable payload and changed wiring are verified.
"""
import datetime,fcntl,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import controller as c,root_common as r
TIMER='msp-wb-daily-weekly.timer'
READER=Path('/usr/local/libexec/msp-wb-effective-reader.py')
OBASE=Path('/var/lib/msp-ozon-daily')
OUNIT=Path('/etc/systemd/system/msp-ozon-daily.service')
OPUBLIC=Path('/var/lib/msp-finance-control/results/ozon-daily.json')
def service_text():
 return ('[Unit]\nDescription=WB daily and Monday weekly verified financial archive\nAfter=network-online.target msp-quota-redis.service\nWants=network-online.target\nStartLimitIntervalSec=0\n[Service]\nType=exec\nUser=root\nUMask=0077\nNoNewPrivileges=yes\nRestart=on-failure\nRestartPreventExitStatus=2\nRestartSec=30\nTimeoutStopSec=90\nStandardOutput=null\nStandardError=file:'+str(c.BASE/'controller.stderr')+'\nExecStart=/usr/bin/python3 -I -B '+str(c.ROOT/'controller.py')+'\n').encode()
def timer_text():
 return ('[Unit]\nDescription=WB daily at 08:45 Moscow; Monday weekly first\n[Timer]\nOnCalendar=*-*-* 08:45:00 Europe/Moscow\nOnBootSec=5min\nPersistent=false\nAccuracySec=1s\nRandomizedDelaySec=0\nUnit='+c.UNIT+'\n[Install]\nWantedBy=timers.target\n').encode()
def verify_ozon(baseline):
 old=Path(baseline['ozon_root']);r.trust(old)
 for name,key in [('MANIFEST.json','ozon_manifest_sha256'),('controller.py','ozon_controller_sha256')]:
  p=old/name;r.trust(p,0o644)
  if r.sha(p.read_bytes())!=baseline[key]:raise ValueError('Ozon source changed')
 for name,pin in json.loads((old/'MANIFEST.json').read_bytes()).items():
  p=old/name;r.trust(p,0o644)
  if r.sha(p.read_bytes())!=pin:raise ValueError('Ozon immutable payload changed')
 for name,pin in baseline['wiring'].items():
  p=Path(name);r.trust(p,0o644)
  if r.sha(p.read_bytes())!=pin:raise ValueError('Ozon wiring changed; reconcile first')
 if r.run(['/usr/bin/systemctl','show','msp-ozon-daily.service','-p','ActiveState']).strip() not in (b'ActiveState=inactive',b'ActiveState=failed'):raise ValueError('Ozon is active; do not change live wiring')
 if (OBASE/'controller.lock').exists():raise ValueError('Ozon partial slot upgrade')
 if list((OBASE/'cycles').glob('*.json')):raise ValueError('Ozon has cycle evidence; reconcile upgrade before proceeding')
 # The sole changed Ozon behavior is the shared-slot lifetime, not its policy.
 incoming=c.ROOT/'ozon';manifest=json.loads((incoming/'MANIFEST.json').read_bytes())
 original=json.loads((old/'MANIFEST.json').read_bytes())
 if set(manifest)!=set(original) or any(pin!=original[name] for name,pin in manifest.items() if name!='controller.py'):raise ValueError('unscoped Ozon change')
 text=OUNIT.read_bytes()
 target=str(old/'controller.py').encode()
 if text.count(target)!=1:raise ValueError('Ozon exact service target')
 return text.replace(target,str(incoming/'controller.py').encode())
def legacy_files(baseline):
 for key in ('reader','guide'):
  path=Path(baseline[key]);r.trust(path,0o644,1001)
  if r.sha(path.read_bytes())!=baseline[key+'_sha256']:raise ValueError('canonical '+key+' drift')
def preflight():
 if os.geteuid()!=0:raise PermissionError('Linux root console required')
 r.verify_payload();r.validate_platform()
 baseline=json.loads((c.ROOT/'baseline.json').read_bytes());reader=Path(baseline['reader'])
 legacy_files(baseline)
 unit=Path('/etc/systemd/system')/c.UNIT;timer=unit.with_name(TIMER)
 for p in (c.BASE,c.PUBLIC,unit,timer,READER,r.ARCHIVE/'wb-current-catalog',r.ARCHIVE/'wb-scheduled-capture'):
  if p.exists() or p.is_symlink():raise ValueError('existing/partial WB install; reconcile before repeat')
 for name in (c.UNIT,TIMER):
  if r.run(['/usr/bin/systemctl','show',name,'-p','LoadState']).strip()!=b'LoadState=not-found':raise ValueError('unknown existing unit')
 for p in (c.BASE.parent,unit.parent,READER.parent,c.PUBLIC.parent):r.trust(p)
 r.trust(r.ARCHIVE,0o711,995)
 for path,pin in json.loads((c.ROOT/'baseline-coverage.json').read_bytes())['pointers'].items():
  p=Path(path);r.trust(p,0o644,995)
  if r.sha(p.read_bytes())!=pin:raise ValueError('WB baseline changed')
 check=json.loads(r.run(['/usr/sbin/runuser','-u','hermes','--','/usr/bin/python3','-I','-B',str(c.ROOT/'notify.py'),'--check']))
 if check!={'credentials_available':True,'chat_id':-1002485321031,'thread_id':758}:raise ValueError('notification prerequisite')
 ozon_unit=verify_ozon(baseline)
 return baseline,reader,unit,timer,ozon_unit

def main():
 baseline,reader,unit,timer,ozon_unit=preflight()
 r.trust(c.FINANCE_LOCK,0o600)
 with c.FINANCE_LOCK.open('rb') as slot:
  fcntl.flock(slot,fcntl.LOCK_EX|fcntl.LOCK_NB)
  s=c.state()
  if s['ActiveState'] not in ('inactive','failed') or s['PrivateNetwork']!='yes' or s['DropInPaths']:raise ValueError('shared finance executor not idle and isolated')
  # Recheck related controller after acquiring the shared slot; no live stop.
  verify_ozon(baseline)
  c.mkdir(c.BASE);r.save(c.BASE/'installation.json',r.doc(dict(status='INSTALLING',root_release=str(c.ROOT))),0o644)
  c.mkdir(c.BASE/'backups');c.mkdir(c.BASE/'cycles');c.mkdir(c.BASE/'runs')
  for i,(path,pin) in enumerate(baseline['wiring'].items()):r.save(c.BASE/'backups'/('ozon-%02d'%i),Path(path).read_bytes(),0o600)
  r.save(c.BASE/'backups'/'canonical-reader.py',(c.ROOT/'baseline_reader.py').read_bytes(),0o644)
  r.save(c.BASE/'backups'/'canonical-guide.py',(c.ROOT/'baseline_guide.py').read_bytes(),0o644)
  r.save(c.BASE/'backups'/'targets.json',r.doc(baseline),0o600)
  for name in ('wb-current-catalog','wb-scheduled-capture'):c.mkdir(r.ARCHIVE/name,995)
  r.save(c.BASE/'controller.lock',b'',0o600);r.save(c.BASE/'jobs.json',r.doc({}),0o600)
  now=datetime.datetime.now(c.plan.TZ);first=datetime.datetime.combine(now.date()+datetime.timedelta(days=1),datetime.time(8,45),tzinfo=c.plan.TZ)
  schedule={'timezone':'Europe/Moscow','time':'08:45','weekly_day':'Monday','weekly_total_checks':10,'daily_total_checks':3,'interval_seconds':1200,'not_before_epoch':first.timestamp(),'root_release':str(c.ROOT),'initial_backfill':True}
  r.save(c.BASE/'schedule.json',r.doc(schedule),0o644)
  r.save(READER,(c.ROOT/'catalog.py').read_bytes(),0o644)
  # Root-owned atomic file replacements, preserving original backups and data.
  def bytes_replace(path,raw):
   tmp=path.with_name(path.name+'.wb-upgrade.tmp');r.save(tmp,raw,0o644);os.replace(tmp,path);r.syncdir(path.parent)
  # Canonical sources are updated as hermes before this root transaction.
  # Root never replaces files inside the user-owned source checkout.
  legacy_files(baseline)
  r.save(OBASE/'controller.lock',b'',0o600)
  bytes_replace(OUNIT,ozon_unit)
  for path in (OBASE/'schedule.json',OBASE/'installation.json',OPUBLIC):
   value=json.loads(path.read_bytes());value['root_release']=str(c.ROOT/'ozon');c.replace(path,value)
  wiring=json.loads((OBASE/'installed-wiring.json').read_bytes());wiring['unit_sha256']=r.sha(ozon_unit);c.replace(OBASE/'installed-wiring.json',wiring)
  r.save(unit,service_text(),0o644);r.save(timer,timer_text(),0o644)
  # Prove exact installed files before activation; no provider calls here.
  if reader.read_bytes()!=(c.ROOT/'local_reports.py').read_bytes() or READER.read_bytes()!=(c.ROOT/'catalog.py').read_bytes():raise ValueError('reader install mismatch')
  r.run(['/usr/bin/systemctl','daemon-reload']);r.run(['/usr/bin/systemctl','enable','--now',TIMER])
  state=dict(x.split('=',1) for x in r.run(['/usr/bin/systemctl','show',TIMER,'-p','ActiveState','-p','UnitFileState','-p','NextElapseUSecRealtime']).decode().splitlines())
  if state['ActiveState']!='active' or state['UnitFileState']!='enabled' or not state['NextElapseUSecRealtime']:raise ValueError('timer not installed')
  info=dict(status='INSTALLED_INITIAL_BACKFILL_PENDING',root_release=str(c.ROOT),time_moscow='08:45',first_scheduled_at=first.isoformat(),background_model_calls=0)
  c.replace(c.BASE/'installation.json',info);c.replace(c.PUBLIC,info)
 # Release the shared slot BEFORE triggering independently locking controller.
 r.run(['/usr/bin/systemctl','start','--no-block',c.UNIT])
 actual=r.run(['/usr/bin/systemctl','show',c.UNIT,'-p','ActiveState','-p','ExecStart']).decode()
 print(json.dumps(info));print(actual.strip());print(r.run(['/usr/bin/systemctl','show',TIMER,'-p','ActiveState','-p','UnitFileState','-p','NextElapseUSecRealtime']).decode().strip())
if __name__=='__main__':main()
