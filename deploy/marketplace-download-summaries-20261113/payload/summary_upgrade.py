"""Pinned inactive WB/Ozon upgrade; no new provider calls or test messages."""
import datetime,fcntl,hashlib,json,os,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import root_common as r
ROOT=Path(__file__).resolve().parent
WB=Path('/var/lib/msp-wb-daily-weekly')
OZ=Path('/var/lib/msp-ozon-daily')
BASE=Path('/var/lib/msp-finance-notices')
UNITDIR=Path('/etc/systemd/system')
NEWUNIT='msp-finance-notices.service'
POLICY='MP_DOWNLOAD_SUMMARY_V1_20261113'
FINANCE=Path('/var/lib/msp-finance-control/controller.lock')
def atomic(path,value):
 if path.exists():r.trust(path,0o644)
 tmp=path.with_name('.'+path.name+'.new');r.save(tmp,value if isinstance(value,bytes) else r.doc(value),0o644);os.replace(tmp,path);r.syncdir(path.parent)
def state(unit):
 return dict(x.split('=',1) for x in r.run(['/usr/bin/systemctl','show',unit,'-p','ActiveState','-p','DropInPaths','-p','PrivateNetwork','-p','ExecStart','-p','MainPID']).decode().splitlines() if '=' in x)
def same_files(cfg):
 for name,pin in cfg['files'].items():
  p=Path(name);r.trust(p,0o644)
  if r.sha(p.read_bytes())!=pin:raise ValueError('installed wiring drift')
def verify_old(path,pin):
 r.trust(path);r.trust(path/'MANIFEST.json',0o644);raw=(path/'MANIFEST.json').read_bytes()
 if r.sha(raw)!=pin:raise ValueError('old manifest mismatch')
 for name,h in json.loads(raw).items():
  p=path/name;r.trust(p,0o644)
  if r.sha(p.read_bytes())!=h:raise ValueError('old payload drift')
def mkdir(path,mode=0o755):
 os.mkdir(path,mode);os.chmod(path,mode);r.syncdir(path.parent)
