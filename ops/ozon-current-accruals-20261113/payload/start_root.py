import os,sys,time,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import chain as h
import root_common as r

def rule_text():
 return ('polkit.addRule(function(action, subject) {\n if (subject.user === "hermes" && action.id === "org.freedesktop.systemd1.manage-units" && action.lookup("unit") === "'+h.UNIT+'" && action.lookup("verb") === "start") return polkit.Result.YES;\n});\n').encode()

def service_text():
 return ('[Unit]\nDescription=Ozon three cabinets Nov1-13 current snapshot 2026\n[Service]\nType=oneshot\nUser=root\nUMask=0077\nRestart=no\nNoNewPrivileges=yes\nTimeoutStartSec=200000\nRuntimeMaxSec=200000\nStandardOutput=null\nStandardError=file:'+str(h.ROOT/'chain.stderr')+'\nExecStart=/usr/bin/python3 -I -B '+str(h.ROOT/'chain.py')+'\nExecStopPost=/usr/bin/python3 -I -B '+str(h.ROOT/'chain.py')+' --cleanup\n').encode()

def main():
 if os.geteuid()!=0:raise PermissionError('root console required')
 r.verify_payload()
 unit=Path('/etc/systemd/system')/h.UNIT
 for p in (unit,h.RULE,h.PUBLIC,h.ROOT/'ownership.json',h.ROOT/'approval.json'):
  if p.exists() or p.is_symlink():raise ValueError('existing attempt; reconcile first')
 if r.run(['/usr/bin/systemctl','show',h.UNIT,'-p','LoadState']).strip()!=b'LoadState=not-found':raise ValueError('unit already exists')
 for cabinet in h.CABINETS:r.run(h.child(cabinet,'year_root.py','--preflight'))
 if r.run(['/usr/bin/systemctl','is-active','polkit.service']).strip()!=b'active':raise ValueError('polkit not active')
 r.trust(unit.parent);r.trust(h.RULE.parent)
 rule=rule_text();service=service_text()
 r.save(h.ROOT/'ownership.json',r.doc(dict(rule_sha256=r.sha(rule),unit_sha256=r.sha(service))),0o600)
 r.save(h.ROOT/'approval.json',r.doc(dict(cabinets=list(h.CABINETS),start_before_epoch=time.time()+1200)),0o644)
 r.save(unit,service,0o644);r.save(h.RULE,rule,0o644);r.run(['/usr/bin/systemctl','daemon-reload'])
 # Do not use pkcheck --detail: nonroot callers are rejected independently of systemd permission.
 # Give polkit's file monitor time to load, then submit the single real start via common supervisor.
 time.sleep(3)
 env=['/usr/sbin/runuser','-u','hermes','--','/usr/bin/env','--ignore-environment','HOME=/home/hermes','USER=hermes','PATH=/usr/sbin:/usr/bin:/sbin:/bin','XDG_RUNTIME_DIR=/run/user/1001','DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1001/bus']
 verify=json.dumps(['/usr/bin/python3','-I','-B',str(h.ROOT/'chain.py'),'--verify'])
 result=r.run(env+['/usr/bin/python3','-I','-B','/home/hermes/workspace/task-visibility/run.py',h.TASK,'--origin-name','Загрузчик Ozon','--summary','Дозагрузить ноябрь по всем трём кабинетам','--stage','Срез 1–13 ноября, текущий день предварительный','--title','Ozon: ноябрь по 13-е, все три кабинета','--cwd','/home/hermes/workspace','--verify-command',verify,'--','/usr/bin/systemctl','--no-ask-password','start','--wait',h.UNIT])
 registration=json.loads(result)
 token=registration['unit'].removeprefix('hermes-task-').removesuffix('.service')
 import re
 if not re.fullmatch('[0-9a-f]{32}',token):raise ValueError('launcher identity')
 spec=json.loads((h.ROOT/'observer-template.json').read_bytes())
 spec['unit']={'name':registration['unit'],'scope':'user'}
 spec['receipt']['path']='/home/hermes/.local/state/hermes-task-visibility/runs/'+token+'.result.json'
 spec['receipt']['require']={'run_id':token}
 r.save(h.ROOT/'progress-observer.json',r.doc(spec),0o644)
 r.run(env+['/usr/bin/python3','-I','-B','/home/hermes/workspace/task-visibility/task.py',h.TASK,'running','--title','Ozon: ноябрь','--status','Скачивание по дням','--observer',str(h.ROOT/'progress-observer.json')])
 print(result.decode().strip());print('REQUEST_REGISTERED_NOT_YET_COMPLETE');print('PROGRESS '+str(h.PUBLIC))

if __name__=='__main__':main()
