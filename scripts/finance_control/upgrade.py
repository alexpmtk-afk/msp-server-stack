"""Pinned PR120 diagnostic upgrade; no A/B/C, secrets, budgets or API changes.
Root-only one-time wiring update. --rollback restores only recorded wiring.
"""
import base64,fcntl,hashlib,json,os,stat,subprocess,sys
from pathlib import Path
PACKAGE = {}  # BUILD_PACKAGE
OLD = {}  # BUILD_OLD
STATE=Path('/var/lib/msp-finance-control')
BACKUP=STATE/'upgrades'/('diagnostics-'+PACKAGE.get('payload_sha256','unbuilt')[:16])
def sha(raw):return hashlib.sha256(raw).hexdigest()
def enc(value):return (json.dumps(value,sort_keys=True)+'\n').encode()
def trusted(p,directory=False):
 p=Path(p)
 for q in [p,*p.parents]:
  st=q.lstat()
  if st.st_uid!=0 or st.st_mode&0o022 or stat.S_ISLNK(st.st_mode):raise ValueError('untrusted root path')
 st=p.lstat()
 if directory and not stat.S_ISDIR(st.st_mode):raise ValueError('directory required')
 if not directory and (not stat.S_ISREG(st.st_mode) or st.st_nlink!=1):raise ValueError('plain file required')
