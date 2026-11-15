"""Root-only pinned Ozon calendar repair; source history and attempts retained."""
import fcntl,json,os,stat,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import root_common as r
import calendar_recovery as recovery
ROOT=Path(__file__).resolve().parent
BASE=Path('/var/lib/msp-ozon-calendar-repair-20261115')
OZ=Path('/var/lib/msp-ozon-daily')
NOTICES=Path('/var/lib/msp-finance-notices')
UNIT=Path('/etc/systemd/system/msp-ozon-daily.service')
POLICY='OZON_ROLLING_CALENDAR_V1_20261115'

def atomic(path,value,mode=0o644):
 if path.exists():r.trust(path,mode)
 raw=value if isinstance(value,bytes) else r.doc(value)
 tmp=path.with_name('.'+path.name+'.calendar-new')
 r.save(tmp,raw,mode);os.replace(tmp,path);r.syncdir(path.parent)

def state(unit):
 return dict(x.split('=',1) for x in r.run(['/usr/bin/systemctl','show',unit,'-p','ActiveState','-p','ExecStart','-p','PrivateNetwork','-p','DropInPaths']).decode().splitlines() if '=' in x)

def pins(cfg):
 for name,digest in cfg['files'].items():
  p=Path(name);r.trust(p,0o644)
  if r.sha(p.read_bytes())!=digest:raise ValueError('pinned runtime wiring changed: '+p.name)
 old=Path(cfg['old_root']);r.trust(old/'MANIFEST.json',0o644)
 if r.sha((old/'MANIFEST.json').read_bytes())!=cfg['old_manifest_sha256']:raise ValueError('old manifest changed')
 for n,h in json.loads((old/'MANIFEST.json').read_bytes()).items():
  if Path(n).is_absolute() or '..' in Path(n).parts:raise ValueError('unsafe old manifest')
  p=old/n;r.trust(p,0o644)
  if r.sha(p.read_bytes())!=h:raise ValueError('old immutable source changed')

def prepared_recovery(cfg):
 day=cfg['repair_day'];cid=cfg['repair_cycle_id'];cp=OZ/'cycles'/(cfg['repair_key']+'.json')
 r.trust(cp,0o600);r.trust(OZ/'catalog.json',0o600)
 cycle=json.loads(cp.read_bytes());catalog=json.loads((OZ/'catalog.json').read_bytes())
 sources={};operations=[]
 for cab in recovery.CABINETS:
  src=r.ARCHIVE/'ozon-daily-accruals'/cab/day/cid/'attempt-01';r.trust(src,0o755,995)
  # Refuse a partial response, derived data, unexpected file or link, even if
  # today's public receipt incorrectly calls the failure pre-send.
  for p in src.rglob('*'):r.trust(p,uid=995)
  result=src/'worker-result.json';r.trust(result,0o644,995)
  allowed={result,src/day}
  if set(src.iterdir())-allowed:raise ValueError('unexpected original source artifacts')
  if (src/day).exists() and any((src/day).iterdir()):raise ValueError('original day contains sender artifacts')
  ledger=OZ/'runs'/cid/day/cab/'attempt-01'
  if (ledger/'activation.json').exists() or (ledger/'activation-intent.json').exists():raise ValueError('unreconciled activation')
  r.trust(ledger/'claim.json',0o600);claim=json.loads((ledger/'claim.json').read_bytes())
  job=ledger/(cab+'.job.json');r.trust(job,0o644)
  j=json.loads(job.read_bytes())
  expected=dict(cabinet=cab,period=day[:7],day=day,max_send_entries=10,nonce=claim['nonce'],expires_epoch=0,cycle_id=cid,attempt=1)
  if j!=expected:raise ValueError('retained job/claim conflict')
  sources[cab]=dict(result=json.loads(result.read_bytes()),nonce=claim['nonce'],entries=len(list(src.rglob('*.entry.json'))),responses=len(list(src.rglob('*.response.json'))),derived=len(list(src.glob('*.csv'))))
  target=result.with_name('worker-result.preflight-hold-20261115.json')
  if target.exists():raise ValueError('partial repair already moved source evidence')
  operations.append((result,target,job,cab))
 cy,ca=recovery.rearm(cycle,catalog,sources,day=day,cycle_id=cid,now=time.time())
 # Check the actual fixed worker under its real UID against retained root jobs.
 # --probe does no HTTP, no credential loading, and no publication.
 for result,target,job,cab in operations:
  raw=r.run(['/usr/sbin/runuser','-u','msp-reports','--','/usr/bin/env','MSP_OZON_JOB='+str(job),'/usr/bin/python3','-I','-B',str(ROOT/'ozon'/cab/'capture_worker.py'),'--probe'],timeout=60)
  if json.loads(raw)!={'completed':False,'rows':0}:raise ValueError('original outcome not empty before sender')
 return cp,cy,ca,operations

