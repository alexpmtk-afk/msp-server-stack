"""Fixed read-only finance probe and public redacted failure receipts; no HTTP.
No journal access grant, arbitrary paths, commands, exception text or locals.
"""
import fcntl,importlib.util,json,os,re,stat,subprocess,sys,time,uuid
from pathlib import Path
ROOT=Path('__CONTROL_RELEASE__')
STATE=Path('/var/lib/msp-finance-control')
def failure(exc,phase):
 frames=[];tb=exc.__traceback__
 while tb is not None:
  code=tb.tb_frame.f_code
  frames.append({'file':Path(code.co_filename).name,'function':code.co_name,'line':tb.tb_lineno});tb=tb.tb_next
 return {'phase':phase,'error_type':type(exc).__name__,'errno':getattr(exc,'errno',None),'frames':frames[-12:]}
def probe(stages):
 done=[]
 for phase,action in stages:
  try:action();done.append(phase)
  except Exception as exc:return {'status':'HOLD','completed_stages':done,'failure':failure(exc,phase),'provider_calls':0,'retry_permitted':False}
 return {'status':'READ_ONLY_PASS','completed_stages':done,'provider_calls':0,'retry_permitted':False}
def publish(folder,value,uid=0,name='diagnostics-latest.json'):
 if not re.fullmatch(r'[a-zA-Z0-9-]+\.json',name):raise ValueError('fixed public filename')
 folder=Path(folder);info=folder.lstat()
 if not stat.S_ISDIR(info.st_mode) or (uid is not None and info.st_uid!=uid) or info.st_mode&0o022:raise ValueError('untrusted result directory')
 target=folder/name
 if target.exists() or target.is_symlink():
  st=target.lstat()
  if not stat.S_ISREG(st.st_mode) or st.st_nlink!=1 or (uid is not None and st.st_uid!=uid):raise ValueError('unsafe public receipt')
 raw=(json.dumps(value,sort_keys=True)+'\n').encode();tmp=folder/('.diagnostic-'+uuid.uuid4().hex)
 fd=os.open(tmp,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
 try:
  with os.fdopen(fd,'wb',closefd=False) as f:f.write(raw);f.flush();os.fchmod(fd,0o644);os.fsync(fd)
 finally:os.close(fd)
 os.replace(tmp,target);fd=os.open(folder,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
 try:os.fsync(fd)
 finally:os.close(fd)
def save_failure(exc,phase,nonce=None):
 value={'status':'STOP_OR_UNCERTAIN','failure':failure(exc,phase),'auto_retry':False,'request_nonce':nonce,'recorded_epoch':time.time()}
 if nonce and re.fullmatch('[a-f0-9]{32}',nonce):publish(STATE/'results',value,name=nonce+'-failure.json')
 publish(STATE/'results',value,name='controller-latest-failure.json')
 return value

def main():
 if os.geteuid()!=0 or sys.argv[1:]:raise ValueError('fixed diagnostic service only')
 lock=os.open(STATE/'controller.lock',os.O_RDONLY|os.O_NOFOLLOW)
 try:fcntl.flock(lock,fcntl.LOCK_SH|fcntl.LOCK_NB)
 except BlockingIOError:
  publish(STATE/'results',{'status':'BUSY','provider_calls':0,'retry_permitted':False});os.close(lock);return 0
 sys.path.insert(0,str(ROOT));spec=importlib.util.spec_from_file_location('diagnosed_control',ROOT/'control.py');c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
 from apps.msp_marketplace_reports import standalone_wb as s
 context={}
 def read_request():context['request']=c.request(c.checked_json(c.INBOX,1001,4096))
 def ownership():
  if (STATE/'active-run.json').exists():raise ValueError('unreconciled prior execution; do not launch')
 def selection():context['selected']=c.choose('/opt/mcp/data/msp-marketplace-reports',context['request']['cabinet'])
 def reconcile():
  if context.get('selected'):s.reconcile_admission('/opt/mcp/data/msp-marketplace-reports',context['selected'])
 result=probe([('VERIFY_IMMUTABLE_CODE',c.verify_payload),('READ_REQUEST',read_request),('CHECK_PRIOR_OWNERSHIP',ownership),('SELECT_REPORT_READ_ONLY',selection),('VERIFY_BUDGET_HTTP_PAGES',reconcile)])
 result['request_nonce']=context.get('request',{}).get('nonce');result['selected_plan']=context.get('selected');result['checked_epoch']=time.time()
 args=['/usr/bin/systemctl','show','msp-finance-control.service','msp-wb-pilot.service','-p','Id','-p','ActiveState','-p','Result','-p','MainPID','-p','ExecMainStartTimestamp','-p','IPAddressAllow','-p','IPAddressDeny','-p','DropInPaths']
 r=subprocess.run(args,capture_output=True,text=True,timeout=15,env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'});result['unit_state']=r.stdout if r.returncode==0 else 'UNAVAILABLE'
 publish(STATE/'results',result);print(json.dumps(result));return 0
if __name__=='__main__':raise SystemExit(main())
