"""One pinned root-only recovery install; no old task/budget/data reset."""
import os,sys,json,time,uuid,fcntl
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import controller as c
import root_common as r
RULE=c.RULE
OLD_MANIFEST_SHA='e2b1664aa7d288b0bbffdbf8d5bb2fc3cf7089610f24617318e7297d9a8d0f85'
OLD_RESULT=Path('/var/lib/msp-finance-control/results/ozon-current-accruals-2026.json')
OLD_RESULT_SHA='83a459d00e8d33b9b0aa66910add205bdd2c91bfe3da8cd0bbb13c23fdf6f272'

def service_text():
 return ('[Unit]\nDescription=Recoverable bounded Ozon Nov1-13 collection\nAfter=network-online.target msp-quota-redis.service\nWants=network-online.target\nConditionPathExists=!'+str(c.LEDGER/'DONE')+'\nConditionPathExists=!'+str(c.LEDGER/'HOLD')+'\nStartLimitIntervalSec=0\n[Service]\nType=exec\nUser=root\nUMask=0077\nNoNewPrivileges=yes\nRestart=on-failure\nRestartPreventExitStatus=2\nRestartSec=15\nTimeoutStartSec=30\nTimeoutStopSec=90\nStandardOutput=null\nStandardError=file:'+str(c.ROOT/'controller.stderr')+'\nExecStart=/usr/bin/python3 -I -B '+str(c.ROOT/'controller.py')+'\n[Install]\nWantedBy=multi-user.target\n').encode()

def rule_text():
 return ('polkit.addRule(function(action, subject) { if (subject.user === "hermes" && action.id === "org.freedesktop.systemd1.manage-units" && action.lookup("unit") === "'+c.UNIT+'" && action.lookup("verb") === "start") return polkit.Result.YES; });\n').encode()

def preflight():
 if os.geteuid()!=0:raise PermissionError('root console required')
 r.verify_payload();r.validate_platform();r.trust(r.MASTER,0o600);r.trust(r.ARCHIVE,0o711,995)
 unit=Path('/etc/systemd/system')/c.UNIT
 for p in (unit,RULE,c.LEDGER,c.PUBLIC,c.ROOT/'setup-ownership.json'):
  if p.exists() or p.is_symlink():raise ValueError('existing recovery install; reconcile before any action')
 if r.run(['/usr/bin/systemctl','show',c.UNIT,'-p','LoadState']).strip()!=b'LoadState=not-found':raise ValueError('preexisting recovery unit')
 s=c.state()
 if s['ActiveState'] not in ('inactive','failed') or s['PrivateNetwork']!='yes' or s['DropInPaths']:raise ValueError('worker live/foreign activation')
 if (r.run(['/usr/bin/systemctl','show','msp-ozon-current-accruals-2026.service','-p','ActiveState']).strip() not in (b'ActiveState=failed',b'ActiveState=inactive')):raise ValueError('old campaign live')
 r.trust(c.SOURCE_ROOT);r.trust(c.SOURCE_ROOT/'MANIFEST.json',0o644)
 if r.sha((c.SOURCE_ROOT/'MANIFEST.json').read_bytes())!=OLD_MANIFEST_SHA:raise ValueError('old release manifest drift')
 for n,digest in json.loads((c.SOURCE_ROOT/'MANIFEST.json').read_bytes()).items():
  if Path(n).is_absolute() or '..' in Path(n).parts:raise ValueError('old manifest path')
  p=c.SOURCE_ROOT/n;r.trust(p,0o644)
  if r.sha(p.read_bytes())!=digest:raise ValueError('old release drift')
 r.trust(OLD_RESULT,0o644)
 if r.sha(OLD_RESULT.read_bytes())!=OLD_RESULT_SHA:raise ValueError('old interruption changed')
 r.trust(c.SEED,0o644)
 if r.sha(c.SEED.read_bytes())!=c.TYPE_SHA:raise ValueError('type seed drift')
 account=__import__('pwd').getpwnam('msp-reports')
 if (account.pw_uid,account.pw_gid)!=(995,985):raise ValueError('executor identity drift')
 for parent in (unit.parent,RULE.parent,c.LEDGER.parent,c.PUBLIC.parent):r.trust(parent)
 creds=json.loads(r.MASTER.read_bytes());claims={};deadline=time.time()+86400
 for cabinet in c.CABINETS:
  credential=creds.get(cabinet)
  if not isinstance(credential,dict) or any(type(credential.get(k)) is not str or not credential[k].strip() for k in ('client_id','api_key')):raise ValueError('credentials unavailable')
  evidence=c.interrupted_reconcile(cabinet)
  if evidence['entries']>128:raise ValueError('original cumulative budget exhausted')
  oldjob=c.SOURCE_ROOT/cabinet/'job.json'
  if oldjob.exists():
   r.trust(oldjob,0o644);job=json.loads(oldjob.read_bytes())
   if job['cabinet']!=cabinet or job['period']!='2026-11' or job['max_send_entries']!=128:raise ValueError('original claim scope')
   nonce=job['nonce']
  elif cabinet=='ozon_laser_master':nonce=uuid.uuid4().hex
  else:raise ValueError('original claim missing')
  claims[cabinet]=dict(nonce=nonce,deadline=deadline,max_send_entries=128,retained_entries_at_recovery=evidence['entries'])
 # Real accepted cabinet verifier, no HTTP or publication.
 report=json.loads(r.run(['/usr/bin/python3','-I','-B',str(c.SOURCE_ROOT/'ozon_dmitrieva/verify_results.py')],timeout=3600))
 if report.get('verification')!='PASS' or report['verified_days']!=13:raise ValueError('accepted Dmitrieva changed')
 return claims

