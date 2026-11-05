"""Single reviewed administrative installation. No provider call/financial start."""
import base64,hashlib,json,os,stat,subprocess,sys,types,pwd
from pathlib import Path
PACKAGE = {}  # BUILD_PACKAGE
def sha(v):return hashlib.sha256(v).hexdigest()
def write(p,raw,mode=0o600,uid=0,gid=0):
 fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,mode)
 try:os.write(fd,raw);os.fchown(fd,uid,gid);os.fchmod(fd,mode);os.fsync(fd)
 finally:os.close(fd)
 sync(p.parent)
def sync(p):
 fd=os.open(p,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try:os.fsync(fd)
 finally:os.close(fd)
def run(args):
 p=subprocess.run(args,capture_output=True,timeout=60,env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin','LANG':'C.UTF-8'})
 if p.returncode:raise RuntimeError('fixed administrative command failed')
 return p.stdout

def install():
 if os.geteuid()!=0:raise ValueError('root snapshot required')
 user=pwd.getpwnam('hermes')
 if (user.pw_uid,user.pw_gid)!=(1001,1001):raise ValueError('hermes identity drift')
 if not Path('/usr/lib/polkit-1/polkitd').is_file():raise ValueError('existing Polkit backend required')
 release=Path(PACKAGE['release']);state=Path('/var/lib/msp-finance-control');receipt=state/'INSTALL.json'
 for p in [Path(__file__),*Path(__file__).parents]:
  st=p.lstat()
  if stat.S_ISLNK(st.st_mode) or st.st_uid!=0 or st.st_mode&0o022:raise ValueError('installer requires root-owned snapshot')
 files={n:base64.b64decode(v) for n,v in PACKAGE['files'].items()}
 for n,raw in files.items():
  if Path(n).is_absolute() or '..' in Path(n).parts or sha(raw)!=PACKAGE['hashes'][n]:raise ValueError('invalid immutable package')
 if receipt.exists():
  if json.loads(receipt.read_text()).get('payload_sha256')!=PACKAGE['payload_sha256']:raise ValueError('different/partial existing controller')
  for n,d in PACKAGE['hashes'].items():
   if sha((release/n).read_bytes())!=d:raise ValueError('installed code drift')
  expected={Path('/etc/systemd/system')/n:files['units/'+n] for n in ['msp-finance-control.service','msp-finance-recover.service','msp-finance-diagnostics.service']}
  expected[Path('/etc/polkit-1/rules.d/49-msp-finance-control.rules')]=files['units/49-msp-finance-control.rules']
  expected[Path('/etc/polkit-1/rules.d/48-msp-finance-diagnostics.rules')]=files['units/48-msp-finance-diagnostics.rules']
  expected[Path('/usr/local/bin/msp-finance-diagnose')]=('#!/bin/sh\nexec /usr/bin/python3 -I -B '+str(release/'diagnostics_client.py')+' "$@"\n').encode()
  expected[Path('/usr/local/bin/msp-finance-wake')]=('#!/bin/sh\nexec /usr/bin/python3 -I -B '+str(release/'client.py')+' "$@"\n').encode()
  expected[Path('/etc/tmpfiles.d/msp-finance-control.conf')]=b'd /run/msp-finance-control 0700 root root -\n'
  for p,b in expected.items():
   st=p.lstat()
   if stat.S_ISLNK(st.st_mode) or st.st_uid!=0 or st.st_mode&0o022 or p.read_bytes()!=b:raise ValueError('installed administrative wiring drift')
  print('ALREADY_INSTALLED_NO_START');return
 # Reuse exact accepted runtime/unit acceptance without mutating infrastructure.
 c=types.ModuleType('accepted_preflight');c.__file__=__file__
 exec(compile(files['pilot_supervisor.py'],'<accepted preflight>','exec'),c.__dict__)
 c.ASSETS=json.loads(files['assets.json']);c.ASSETS['recovery']=True
 c.PUBLIC=state/'results';c.RESULT_NAME='unused.json';c.preflight()
 unitdir=Path('/etc/systemd/system');rule=Path('/etc/polkit-1/rules.d/49-msp-finance-control.rules');entry=Path('/usr/local/bin/msp-finance-wake')
 targets=[unitdir/'msp-finance-diagnostics.service',Path('/etc/polkit-1/rules.d/48-msp-finance-diagnostics.rules'),Path('/usr/local/bin/msp-finance-diagnose'),unitdir/'msp-finance-control.service',unitdir/'msp-finance-recover.service',rule,entry,release,state,Path('/run/msp-finance-control')]
 for p in targets:
  if p.exists() or p.is_symlink():raise ValueError('existing target/partial install; preserve and inspect')
 # Durable refusal marker before installation mutations; unknown partial never reruns.
 state.mkdir(mode=0o755);os.chmod(state,0o755);write(state/'BEGIN.json',b'{"phase":"BEGIN","api_enabled":false}\n')
 for n,mode in [('runs',0o700),('claims',0o700),('programs',0o755),('results',0o755),('inbox',0o700)]:
  p=state/n;p.mkdir(mode=mode);os.chmod(p,mode)
  if n=='inbox':os.chown(p,1001,1001)
  sync(p)
 release.mkdir(mode=0o755);os.chmod(release,0o755)
 for n,raw in sorted(files.items()):
  p=release/n;p.parent.mkdir(parents=True,exist_ok=True)
  for d in [p.parent,*p.parent.parents]:
   if d==release.parent:break
   os.chmod(d,0o755)
  write(p,raw,0o644)
 for d in sorted((p for p in release.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True):sync(d)
 sync(release);sync(release.parent);sync(state)
 runtime=Path('/run/msp-finance-control');runtime.mkdir(mode=0o700);os.chmod(runtime,0o700)
 # /run is recreated on boot by tmpfiles; no credentials are persisted here by installer.
 tmpfile=Path('/etc/tmpfiles.d/msp-finance-control.conf')
 if tmpfile.exists():raise ValueError('unknown tmpfiles config')
 write(tmpfile,b'd /run/msp-finance-control 0700 root root -\n',0o644)
 for n in ['msp-finance-control.service','msp-finance-recover.service','msp-finance-diagnostics.service']:write(unitdir/n,files['units/'+n],0o644)
 write(rule,files['units/49-msp-finance-control.rules'],0o644)
 write(Path('/etc/polkit-1/rules.d/48-msp-finance-diagnostics.rules'),files['units/48-msp-finance-diagnostics.rules'],0o644)
 write(Path('/usr/local/bin/msp-finance-diagnose'),('#!/bin/sh\nexec /usr/bin/python3 -I -B '+str(release/'diagnostics_client.py')+' "$@"\n').encode(),0o755)
 write(entry,('#!/bin/sh\nexec /usr/bin/python3 -I -B '+str(release/'client.py')+' "$@"\n').encode(),0o755)
 run(['/usr/bin/systemd-analyze','verify','msp-finance-control.service','msp-finance-recover.service'])
 run(['/usr/bin/systemctl','daemon-reload'])
 # Boot closure ONLY; no download unit/timer enabled or started.
 run(['/usr/bin/systemctl','enable','msp-finance-recover.service'])
 write(receipt,json.dumps({'status':'INSTALLED_NOT_EXECUTED','payload_sha256':PACKAGE['payload_sha256'],'release':str(release),'schedule_enabled':False,'api_enabled':False}).encode(),0o644)
 print(json.dumps({'status':'INSTALLED_NOT_EXECUTED','next':'msp-finance-wake --cabinet wb_laser_master --jobs 1','two_portions':'msp-finance-wake --cabinet wb_laser_master --jobs 2','root_required_for_future_wakes':False,'schedule_enabled':False}))
if __name__=='__main__':
 try:install()
 except Exception as e:print(json.dumps({'status':'STOP_OR_UNCERTAIN','error_type':type(e).__name__,'no_auto_retry':True}));raise SystemExit(1)
