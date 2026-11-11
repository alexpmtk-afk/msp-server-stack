import json,os,subprocess,sys,tempfile
from pathlib import Path
base=Path(__file__).parent
sys.path.insert(0,str(base/'payload'))
from run_root import unit_condition_override
stage=Path(tempfile.mkdtemp(prefix='ozon-condition-',dir='/home/hermes/.hermes/cache/scratch'))
unit='msp-ozon-condition-fixture-20261111.service'
folder=Path.home()/'.config/systemd/user'
file=folder/unit;dropdir=folder/(unit+'.d');drop=dropdir/'90-own-approval.conf'
assert not file.exists() and not dropdir.exists()
approval=stage/'approval.json';approval.write_text('{}\n')
marker=stage/'worker-started'
raw='[Unit]\nConditionPathIsDirectory='+str(stage)+'\nConditionPathExists='+str(stage/'missing-wb-approval')+'\n[Service]\nType=oneshot\nRemainAfterExit=yes\nExecStart=/usr/bin/touch '+str(marker)+'\n'
file.write_text(raw)
def ctl(*args):
 return subprocess.run(['systemctl','--user',*args],check=True,capture_output=True,text=True).stdout
try:
 ctl('daemon-reload');ctl('start',unit)
 before=ctl('show',unit,'-p','ConditionResult','-p','ExecMainStartTimestamp')
 assert 'ConditionResult=no' in before and not marker.exists(),before
 dropdir.mkdir();drop.write_text(unit_condition_override(approval,stage))
 ctl('daemon-reload');ctl('start',unit)
 after=ctl('show',unit,'-p','ConditionResult','-p','ExecMainStatus','-p','ExecMainStartTimestamp','-p','FragmentPath','-p','DropInPaths','-p','ConditionTimestamp')
 print(ctl('cat',unit))
 print(after)
 print('approval exists',approval.exists())
 assert 'ConditionResult=yes' in after and 'ExecMainStatus=0' in after and marker.exists(),after
 result={'real_user_systemd_condition_reset':'PASS','before':before,'after':after,'provider_calls':0,'root_executor_touched':False,'fixture':str(stage)}
 (base/'condition-runtime-test.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result))
finally:
 ctl('stop',unit)
 if drop.exists():drop.unlink()
 if dropdir.exists():dropdir.rmdir()
 assert file.read_text()==raw
 file.unlink();ctl('daemon-reload')