def main():
 if os.geteuid()!=0:raise PermissionError('Linux root console required')
 r.verify_payload();r.validate_platform();cfg=json.loads((ROOT/'repair-baseline.json').read_bytes())
 if BASE.exists():
  receipt=BASE/'installation.json'
  if not receipt.exists():raise ValueError('partial repair: reconcile retained backup; do not replay')
  r.trust(receipt,0o644);old=json.loads(receipt.read_bytes());active=Path(old['root_release'])
  if old.get('policy')!=POLICY or old.get('status') not in ('INSTALLED_RECOVERY_PENDING_START','INSTALLED_RECOVERY_REQUESTED') or r.sha((active/'MANIFEST.json').read_bytes())!=r.sha((ROOT/'MANIFEST.json').read_bytes()):raise ValueError('unknown existing repair')
  if str(active/'ozon/controller.py') not in state('msp-ozon-daily.service')['ExecStart']:raise ValueError('repaired service wiring drift')
  print(json.dumps(dict(status='ALREADY_INSTALLED_NO_REPLAY',root_release=str(active))));return
 pins(cfg)
 for unit in ('msp-ozon-daily.service','msp-wb-daily-weekly.service'):
  s=state(unit)
  if s['ActiveState'] not in ('inactive','failed') or s['DropInPaths']:raise ValueError('coordinator busy or drift; no automatic stop')
 s=state(r.SERVICE)
 if s['ActiveState'] not in ('inactive','failed') or s['PrivateNetwork']!='yes' or s['DropInPaths']:raise ValueError('source worker busy/not isolated')
 oldoz=Path(cfg['old_root'])/'ozon'
 if str(oldoz/'controller.py') not in state('msp-ozon-daily.service')['ExecStart']:raise ValueError('unexpected current Ozon executable')
 if any((oldoz/c/'cabinets.json').exists() for c in recovery.CABINETS):raise ValueError('unreconciled credential artifact')
 if any(p.name in ('activation.json','activation-intent.json') for p in (OZ/'runs').rglob('*.json')):raise ValueError('unreconciled source control')
 locks=[]
 try:
  for path in (Path('/var/lib/msp-wb-daily-weekly/controller.lock'),OZ/'controller.lock',Path('/var/lib/msp-finance-control/controller.lock')):
   r.trust(path,0o600);h=path.open('rb');locks.append(h);fcntl.flock(h,fcntl.LOCK_EX|fcntl.LOCK_NB)
  pins(cfg);cp,cy,ca,ops=prepared_recovery(cfg)
  raw=UNIT.read_bytes();needle=str(oldoz/'controller.py').encode()
  if raw.count(needle)!=1:raise ValueError('unexpected Ozon unit content')
  os.mkdir(BASE,0o755);os.chmod(BASE,0o755);r.syncdir(BASE.parent)
  os.mkdir(BASE/'backup',0o700);r.syncdir(BASE)
  targets=[UNIT,OZ/'schedule.json',OZ/'installation.json',NOTICES/'installation.json',cp,OZ/'catalog.json']+[a for a,b,c,d in ops]
  # Backup originals byte-for-byte before any live mutation.
  saved=[]
  for n,p in enumerate(targets):
   b=BASE/'backup'/('%02d.backup'%n);rawbackup=p.read_bytes();r.save(b,rawbackup,0o600)
   if b.read_bytes()!=rawbackup:raise ValueError('backup readback mismatch')
   saved.append(dict(path=str(p),sha256=r.sha(rawbackup),backup=str(b),mode=stat.S_IMODE(p.stat().st_mode),uid=p.stat().st_uid))
  r.save(BASE/'backup/manifest.json',r.doc(saved),0o600)
  # Rename, never erase, the proven pre-send failure receipts. Nonce, attempt,
  # root claim, quota, raw evidence, published generations and notices survive.
  for source,target,job,cab in ops:
   if source.stat().st_uid!=995:raise ValueError('source ownership drift')
   os.rename(source,target);r.syncdir(source.parent)
  atomic(OZ/'catalog.json',ca,0o600);atomic(cp,cy,0o600)
  atomic(UNIT,raw.replace(needle,str(ROOT/'ozon/controller.py').encode()))
  for name in ('schedule.json','installation.json'):
   p=OZ/name;value=json.loads(p.read_bytes());value.update(root_release=str(ROOT/'ozon'),calendar_policy=POLICY);atomic(p,value)
  p=NOTICES/'installation.json';value=json.loads(p.read_bytes());value.update(ozon_root_release=str(ROOT/'ozon'),ozon_calendar_policy=POLICY);atomic(p,value)
  r.run(['/usr/bin/systemctl','daemon-reload'])
  if str(ROOT/'ozon/controller.py') not in state('msp-ozon-daily.service')['ExecStart']:raise ValueError('new Ozon wiring readback failed')
  for name in ('msp-wb-daily-weekly.timer','msp-ozon-daily.timer'):
   rawtimer=r.run(['/usr/bin/systemctl','show',name,'-p','ActiveState','-p','UnitFileState']).decode()
   if 'ActiveState=active' not in rawtimer or 'UnitFileState=enabled' not in rawtimer:raise ValueError('timer not ready')
  result=dict(status='INSTALLED_RECOVERY_PENDING_START',policy=POLICY,root_release=str(ROOT),repair_day=cfg['repair_day'],source_calls_during_install=0,recovery='same cycle/attempt/nonce; source failure receipts retained',wb_code_changed=False,notifier_restarted=False,telegram_messages_during_install=0,background_model_calls=0)
  # Publish a durable commit before requesting the existing independent unit.
  atomic(BASE/'installation.json',result)
 finally:
  for h in reversed(locks):h.close()
 # Existing supervisor owns continuation after this installer exits.
 r.run(['/usr/bin/systemctl','reset-failed','msp-ozon-daily.service'])
 r.run(['/usr/bin/systemctl','start','--no-block','msp-ozon-daily.service'])
 result['status']='INSTALLED_RECOVERY_REQUESTED';atomic(BASE/'installation.json',result)
 print(json.dumps(result))

if __name__=='__main__':main()
