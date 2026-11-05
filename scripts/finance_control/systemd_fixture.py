"""Ephemeral hosted-CI integration: actual non-root Polkit start + same cleanup.
No production paths, finance credentials, Redis or provider calls. No VM reboot.
"""
import json,os,pwd,shutil,subprocess,sys,tempfile,time
from pathlib import Path

def run(args,check=True):
 p=subprocess.run(args,capture_output=True,timeout=100)
 if check and p.returncode:raise AssertionError('fixture command failed '+Path(args[0]).name+' '+p.stderr.decode(errors='replace')[:400])
 return p

def main():
 if os.geteuid()!=0:raise ValueError('ephemeral CI root fixture only')
 if Path('/proc/1/comm').read_text().strip()!='systemd':raise AssertionError('hosted CI requires actual systemd PID1')
 manager=run(['/usr/bin/systemctl','show','--property=Version']).stdout
 if b'Version=' not in manager:raise AssertionError('actual systemd manager unavailable')
 repo=Path(sys.argv[1]);uid=int(os.environ.get('SUDO_UID','1001'));user=pwd.getpwuid(uid)
 if uid!=1001:raise AssertionError('real unprivileged UID1001 required')
 folder=Path(tempfile.mkdtemp(prefix='msp-control-ci-',dir='/var/lib'));os.chmod(folder,0o755)
 suffix=folder.name[-8:];financial='msp-fin-ci-'+suffix+'.service';admin='msp-adm-ci-'+suffix+'.service'
 unitdir=Path('/etc/systemd/system');ruledir=Path('/etc/polkit-1/rules.d');rule=ruledir/('49-'+suffix+'.rules')
 diagnostic='msp-diagnostic-ci-'+suffix+'.service'
 units=[unitdir/financial,unitdir/admin,unitdir/diagnostic];dropdir=Path('/run/systemd/system')/(financial+'.d')
 try:
  for name,source in [('control.py',repo/'scripts/finance_control/control.py'),('supervisor.py',repo/'scripts/wb_live_pilot/launch.py'),('client.py',repo/'scripts/finance_control/client.py'),('diagnostics.py',repo/'scripts/finance_control/diagnostics.py'),('diagnostics_client.py',repo/'scripts/finance_control/diagnostics_client.py')]:
   p=folder/name;p.write_bytes(source.read_bytes());os.chmod(p,0o644)
  for name in ['inbox','budget']:
   p=folder/name;p.mkdir();os.chown(p,uid,user.pw_gid);os.chmod(p,0o700)
  (folder/'results').mkdir();os.chmod(folder/'results',0o755)
  # Root-owned helper invokes the production bounded-orchestration and cleanup functions.
  helper='''import importlib.util,json,os,subprocess,sys
from pathlib import Path
F=Path(__FOLDER__);FIN=__FIN__
def load(name):
 s=importlib.util.spec_from_file_location(name,F/(name+'.py'));m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
c=load('supervisor');co=load('control');c.SERVICE=FIN;c.APPROVAL=F/'approval.json';c.DROP_DIR=Path('/run/systemd/system')/(FIN+'.d');c.DROP=c.DROP_DIR/'90-test.conf'
def close():
 if (F/'ownership.json').exists():
  ownership=json.loads((F/'ownership.json').read_text());c.cleanup(ownership,stop=True);(F/'ownership.json').unlink()
if sys.argv[1:]==['--close']:close();raise SystemExit(0)
req=json.loads((F/'inbox/request.json').read_text());results=[]
def perform(i,plan):
 c.DROP_DIR.mkdir();raw=b'[Service]\\nPrivateNetwork=no\\n';approval=b'{"fixture":true}\\n'
 ownership={'dropin_sha256':c.sha(raw),'approval_sha256':c.sha(approval)}
 (F/'ownership.json').write_text(json.dumps(ownership));c.write_new(c.DROP,raw,0o644);c.write_new(c.APPROVAL,approval,0o640,gid=__GID__)
 c.run(['/usr/bin/systemctl','daemon-reload']);c.run(['/usr/bin/systemctl','start',FIN])
 if (F/'crash').exists():os._exit(77)
 close();return {'status':'PASS','synthetic_only':True}
results=co.process(req,lambda cabinet:{'fixture':True},perform,lambda *a:None)
c.write_new(F/'results'/(req['nonce']+'.json'),json.dumps({'status':'PASS','jobs':results,'provider_calls':0}).encode(),0o644)
'''.replace('__FOLDER__',repr(str(folder))).replace('__FIN__',repr(financial)).replace('__GID__',str(user.pw_gid))
  (folder/'helper.py').write_text(helper);os.chmod(folder/'helper.py',0o644)
  worker='''import json,os
from pathlib import Path
p=Path(__FOLDER__)/'budget/counter.json';old=json.loads(p.read_text())['entries'] if p.exists() else 0
fd=os.open(p,os.O_CREAT|os.O_WRONLY|os.O_TRUNC,0o600);os.write(fd,json.dumps({'entries':old+1,'uid':os.geteuid(),'provider_calls':0}).encode());os.fsync(fd);os.close(fd)
'''.replace('__FOLDER__',repr(str(folder)))
  (folder/'worker.py').write_text(worker);os.chmod(folder/'worker.py',0o644)
  client='''import importlib.util,sys
from pathlib import Path
f=Path(__FOLDER__);s=importlib.util.spec_from_file_location('client',f/'client.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);m.STATE=f
actual=m.subprocess.run
def dispatch(args,**kw):
 assert args==['/usr/bin/systemctl','--no-ask-password','start','msp-finance-control.service'];return actual(['/usr/bin/systemctl','--no-ask-password','start',__ADMIN__],**kw)
m.subprocess.run=dispatch;m.main()
'''.replace('__FOLDER__',repr(str(folder))).replace('__ADMIN__',repr(admin))
  (folder/'invoke.py').write_text(client);os.chmod(folder/'invoke.py',0o644)
  units[0].write_text('[Service]\nType=oneshot\nUser='+user.pw_name+'\nGroup='+str(user.pw_gid)+'\nExecStart=/usr/bin/python3 -I -B '+str(folder/'worker.py')+'\nPrivateNetwork=yes\nIPAddressDeny=any\nNoNewPrivileges=yes\n')
  units[1].write_text('[Service]\nType=oneshot\nExecStart=/usr/bin/python3 -I -B '+str(folder/'helper.py')+'\nExecStopPost=/usr/bin/python3 -I -B '+str(folder/'helper.py')+' --close\nTimeoutStartSec=60\n')
  rule.write_text('polkit.addRule(function(a,s){if(a.id==="org.freedesktop.systemd1.manage-units" && a.lookup("unit")==='+json.dumps(admin)+' && a.lookup("verb")==="start" && s.user==='+json.dumps(user.pw_name)+') return polkit.Result.YES;});\n');os.chmod(rule,0o644)
  # Actual root diagnostic service emits only redacted location, then actual
  # UID1001 reads it via the production diagnostic client and Polkit path.
  diag_helper="import importlib.util,json\nfrom pathlib import Path\nf=Path("+repr(str(folder))+");s=importlib.util.spec_from_file_location('diagnostics',f/'diagnostics.py');d=importlib.util.module_from_spec(s);s.loader.exec_module(d)\ndef bad():raise ValueError('CI_PRIVATE_VALUE_MUST_NOT_LEAK')\nr=d.probe([('SELECT_REPORT_READ_ONLY',bad)]);d.publish(f/'results',r)\n"
  (folder/'diagnostic_helper.py').write_text(diag_helper);os.chmod(folder/'diagnostic_helper.py',0o644)
  diag_client="import importlib.util\nfrom pathlib import Path\nf=Path("+repr(str(folder))+");s=importlib.util.spec_from_file_location('diag_client',f/'diagnostics_client.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);m.STATE=f\nactual=m.subprocess.run\ndef dispatch(args,**kw):\n assert args==['/usr/bin/systemctl','--no-ask-password','start','msp-finance-diagnostics.service'];return actual(['/usr/bin/systemctl','--no-ask-password','start',"+repr(diagnostic)+"],**kw)\nm.subprocess.run=dispatch;m.main()\n"
  (folder/'diagnose.py').write_text(diag_client);os.chmod(folder/'diagnose.py',0o644)
  units[2].write_text('[Service]\nType=oneshot\nUser=root\nExecStart=/usr/bin/python3 -I -B '+str(folder/'diagnostic_helper.py')+'\nPrivateNetwork=yes\nNoNewPrivileges=yes\nProtectSystem=strict\nReadWritePaths='+str(folder/'results')+'\nUMask=0077\n')
  with rule.open('a') as f:f.write('polkit.addRule(function(a,s){if(a.id==="org.freedesktop.systemd1.manage-units" && a.lookup("unit")==='+json.dumps(diagnostic)+' && a.lookup("verb")==="start" && s.user==='+json.dumps(user.pw_name)+') return polkit.Result.YES;});\n')
  run(['/usr/bin/systemctl','start','polkit.service']);run(['/usr/bin/systemctl','daemon-reload']);time.sleep(1)
  def wake():return run(['/usr/bin/sudo','-n','-u',user.pw_name,'/usr/bin/python3','-I','-B',str(folder/'invoke.py'),'--cabinet','wb_laser_master','--jobs','1'],False)
  for expected in [1,2]:
   p=wake()
   if p.returncode:raise AssertionError('real unprivileged Polkit wake denied '+p.stderr.decode()[:400])
   counter=json.loads((folder/'budget/counter.json').read_text());assert counter['entries']==expected and counter['uid']==uid
   settings=run(['/usr/bin/systemctl','show',financial,'--property=PrivateNetwork,DropInPaths']).stdout.decode();assert 'PrivateNetwork=yes' in settings and not dropdir.exists()
  # Kill-equivalent hard exit skips finally; actual systemd ExecStopPost restores block.
  (folder/'crash').write_text('1');p=wake();assert p.returncode!=0
  counter=json.loads((folder/'budget/counter.json').read_text());assert counter['entries']==3
  settings=run(['/usr/bin/systemctl','show',financial,'--property=PrivateNetwork']).stdout.decode();assert 'PrivateNetwork=yes' in settings and not dropdir.exists()
  (folder/'crash').unlink()
  # Boot-equivalent /run loss with persistent ownership: same recovery path, no calls.
  raw=b'[Service]\nPrivateNetwork=no\n';approval=b'{"fixture":true}\n'
  (folder/'ownership.json').write_text(json.dumps({'dropin_sha256':__import__('hashlib').sha256(raw).hexdigest(),'approval_sha256':__import__('hashlib').sha256(approval).hexdigest()}));(folder/'approval.json').write_bytes(approval)
  dropdir.mkdir();(dropdir/'90-test.conf').write_bytes(raw);shutil.rmtree(dropdir) # reboot removes volatile dropin, not budget
  run(['/usr/bin/python3','-I','-B',str(folder/'helper.py'),'--close']);assert json.loads((folder/'budget/counter.json').read_text())['entries']==3
  p=wake();assert p.returncode==0,p.stderr.decode();assert json.loads((folder/'budget/counter.json').read_text())['entries']==4
  diag=run(['/usr/bin/sudo','-n','-u',user.pw_name,'/usr/bin/python3','-I','-B',str(folder/'diagnose.py')]);diagnostic_result=json.loads(diag.stdout)
  assert diagnostic_result['status']=='HOLD' and diagnostic_result['failure']['phase']=='SELECT_REPORT_READ_ONLY'
  assert 'CI_PRIVATE_VALUE_MUST_NOT_LEAK' not in diag.stdout.decode()
  assert json.loads((folder/'budget/counter.json').read_text())['entries']==4
  print(json.dumps({'actual_nonroot_uid':uid,'polkit_sequential_wakes':2,'entries_after_two':2,'crash_entries_preserved':3,'boot_equivalent_recovery_entries':3,'subsequent_entries':4,'network_block_restored':True,'physical_reboot_tested':False,'diagnostics_nonroot_read':'PASS','diagnostics_no_financial_start':True,'provider_calls':0}))
 finally:
  run(['/usr/bin/systemctl','stop',admin,financial,diagnostic],False)
  for p in units+[rule]:p.unlink(missing_ok=True)
  if dropdir.exists():shutil.rmtree(dropdir)
  run(['/usr/bin/systemctl','daemon-reload'],False);run(['/usr/bin/systemctl','reset-failed',admin,financial,diagnostic],False);shutil.rmtree(folder)
if __name__=='__main__':main()