def unit_bytes():
 return ('''[Unit]
Description=Verified WB/Ozon daily and Monday-weekly completion notices
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=0
[Service]
Type=exec
User=root
UMask=0077
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/var/lib/msp-finance-notices
Restart=on-failure
RestartSec=30
TimeoutStartSec=45
TimeoutStopSec=10
ExecStartPre=/usr/sbin/runuser -u hermes -- /usr/bin/python3 -I -B '''+str(ROOT/'notices/sender.py')+''' --check
ExecStart=/usr/bin/python3 -I -B '''+str(ROOT/'notices/controller.py')+''' --serve
StandardOutput=null
StandardError=journal
[Install]
WantedBy=multi-user.target
''').encode()
def main():
 if os.geteuid()!=0:raise PermissionError('Linux root console required')
 r.verify_payload();r.validate_platform();cfg=json.loads((ROOT/'summary-upgrade-baseline.json').read_bytes())
 receipt=BASE/'installation.json'
 if BASE.exists():
  r.trust(BASE,0o755)
  if not receipt.exists():raise ValueError('partial installation, reconcile before replay')
  old=json.loads(receipt.read_bytes());active=Path(old['root_release'])
  if old.get('status')!='INSTALLED' or old.get('policy')!=POLICY or r.sha((active/'MANIFEST.json').read_bytes())!=r.sha((ROOT/'MANIFEST.json').read_bytes()):raise ValueError('unknown existing installation')
  if str(active/'notices/controller.py') not in state(NEWUNIT)['ExecStart']:raise ValueError('notice wiring drift')
  for base,unit,target in ((WB,'msp-wb-daily-weekly.service',active),(OZ,'msp-ozon-daily.service',active/'ozon')):
   if str(target/'controller.py') not in state(unit)['ExecStart'] or json.loads((base/'schedule.json').read_bytes()).get('consolidated_notices') is not True:raise ValueError('active source wiring drift')
  print(json.dumps(dict(status='ALREADY_INSTALLED',root_release=str(active))));return
 oldwb=Path(cfg['old_wb_root']);oldoz=Path(cfg['old_ozon_root']);verify_old(oldwb,cfg['old_wb_manifest']);verify_old(oldoz,cfg['old_ozon_manifest']);same_files(cfg)
 for name in ('msp-wb-daily-weekly.service','msp-ozon-daily.service'):
  if state(name)['ActiveState'] not in ('inactive','failed'):raise ValueError('coordinator active; no automatic stop or replay')
 sender=state(r.SERVICE)
 if sender['ActiveState'] not in ('inactive','failed') or sender['PrivateNetwork']!='yes' or sender['DropInPaths']:raise ValueError('shared sender not isolated')
 if (UNITDIR/NEWUNIT).exists():raise ValueError('unknown notice unit')
 if any((old/'cabinets.json').exists() for old in (oldwb,oldoz)):raise ValueError('unreconciled credential artifact; no automatic cleanup')
 for base in (WB,OZ):
  if any(p.name in ('activation.json','activation-intent.json') for p in (base/'runs').rglob('*.json')):raise ValueError('unreconciled source activation; preserve original controls')
 for path in (WB/'controller.lock',OZ/'controller.lock',FINANCE):r.trust(path,0o600)
 with (WB/'controller.lock').open('rb') as wb,(OZ/'controller.lock').open('rb') as oz,FINANCE.open('rb') as slot:
  for f in (wb,oz,slot):fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
  same_files(cfg);mkdir(BASE);mkdir(BASE/'outbox');mkdir(BASE/'deliveries');mkdir(BASE/'backup',0o700);r.save(BASE/'lock',b'',0o600)
  # Exact original wiring and metadata retained before any replacement.
  targets=[UNITDIR/'msp-wb-daily-weekly.service',UNITDIR/'msp-ozon-daily.service',WB/'schedule.json',OZ/'schedule.json',WB/'installation.json',OZ/'installation.json']
  for n,path in enumerate(targets):r.save(BASE/'backup'/('%02d.backup'%n),path.read_bytes(),0o600)
  r.save(BASE/'backup/targets.json',r.doc(cfg),0o600)
  atomic(BASE/'config.json',dict(policy=POLICY,first_run_date='2026-11-14',root_release=str(ROOT),poll_seconds=60,summary_destination_chat=-1002485321031,summary_destination_topic=758))
  for base,old,new,unit in ((WB,oldwb,ROOT,'msp-wb-daily-weekly.service'),(OZ,oldoz,ROOT/'ozon','msp-ozon-daily.service')):
   path=UNITDIR/unit;raw=path.read_bytes();needle=str(old/'controller.py').encode()
   if raw.count(needle)!=1:raise ValueError('unexpected controller target')
   atomic(path,raw.replace(needle,str(new/'controller.py').encode()))
   for path in (base/'schedule.json',base/'installation.json'):
    doc=json.loads(path.read_bytes());doc.update(root_release=str(new),consolidated_notices=False,download_summary_policy=POLICY)
    if base==WB:doc.update(weekly_after_daily=True,daily_cleanup='verified weekly coverage; audit retained')
    atomic(path,doc)
  atomic(UNITDIR/NEWUNIT,unit_bytes())
  # Files are removed only by the existing archive writer, never by root.
  clean=json.loads(r.run(['/usr/sbin/runuser','-u','msp-reports','--','/usr/bin/python3','-I','-B',str(ROOT/'cleanup_cli.py')],timeout=600))
  if clean.get('status')!='VERIFIED':raise ValueError('initial cleanup not acknowledged')
  atomic(BASE/'initial-cleanup.json',clean)
  r.run(['/usr/bin/systemctl','daemon-reload'])
  if str(ROOT/'controller.py') not in state('msp-wb-daily-weekly.service')['ExecStart'] or str(ROOT/'ozon/controller.py') not in state('msp-ozon-daily.service')['ExecStart']:raise ValueError('controller target readback')
  # No current/historical notice is sent: first automatic day is14November.
  r.run(['/usr/bin/python3','-I','-B',str(ROOT/'notices/controller.py')],timeout=45)
  r.run(['/usr/bin/systemctl','enable','--now',NEWUNIT],timeout=55)
  live=state(NEWUNIT)
  if live['ActiveState']!='active' or int(live['MainPID'])<=0:raise ValueError('notifier not running')
  # Disable old per-cabinet notices only after notifier readiness succeeded.
  for base in (WB,OZ):
   for path in (base/'schedule.json',base/'installation.json'):
    doc=json.loads(path.read_bytes());doc['consolidated_notices']=True;atomic(path,doc)
 for name in ('msp-wb-daily-weekly.timer','msp-ozon-daily.timer'):
  check=dict(x.split('=',1) for x in r.run(['/usr/bin/systemctl','show',name,'-p','ActiveState','-p','UnitFileState']).decode().splitlines())
  if check!={'ActiveState':'active','UnitFileState':'enabled'}:raise ValueError('source timer state changed')
 observer=dict(kind='service',workload=dict(sources=[dict(path=str(BASE/'queue.sqlite3'),table='items',state_column='state',states={'WAITING_FOR_SOURCE_COMPLETION':'queued','WAITING_FOR_DAILY_DELIVERY':'queued','DELIVERY_UNCERTAIN_NO_REPLAY':'blocked','UNKNOWN':'unknown'})]))
 atomic(BASE/'observer.json',observer)
 env=['/usr/sbin/runuser','-u','hermes','--','/usr/bin/env','--ignore-environment','HOME=/home/hermes','USER=hermes','PATH=/usr/sbin:/usr/bin:/sbin:/bin','XDG_RUNTIME_DIR=/run/user/1001','DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1001/bus']
 r.run(env+['/usr/bin/python3','-I','-B','/home/hermes/workspace/task-visibility/task.py','marketplace-download-notices','running','--title','Итоги загрузки WB/Ozon','--origin-name','Загрузчики отчётов WB/Ozon','--summary','Дневной итог и отдельный недельный итог WB','--stage','Наблюдение квитанций загрузчиков','--status','Служба включена','--unit',NEWUNIT,'--system','--observer',str(BASE/'observer.json')])
 result=dict(status='INSTALLED',root_release=str(ROOT),policy=POLICY,first_run_date='2026-11-14',wb_time='08:45',ozon_time='08:40',daily_checks=3,weekly_checks=10,interval_minutes=20,notifications='daily WB+Ozon; Monday daily then WB weekly',cleanup='verified same-type/currency coverage, compressed audit preserved',source_calls_during_install=0,background_model_calls=0,telegram_test_messages=0)
 atomic(receipt,result);print(json.dumps(result))
if __name__=='__main__':main()
