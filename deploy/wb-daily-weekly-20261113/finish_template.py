"""Finish the already installed WB metadata only; never start/restart senders."""
import datetime,fcntl,hashlib,json,os,stat,subprocess,sys,uuid
from pathlib import Path
EXPECTED = __EXPECTED_BASELINE__

def sha(raw):return hashlib.sha256(raw).hexdigest()
def trust(path,mode=0o644,uid=0):
 s=path.lstat()
 if not stat.S_ISREG(s.st_mode) or s.st_uid!=uid or stat.S_IMODE(s.st_mode)!=mode or s.st_nlink!=1:raise ValueError('unexpected file inode: '+path.name)
 return s

def read_pin(path,pin,uid=0):
 trust(path,uid=uid);raw=path.read_bytes()
 if sha(raw)!=pin:raise ValueError('file drift: '+path.name)
 return raw

def show(unit):
 allowed=('msp-wb-daily-weekly.timer','msp-wb-daily-weekly.service','msp-ozon-daily.timer')
 if unit not in allowed:raise ValueError('unit scope')
 run=subprocess.run(['/usr/bin/systemctl','show',unit,'-p','ActiveState','-p','SubState','-p','UnitFileState','-p','NextElapseUSecRealtime','-p','DropInPaths'],capture_output=True,check=True,timeout=20,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
 return dict(line.split('=',1) for line in run.stdout.decode().splitlines() if '=' in line)

def atomic(path,raw,mode):
 tmp=path.with_name('.'+path.name+'.'+uuid.uuid4().hex+'.finalizing')
 fd=os.open(tmp,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,mode)
 try:
  with os.fdopen(fd,'wb',closefd=False) as f:f.write(raw);f.flush()
  os.fchmod(fd,mode);os.fsync(fd)
 finally:os.close(fd)
 os.replace(tmp,path);d=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try:os.fsync(d)
 finally:os.close(d)

def verify():
 root=Path(EXPECTED['release']);manifest=root/'MANIFEST.json';raw=read_pin(manifest,EXPECTED['manifest_sha256'])
 for name,pin in json.loads(raw).items():
  if Path(name).is_absolute() or '..' in Path(name).parts:raise ValueError('manifest path')
  read_pin(root/name,pin)
 for name,pin in EXPECTED['files'].items():read_pin(Path(name),pin)
 for name,pin in EXPECTED['canonical'].items():read_pin(Path(name),pin,1001)
 link=Path('/etc/systemd/system/timers.target.wants/msp-wb-daily-weekly.timer')
 if link.lstat().st_uid!=0 or not link.is_symlink() or os.readlink(link)!='/etc/systemd/system/msp-wb-daily-weekly.timer':raise ValueError('timer enable link drift')
 wb=show('msp-wb-daily-weekly.timer');oz=show('msp-ozon-daily.timer')
 for state in (wb,oz):
  if state['ActiveState']!='active' or state['UnitFileState']!='enabled' or state['DropInPaths']:raise ValueError('timer not enabled/active or unknown controls')
 controller=show('msp-wb-daily-weekly.service')
 if controller['DropInPaths']:raise ValueError('unexpected controller controls')
 return wb,oz,controller

def main(check=False):
 if not check:
  if os.geteuid()!=0:raise PermissionError('root console required to finalize metadata')
  trust(Path(__file__),mode=0o600)
 wb,oz,controller=verify();path=Path('/var/lib/msp-wb-daily-weekly/installation.json');trust(path)
 current=path.read_bytes();value=json.loads(current)
 if value.get('root_release')!=EXPECTED['release']:raise ValueError('foreign installation')
 if value.get('status')=='INSTALLED':
  return {'status':'ALREADY_FINALIZED','root_release':EXPECTED['release'],'time_moscow':'08:45','provider_restarted':False}
 if value.get('status')!='INSTALLING' or sha(current)!=EXPECTED['installation_sha256']:raise ValueError('installation drift; no replay')
 if check:return {'status':'READY_TO_FINALIZE','wb_timer':wb,'ozon_timer':oz,'controller':controller,'writes':0,'provider_calls':0}
 # Only this installer receipt is changed. Public progress belongs to the live
 # controller and is never overwritten. All source pages/budgets remain intact.
 with path.open('rb') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  if path.read_bytes()!=current:raise ValueError('receipt changed concurrently')
  backup=path.parent/'backups'/'installation-before-finalize.json'
  if backup.exists():read_pin(backup,sha(current))
  else:atomic(backup,current,0o644)
  schedule=json.loads(Path('/var/lib/msp-wb-daily-weekly/schedule.json').read_bytes())
  info={'status':'INSTALLED','root_release':EXPECTED['release'],'time_moscow':'08:45','first_scheduled_at':datetime.datetime.fromtimestamp(schedule['not_before_epoch'],__import__('zoneinfo').ZoneInfo('Europe/Moscow')).isoformat(),'background_model_calls':0,'initial_backfill':'READ_LIVE_PROGRESS_RECEIPT','progress_path':'/var/lib/msp-finance-control/results/wb-daily-weekly.json','source_replayed':False,'service_restarted':False}
  raw=(json.dumps(info,sort_keys=True)+'\n').encode();atomic(path,raw,0o644)
  if read_pin(path,sha(raw))!=raw:raise ValueError('receipt readback failed')
 return dict(info,wb_timer=wb,ozon_timer=oz)

if __name__=='__main__':
 if sys.argv[1:] not in ([],['--check']):raise ValueError('fixed finalizer only')
 print(json.dumps(main(check=sys.argv[1:]==['--check'])))
