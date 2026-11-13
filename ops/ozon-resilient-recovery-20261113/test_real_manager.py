"""Harmless real user-systemd test; no provider, root, Redis or financial writes."""
import sys,tempfile,json,time,subprocess,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'payload'))
from recovery import wait_worker,StartNotificationLost
with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as tmp:
 root=Path(tmp);marker=root/'complete.json';worker=root/'fixture.py';worker.write_text('import time,json,sys;from pathlib import Path;time.sleep(4);Path(sys.argv[1]).write_text(json.dumps({"fixture":"PASS"}))\n')
 identity={};calls=[]
 def start():
  calls.append('start')
  env=dict(os.environ,HERMES_TASK_ROOT=str(root/'visibility'))
  result=subprocess.run(['/usr/bin/python3','-I','-B','/home/hermes/workspace/task-visibility/run.py','recovery-real-fixture','--title','Изолированная проверка восстановления','--maintenance','--','/usr/bin/python3','-I','-B',str(worker),str(marker)],capture_output=True,text=True,env=env)
  if result.returncode:raise ValueError('maintenance admission failed; fixture not run: '+result.stderr[:100])
  identity.update(json.loads(result.stdout))
  raise StartNotificationLost('simulated notification loss after real supervisor accepted')
 def state():
  p=subprocess.run(['systemctl','--user','show',identity['unit'],'-p','ActiveState'],capture_output=True,text=True,check=True)
  return p.stdout.strip().split('=',1)[1]
 observed=[]
 result=wait_worker(start=start,state=state,has_result=marker.exists,pause=lambda x:observed.append(x),deadline=time.time()+25)
 assert result=='receipt' and calls==['start'] and 'PAUSED_CONTROLLER_LINK' in observed and json.loads(marker.read_text())=={'fixture':'PASS'}
 until=time.time()+10
 while state() in ('active','activating') and time.time()<until:time.sleep(.2)
 assert state()=='inactive'
 print(json.dumps(dict(real_user_systemd_fixture='PASS',start_notifications_lost=1,managed_launches=1,worker_survived=True,completion_observed=True,provider_calls=0,root_changes=0)))
