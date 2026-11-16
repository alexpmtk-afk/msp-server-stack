"""Notifier-only protected upgrade; never touches source workers or financial data."""
import fcntl,hashlib,json,os,stat,subprocess,sys,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parent
BASE=Path('/var/lib/msp-finance-notices')
JOURNAL=Path('/var/lib/msp-daily-notices-v2-20261116')
UNIT=Path('/etc/systemd/system/msp-finance-notices.service')
POLICY='DAILY_READABLE_FOLLOWUPS_V2_20261116'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def trust(path,mode=None):
 s=path.lstat()
 if s.st_uid!=0 or s.st_mode&0o022 or stat.S_ISLNK(s.st_mode) or not (stat.S_ISREG(s.st_mode) or stat.S_ISDIR(s.st_mode)) or (stat.S_ISREG(s.st_mode) and s.st_nlink!=1):raise ValueError('untrusted inode: '+path.name)
 if mode is not None and stat.S_IMODE(s.st_mode)!=mode:raise ValueError('inode mode: '+path.name)
def sync(path):
 f=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try:os.fsync(f)
 finally:os.close(f)
def write(path,raw,mode=0o644):
 if not isinstance(raw,bytes):raw=(json.dumps(raw,sort_keys=True,ensure_ascii=False)+'\n').encode()
 temp=path.with_name('.'+path.name+'.'+uuid.uuid4().hex)
 fd=os.open(temp,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,mode)
 try:
  with os.fdopen(fd,'wb',closefd=False) as f:f.write(raw);f.flush()
  os.fchmod(fd,mode);os.fsync(fd)
 finally:os.close(fd)
 os.replace(temp,path);sync(path.parent)
def run(args):
 p=subprocess.run(args,capture_output=True,timeout=45)
 if p.returncode:raise RuntimeError('system operation failed: '+Path(args[0]).name)
 return p.stdout

def state():return dict(x.split('=',1) for x in run(['/usr/bin/systemctl','show','msp-finance-notices.service','-p','ActiveState','-p','MainPID','-p','ExecStart','-p','DropInPaths']).decode().splitlines() if '=' in x)
def verify():
 for p in (ROOT,*ROOT.parents):trust(p)
 trust(ROOT/'MANIFEST.json',0o644)
 for n,h in json.loads((ROOT/'MANIFEST.json').read_bytes()).items():
  if Path(n).is_absolute() or '..' in Path(n).parts:raise ValueError('manifest path')
  p=ROOT/n;trust(p,0o644)
  if sha(p.read_bytes())!=h:raise ValueError('payload hash')
def pins(cfg):
 for n,h in cfg['files'].items():
  p=Path(n);trust(p,0o644)
  if sha(p.read_bytes())!=h:raise ValueError('installed drift: '+p.name)
def main():
 if os.geteuid()!=0:raise PermissionError('Linux root console required')
 verify();cfg=json.loads((ROOT/'baseline.json').read_text())
 if JOURNAL.exists():
  p=JOURNAL/'installation.json';trust(p,0o644);old=json.loads(p.read_text());active=Path(old['root_release'])
  if old.get('policy')!=POLICY or old.get('status')!='INSTALLED' or sha((active/'MANIFEST.json').read_bytes())!=sha((ROOT/'MANIFEST.json').read_bytes()) or str(active/'notices/controller.py') not in state()['ExecStart']:raise ValueError('partial/unknown upgrade; reconcile without replay')
  print(json.dumps(dict(status='ALREADY_INSTALLED_NO_REPLAY',root_release=str(active))));return
 pins(cfg);s=state()
 if s['ActiveState']!='active' or s['DropInPaths'] or str(Path(cfg['old_root'])/'notices/controller.py') not in s['ExecStart']:raise ValueError('unexpected notifier state')
 targets=[UNIT,BASE/'config.json',BASE/'installation.json'];oldunit=UNIT.read_bytes();newunit=oldunit
 for n in ('controller.py','sender.py'):
  old=str(Path(cfg['old_root'])/'notices'/n).encode()
  if newunit.count(old)!=1:raise ValueError('unit executable layout')
  newunit=newunit.replace(old,str(ROOT/'notices'/n).encode())
 # Exact private backups before the only service lifecycle operation.
 os.mkdir(JOURNAL,0o755);os.chmod(JOURNAL,0o755);sync(JOURNAL.parent)
 os.mkdir(JOURNAL/'backup',0o700);sync(JOURNAL)
 for i,p in enumerate(targets):
  raw=p.read_bytes();backup=JOURNAL/'backup'/('%02d.backup'%i);write(backup,raw,0o600)
  if backup.read_bytes()!=raw:raise ValueError('backup verification')
 write(JOURNAL/'intent.json',dict(policy=POLICY,status='PREPARED_BEFORE_NOTIFIER_STOP',targets=[str(p) for p in targets]),0o600)
 run(['/usr/bin/systemctl','stop','msp-finance-notices.service'])
 if state()['ActiveState']!='inactive':raise ValueError('notifier not stopped')
 trust(BASE/'lock',0o600)
 with (BASE/'lock').open('rb') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);pins(cfg)
  config=json.loads((BASE/'config.json').read_text());config.update(daily_policy=POLICY,followup_from='2026-11-16',notifier_root_release=str(ROOT));write(BASE/'config.json',config)
  meta=json.loads((BASE/'installation.json').read_text());meta.update(daily_policy=POLICY,notifier_root_release=str(ROOT));write(BASE/'installation.json',meta)
  write(UNIT,newunit)
 run(['/usr/bin/systemctl','daemon-reload']);run(['/usr/bin/systemctl','start','msp-finance-notices.service'])
 s=state()
 if s['ActiveState']!='active' or int(s['MainPID'])<=0 or str(ROOT/'notices/controller.py') not in s['ExecStart']:raise ValueError('notifier readiness failed')
 result=dict(status='INSTALLED',policy=POLICY,root_release=str(ROOT),sources_restarted=False,provider_calls=0,weekly_format_changed=False,old_messages_preserved=True,followups_from='2026-11-16',background_model_calls=0)
 write(JOURNAL/'installation.json',result);print(json.dumps(result))
if __name__=='__main__':main()