def main():
 if os.geteuid()!=0:raise PermissionError('root console required')
 r.trust(Path('/var/lib/msp-finance-control/controller.lock'),0o600)
 with Path('/var/lib/msp-finance-control/controller.lock').open('rb') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  claims=preflight()
  os.mkdir(c.LEDGER,0o700);r.syncdir(c.LEDGER.parent)
  r.save(c.LEDGER/'claims.json',r.doc(claims),0o600)
  r.save(c.ROOT/'monitor-window.json',r.doc({'deadline':max(x['deadline'] for x in claims.values())}),0o644)
  for cabinet in c.CABINETS:
   h=c.history(cabinet)
   for path in (h,h/c.PERIOD):
    if not path.exists():os.mkdir(path,0o755);os.chown(path,995,985);os.chmod(path,0o755);r.syncdir(path.parent)
    else:r.trust(path,0o755,995)
   seed=h/'types.seed.json'
   if not seed.exists():r.save(seed,c.SEED.read_bytes(),0o644)
   elif r.sha(seed.read_bytes())!=c.TYPE_SHA:raise ValueError('history type seed drift')
  service=service_text();rule=rule_text()
  r.save(c.ROOT/'setup-ownership.json',r.doc(dict(unit_sha256=r.sha(service),rule_sha256=r.sha(rule))),0o600)
  r.save(Path('/etc/systemd/system')/c.UNIT,service,0o644);r.save(RULE,rule,0o644)
  r.run(['/usr/bin/systemctl','daemon-reload'])
  # Boot resumes only this fixed scope/budget; DONE/HOLD conditions prevent replay.
  r.run(['/usr/bin/systemctl','enable',c.UNIT])
 # Release the controller lock before the actual worker acquires it.
 time.sleep(3)
 env=['/usr/sbin/runuser','-u','hermes','--','/usr/bin/env','--ignore-environment','HOME=/home/hermes','USER=hermes','PATH=/usr/sbin:/usr/bin:/sbin:/bin','XDG_RUNTIME_DIR=/run/user/1001','DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1001/bus']
 verification=json.dumps(['/usr/bin/python3','-I','-B',str(c.ROOT/'controller.py'),'--verify'])
 result=r.run(env+['/usr/bin/python3','-I','-B','/home/hermes/workspace/task-visibility/run.py',c.TASK,'--origin-name','Загрузчик Ozon','--summary','Восстановить ноябрь без повторного скачивания','--stage','Продолжение после обновления сервера','--title','Ozon: восстановление','--cwd','/home/hermes/workspace','--verify-command',verification,'--','/usr/bin/python3','-I','-B',str(c.ROOT/'monitor.py')])
 registration=json.loads(result)
 spec=json.loads((c.ROOT/'observer-template.json').read_bytes())
 spec['unit']={'name':c.UNIT,'scope':'system'};spec['receipt']['path']=str(c.PUBLIC);spec['receipt']['require']={'root_release':str(c.ROOT),'snapshot_through':'2026-11-13'}
 r.save(c.ROOT/'progress-observer.json',r.doc(spec),0o644)
 r.run(env+['/usr/bin/python3','-I','-B','/home/hermes/workspace/task-visibility/task.py',c.TASK,'running','--title','Ozon: восстановление','--status','Продолжение с сохранённого места','--observer',str(c.ROOT/'progress-observer.json')])
 print(result.decode().strip());print('RECOVERY_REGISTERED_NOT_COMPLETE');print('PROGRESS '+str(c.PUBLIC))
if __name__=='__main__':main()