def sync(p):
 fd=os.open(p,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try:os.fsync(fd)
 finally:os.close(fd)
def write(p,raw,mode):
 trusted(p.parent,True);fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
 try:
  with os.fdopen(fd,'wb',closefd=False) as f:f.write(raw);f.flush();os.fchmod(fd,mode);os.fsync(fd)
 finally:os.close(fd)
 sync(p.parent)
def replace(p,raw,mode):
 tmp=p.with_name('.'+p.name+'.diagnostics-upgrade')
 write(tmp,raw,mode);os.replace(tmp,p);sync(p.parent)
def run(args):
 p=subprocess.run(args,capture_output=True,timeout=330 if args==['/usr/bin/systemctl','start','msp-finance-diagnostics.service'] else 70,env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C.UTF-8'})
 if p.returncode:raise RuntimeError('fixed upgrade command failed')
 return p.stdout

def wiring(release,files,diagnostic):
 unit=Path('/etc/systemd/system');out={unit/n:(files['units/'+n],0o644) for n in ('msp-finance-control.service','msp-finance-recover.service')}
 out[Path('/usr/local/bin/msp-finance-wake')]=(('#!/bin/sh\nexec /usr/bin/python3 -I -B '+release+'/client.py "$@"\n').encode(),0o755)
 if diagnostic:
  out[unit/'msp-finance-diagnostics.service']=(files['units/msp-finance-diagnostics.service'],0o644)
  out[Path('/etc/polkit-1/rules.d/48-msp-finance-diagnostics.rules')]=(files['units/48-msp-finance-diagnostics.rules'],0o644)
  out[Path('/usr/local/bin/msp-finance-diagnose')]=(('#!/bin/sh\nexec /usr/bin/python3 -I -B '+release+'/diagnostics_client.py "$@"\n').encode(),0o755)
 return out

LOCK_FD=None
def _main():
 global LOCK_FD
 if os.geteuid()!=0:raise ValueError('root-owned snapshot required')
 trusted(Path(__file__))
 if sys.argv[1:] not in ([],['--rollback']):raise ValueError('fixed upgrade or rollback only')
 trusted(STATE,True)
 # Never stop/start financial execution; refuse any concurrent activation.
 for name in ('msp-finance-control.service','msp-wb-pilot.service'):
  state=run(['/usr/bin/systemctl','show',name,'-p','ActiveState','--value']).decode().strip()
  if state not in ('inactive','failed'):raise ValueError('financial execution active; no upgrade')
 lock=os.open(STATE/'controller.lock',os.O_RDONLY|os.O_NOFOLLOW);LOCK_FD=lock;fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 old=Path(OLD['release']);release=Path(PACKAGE['release']);files={n:base64.b64decode(b) for n,b in PACKAGE['files'].items()}
 for n,b in files.items():
  if Path(n).is_absolute() or '..' in Path(n).parts or sha(b)!=PACKAGE['hashes'][n]:raise ValueError('invalid package')
 oldfiles={}
 for n,h in OLD['hashes'].items():
  p=old/n;trusted(p)
  if sha(p.read_bytes())!=h:raise ValueError('old installed payload drift')
  oldfiles[n]=p.read_bytes()
 before=wiring(str(old),oldfiles,'units/msp-finance-diagnostics.service' in oldfiles);after=wiring(str(release),files,True)
 old_install=STATE/'INSTALL.json';trusted(old_install)
 if sys.argv[1:]==['--rollback']:
  trusted(BACKUP/'snapshot.json');snap=json.loads((BACKUP/'snapshot.json').read_text())
  if set(snap)!={str(p) for p in after}|{str(old_install)}:raise ValueError('unexpected rollback targets')
  for name,entry in snap.items():
   p=Path(name);new=after.get(p)
   if set(entry)!={'raw','mode'} or entry['mode']!=(after[p][1] if p in after else 0o644):raise ValueError('invalid rollback record')
   if p==old_install:new=(enc({**json.loads(base64.b64decode(entry['raw'])),'payload_sha256':PACKAGE['payload_sha256'],'release':str(release),'diagnostics_enabled':True}),0o644)
   if p.exists():
    trusted(p);raw=p.read_bytes()
    if raw not in (base64.b64decode(entry['raw']) if entry['raw'] is not None else b'',new[0] if new else b''):raise ValueError('changed wiring; no rollback')
  for name,entry in snap.items():
   p=Path(name)
   if entry['raw'] is None:
    if p.exists():p.unlink();sync(p.parent)
   else:replace(p,base64.b64decode(entry['raw']),entry['mode'])
  run(['/usr/bin/systemctl','daemon-reload']);print('ROLLED_BACK_WIRING_ONLY_ARCHIVE_PRESERVED');return
 receipt=json.loads(old_install.read_text())
 if receipt.get('payload_sha256')==PACKAGE['payload_sha256']:
  for n,h in PACKAGE['hashes'].items():
   p=release/n;trusted(p)
   if sha(p.read_bytes())!=h:raise ValueError('new payload drift')
  for p,(b,mode) in after.items():
   trusted(p)
   if p.read_bytes()!=b or stat.S_IMODE(p.stat().st_mode)!=mode:raise ValueError('new wiring drift')
  print('ALREADY_UPGRADED_NO_DOWNLOAD');return
 if receipt.get('release')!=str(old) or receipt.get('payload_sha256')!=OLD['payload_sha256']:raise ValueError('different installed control')
 for p,(raw,mode) in before.items():
  trusted(p)
  if p.read_bytes()!=raw or stat.S_IMODE(p.stat().st_mode)!=mode:raise ValueError('old wiring drift')
 for p in set(after)-set(before):
  if p.exists() or p.is_symlink():raise ValueError('unknown diagnostic target')
 if BACKUP.exists() or release.exists():raise ValueError('partial upgrade; preserve evidence and rollback')
 if not BACKUP.parent.exists():BACKUP.parent.mkdir(mode=0o700);os.chmod(BACKUP.parent,0o700);sync(STATE)
 trusted(BACKUP.parent,True);BACKUP.mkdir(mode=0o700);os.chmod(BACKUP,0o700);sync(BACKUP.parent)
 targets={**after,old_install:(b'',0o644)}
 snapshot={str(p):{'raw':base64.b64encode(p.read_bytes()).decode() if p.exists() else None,'mode':stat.S_IMODE(p.stat().st_mode) if p.exists() else mode} for p,(_,mode) in targets.items()}
 write(BACKUP/'snapshot.json',enc(snapshot),0o600)
 release.mkdir(mode=0o755);os.chmod(release,0o755);sync(release.parent)
 for n,b in sorted(files.items()):
  p=release/n;p.parent.mkdir(parents=True,exist_ok=True)
  for d in [p.parent,*p.parent.parents]:
   if d==release.parent:break
   os.chmod(d,0o755)
  write(p,b,0o644)
 for p,(b,mode) in after.items():replace(p,b,mode)
 run(['/usr/bin/systemd-analyze','verify','msp-finance-control.service','msp-finance-recover.service','msp-finance-diagnostics.service'])
 newreceipt={**receipt,'payload_sha256':PACKAGE['payload_sha256'],'release':str(release),'diagnostics_enabled':True}
 replace(old_install,enc(newreceipt),0o644);run(['/usr/bin/systemctl','daemon-reload'])
 # Read-only new service only, never msp-wb-pilot/control/recover.
 run(['/usr/bin/systemctl','start','msp-finance-diagnostics.service'])
 print(json.dumps({'status':'UPGRADED_NO_API','diagnostic_receipt':str(STATE/'results/diagnostics-latest.json'),'hermes_command':'msp-finance-diagnose','schedule_enabled':False}))
def main():
 global LOCK_FD
 try:return _main()
 finally:
  if LOCK_FD is not None:os.close(LOCK_FD);LOCK_FD=None
if __name__=='__main__':
 try:main()
 except Exception as exc:print(json.dumps({'status':'STOP_OR_UNCERTAIN','error_type':type(exc).__name__,'no_download':True,'no_auto_retry':True}));raise SystemExit(1)
