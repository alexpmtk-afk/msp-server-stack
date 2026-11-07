"""Unprivileged sequential backfill admission; NEVER a financial HTTP sender.
Calls only installed msp-finance-wake/diagnose. No credentials, Redis or archive
writes. Continues ONLY verified normal budget pauses; errors/unknowns remain fail-stop.
"""
import fcntl,hashlib,json,math,os,stat,subprocess,time
from pathlib import Path
CABINETS=('wb_laser_master','wb_novokshenov','wb_dmitrieva')
EXPECTED_RELEASE='/opt/mcp/projects/msp-marketplace-reports-releases/control-8dbdf9642b1d5326a363f79f6c8ec21dd3eedeac9315412093d44ed23999306d'
OLD_RELEASE='/opt/mcp/projects/msp-marketplace-reports-releases/control-a1807fd6995695f4e002ec5887d3bee892d9f18f86e4a1f0c92fa6e4a8b328e7'
STATE=Path('/home/hermes/.local/state/msp-finance-history')
ROOT_STATE=Path('/var/lib/msp-finance-control')
MAX_WAKES=512
PORTION_PAUSE_SECONDS=70
ADMISSION_PREFLIGHT=False
ROOT_PREFLIGHT_PINS={
 '/opt/mcp/projects/msp-marketplace-reports-releases/control-56da9d52175d1a3fe083a6710be6633e5ec4bac65223e8c2b6e2914c5dc65666':
 '38e4722a13bcb90257bab340793c5fccbe6b7d297706ec85c133f0afdd86bb1e'}

def failure_location(exc,phase):
 frames=[];tb=exc.__traceback__
 while tb is not None:
  c=tb.tb_frame.f_code;frames.append({'file':Path(c.co_filename).name,'function':c.co_name,'line':tb.tb_lineno});tb=tb.tb_next
 return {'phase':phase,'error_type':type(exc).__name__,'errno':getattr(exc,'errno',None),'frames':frames[-8:]}

def write(path,value):
 raw=(json.dumps(value,sort_keys=True)+'\n').encode();tmp=path.with_suffix('.tmp')
 fd=os.open(tmp,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
 try:
  with os.fdopen(fd,'wb',closefd=False) as f:f.write(raw);f.flush();os.fsync(fd)
 finally:os.close(fd)
 os.replace(tmp,path);fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
def safe_budget_pause(result):
 try:
  if result.get('status')!='PARTIAL' or result.get('api_enabled_after_run') is not False or result.get('schedule_enabled') is not False:return None
  jobs=result['jobs']
  if type(jobs) is not list or len(jobs)!=1 or jobs[0]['status']!='PARTIAL':return None
  out=jobs[0]['outcome'];e=out['executor'];count=e['send_entries'];cap=e['approved_total_entries'];key=e['plan_sha256'];until=e['not_before_epoch']
  if (e['status']!='PAUSED_BUDGET' or type(count) is not int or type(cap) is not int or not 3<=count<cap<=1000
      or type(out['wake_entries']) is not int or out['wake_entries']!=3
      or type(out['http_dispatch_attempts']) is not int or out['http_dispatch_attempts']!=3
      or type(out['http_outcomes_unknown']) is not int or out['http_outcomes_unknown']!=0
      or out['http_response_statuses']!=[200,200,200] or out.get('report_detail_complete') is not False
      or type(key) is not str or len(key)!=64 or any(c not in '0123456789abcdef' for c in key)
      or type(until) not in (int,float) or not math.isfinite(until) or until<0):return None
  return {'plan_sha256':key,'count':count,'not_before':until}
 except (KeyError,TypeError,AttributeError):return None

def recover_pause(path,read_receipt,gate,*,clock=time.time):
 value=json.loads(path.read_text());prior=value.get('last');pause=safe_budget_pause(prior or {})
 if value.get('phase')!='HOLD' or value.get('reason')!='non_pass_no_retry' or pause is None:return False
 # Exact original root receipt + closed-network, read-only page/budget check.
 if read_receipt(prior['request_nonce'])!=prior or gate()!='READY':return False
 value.setdefault('counters',{})[pause['plan_sha256']]=pause['count']
 value.update(phase='COOLDOWN',reason='verified_budget_pause_continuation',resume_not_before=max(clock()+PORTION_PAUSE_SECONDS,pause['not_before']))
 write(path,value);return True

def safe_terminal_stop(result, diagnostic, *, now=None):
 try:
  now=time.time() if now is None else now
  if result.get('status')!='PARTIAL' or result.get('api_enabled_after_run') is not False or result.get('schedule_enabled') is not False:return None
  if len(result['jobs'])!=1 or result['jobs'][0]['status']!='STOP_OR_UNCERTAIN':return None
  if diagnostic.get('status')!='READ_ONLY_PASS' or diagnostic.get('request_nonce')!=result['request_nonce'] or not 0<=now-diagnostic['checked_epoch']<=1800:return None
  recovered=diagnostic['interrupted_recovery'];plan=recovered['plan'];e=recovered['evidence'];r=recovered['receipt']
  if plan.get('cabinet')!='wb_laser_master' or plan.get('year')!=2026 or type(plan.get('report_id')) is not int or plan.get('report_type') not in (1,2):return None
  statuses=e['http_statuses'];attempts=e['http_attempts'];pages=e['pages'];spent=e['budget_entries']
  if (e.get('stage_status')!='STAGED_COMPLETE' or type(pages) is not int or pages<1 or type(attempts) is not int or type(spent) is not int or not pages+1<=spent==attempts<=1000 or type(e.get('unknown_outcomes')) is not int or e.get('unknown_outcomes')!=0 or e.get('pending_response_present') is not False or len(statuses)!=attempts or statuses[-1:]!=[204] or any(x!=200 for x in statuses[:-1])):return None
  if r.get('status')=='STAGED_PUBLICATION_PENDING':
   if diagnostic.get('selected_plan')!=plan:return None
  elif not (r.get('verified') is True and r.get('publication_verified') is True and r.get('page_hashes_verified') is True and r.get('report_id')==plan['report_id'] and r.get('report_type')==plan['report_type'] and r.get('terminal_http_status')==204):return None
  return hashlib.sha256((json.dumps(plan,sort_keys=True,separators=(',',':'))+'\n').encode()).hexdigest()
 except (KeyError,TypeError,AttributeError):return None

def recover_terminal_stop(path, read_diagnostic, read_receipt, closed, *, clock=time.time):
 value=json.loads(path.read_text());prior=value.get('last') or {}
 if value.get('phase')!='HOLD' or value.get('reason')!='non_pass_no_retry':return False
 if len(prior.get('jobs',[]))!=1 or prior['jobs'][0].get('status')!='STOP_OR_UNCERTAIN':return False
 if read_receipt(prior['request_nonce'])!=prior:return False
 closed();diagnostic=read_diagnostic();key=safe_terminal_stop(prior,diagnostic,now=clock())
 if key is None:return False
 counts=value.setdefault('local_publication_recoveries',{})
 if counts.get(key,0)>=2:return False
 counts[key]=counts.get(key,0)+1
 value['terminal_reconciliation_sha256']=hashlib.sha256(json.dumps(diagnostic,sort_keys=True).encode()).hexdigest()
 value.update(phase='COOLDOWN',reason='verified_terminal_local_recovery',resume_not_before=clock()+PORTION_PAUSE_SECONDS)
 write(path,value);return True

def terminal_recovery(path):
 def diagnose():
  p=subprocess.run(['/usr/local/bin/msp-finance-diagnose'],capture_output=True,text=True,timeout=360)
  if p.returncode:raise ValueError('terminal recovery diagnostic failed')
  return root_json(ROOT_STATE/'results/diagnostics-latest.json')
 try:return recover_terminal_stop(path,diagnose,lambda nonce:root_json(ROOT_STATE/'results'/(nonce+'.json')),unit_closed)
 except Exception:return False # Preserve original HOLD, never allocate another request.

def advance(path,gate,wake,observe,*,clock=time.time):
 value=json.loads(path.read_text()) if path.exists() else {'schema':1,'phase':'WAITING_UPDATE','wakes':0,'last':None,'cabinet_index':0}
 if value['phase'] in ('HOLD','COMPLETE'):return value
 if value['phase']=='COOLDOWN' and clock()<value['resume_not_before']:return value
 if value['phase']=='DISPATCHING':
  value.update(phase='HOLD',reason='previous_dispatch_uncertain_no_retry');write(path,value);return value
 phase='preflight'
 try:
  ready=gate()
  if ready!='READY':
   value.update(phase=ready);write(path,value);return value
  if value['wakes']>=MAX_WAKES:raise ValueError('global wake ceiling reached')
  value.update(phase='DISPATCHING',wakes=value['wakes']+1);write(path,value)
  phase='dispatch'
  result=wake();observe(result);value['last']=result
  phase='receipt'
  pause=safe_budget_pause(result)
  if pause is not None:
   counters=value.setdefault('counters',{});previous=counters.get(pause['plan_sha256'])
   if previous is not None and pause['count']!=previous+3:raise ValueError('nonmonotonic cumulative budget')
   counters[pause['plan_sha256']]=pause['count']
   value.update(phase='COOLDOWN',reason='normal_budget_pause',resume_not_before=max(clock()+PORTION_PAUSE_SECONDS,pause['not_before']))
  elif ADMISSION_PREFLIGHT and result.get('jobs')==[] and result.get('status')=='PARTIAL':value.update(phase='CABINET_COMPLETE',reason='root_verified_no_remaining_plan')
  elif result.get('status')=='PASS':value.update(phase='COOLDOWN',reason='portion_complete',resume_not_before=clock()+PORTION_PAUSE_SECONDS)
  else:value.update(phase='HOLD',reason='non_pass_no_retry')
 except Exception as e:value.update(phase='HOLD',reason=type(e).__name__,failure=failure_location(e,phase))
 write(path,value);return value

def root_json(path):
 st=path.lstat()
 if not stat.S_ISREG(st.st_mode) or st.st_uid!=0 or st.st_nlink!=1 or st.st_mode&0o022 or st.st_size>1024*1024:raise ValueError('untrusted public root receipt')
 return json.loads(path.read_text())
def unit_closed():
 p=subprocess.run(['/usr/bin/systemctl','show','msp-wb-pilot.service','-p','ActiveState','-p','MainPID','-p','IPAddressDeny','-p','IPAddressAllow','-p','DropInPaths'],capture_output=True,text=True,timeout=20)
 if p.returncode:raise ValueError('unit inspection failed')
 v=dict(line.split('=',1) for line in p.stdout.splitlines() if '=' in line)
 if v.get('ActiveState') not in ('inactive','failed') or v.get('MainPID')!='0' or v.get('IPAddressAllow') or v.get('DropInPaths') or set(v.get('IPAddressDeny','').split())!={'0.0.0.0/0','::/0'}:raise ValueError('network closure not confirmed')
def control_preflight_verified():
 expected=ROOT_PREFLIGHT_PINS.get(EXPECTED_RELEASE)
 if not expected:raise ValueError('root admission preflight release not reviewed')
 p=Path(EXPECTED_RELEASE)/'control.py';st=p.lstat()
 if not stat.S_ISREG(st.st_mode) or st.st_uid!=0 or st.st_mode&0o022 or st.st_nlink!=1:raise ValueError('root admission preflight not immutable')
 if hashlib.sha256(p.read_bytes()).hexdigest()!=expected:raise ValueError('root admission preflight changed')
 return True

def admission_receipt_gate(cabinet):
 # The exact pinned root controller ALWAYS runs choose()->report_receipt() and
 # reconcile_admission() under its exclusive lock BEFORE provider activation.
 # Do not duplicate that full archive scan in the separate 60-second diagnostic.
 control_preflight_verified()
 prior=json.loads((STATE/'state.json').read_text()).get('last')
 req=json.loads((ROOT_STATE/'inbox/request.json').read_text())
 if not prior or req.get('cabinet')!=cabinet or req.get('nonce')!=prior.get('request_nonce'):raise ValueError('foreign or uncertain prior dispatch')
 receipt=root_json(ROOT_STATE/'results'/(req['nonce']+'.json'))
 if receipt!=prior or receipt.get('api_enabled_after_run') is not False or receipt.get('schedule_enabled') is not False:raise ValueError('prior root receipt changed')
 if receipt.get('jobs')==[] and receipt.get('status')=='PARTIAL':return 'CABINET_COMPLETE'
 if receipt.get('status')!='PASS' and safe_budget_pause(receipt) is None:
  state=json.loads((STATE/'state.json').read_text());diagnostic=root_json(ROOT_STATE/'results/diagnostics-latest.json')
  expected=state.get('terminal_reconciliation_sha256')
  if not expected or hashlib.sha256(json.dumps(diagnostic,sort_keys=True).encode()).hexdigest()!=expected or safe_terminal_stop(receipt,diagnostic) is None:raise ValueError('prior root execution not safely continuable')
 return 'READY'

def gate(cabinet):
 installed=root_json(ROOT_STATE/'INSTALL.json')
 if installed.get('release')==OLD_RELEASE:return 'WAITING_UPDATE'
 if installed.get('release')!=EXPECTED_RELEASE or installed.get('schedule_enabled') is not False:raise ValueError('unexpected release or schedule')
 unit_closed()
 if ADMISSION_PREFLIGHT:return admission_receipt_gate(cabinet)
 p=subprocess.run(['/usr/local/bin/msp-finance-diagnose'],capture_output=True,text=True,timeout=80)
 if p.returncode:raise ValueError('diagnostic execution failed')
 d=root_json(ROOT_STATE/'results/diagnostics-latest.json')
 if d.get('status')!='READ_ONLY_PASS':raise ValueError('diagnostic HOLD or BUSY')
 req=json.loads((ROOT_STATE/'inbox/request.json').read_text())
 if d.get('request_nonce')!=req['nonce']:raise ValueError('diagnostic request changed')
 if req['cabinet']==cabinet and d.get('selected_plan') is None:return 'CABINET_COMPLETE'
 state_path=STATE/'state.json'
 prior=json.loads(state_path.read_text()).get('last',{}) if state_path.exists() else {}
 pause=safe_budget_pause(prior)
 if pause is not None:
  selected=d.get('selected_plan');digest=hashlib.sha256((json.dumps(selected,sort_keys=True,separators=(',',':'))+'\n').encode()).hexdigest()
  if digest!=pause['plan_sha256']:raise ValueError('different report selected during continuation')
 return 'READY'
def wake(cabinet):
 previous=json.loads((ROOT_STATE/'inbox/request.json').read_text())['nonce']
 p=subprocess.run(['/usr/local/bin/msp-finance-wake','--cabinet',cabinet,'--jobs','1'],capture_output=True,text=True,timeout=1800)
 # Preserve raw wrapper-only stdout/stderr locally; no token/HTTP bodies exist
 # in this entrypoint. A nonzero exit is never retried or converted to PASS.
 (STATE/'last-client-output.txt').write_text(p.stdout+'\n'+p.stderr);os.chmod(STATE/'last-client-output.txt',0o600)
 if p.returncode:raise ValueError('wake failed; no retry')
 req=json.loads((ROOT_STATE/'inbox/request.json').read_text())
 if req['nonce']==previous or req['cabinet']!=cabinet or req['max_jobs']!=1:raise ValueError('wrong or unchanged admission request')
 result=root_json(ROOT_STATE/'results'/(req['nonce']+'.json'))
 if result.get('request_nonce')!=req['nonce'] or result.get('api_enabled_after_run') is not False or result.get('schedule_enabled') is not False:raise ValueError('invalid close receipt')
 unit_closed();return result

def main():
 if os.geteuid()!=1001:raise ValueError('hermes only')
 STATE.mkdir(parents=True,mode=0o700,exist_ok=True);os.chmod(STATE,0o700)
 fd=os.open(STATE/'driver.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600);fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
 path=STATE/'state.json'
 while True:
  old=json.loads(path.read_text()) if path.exists() else {'cabinet_index':0}
  if old.get('phase')=='COMPLETE':return 0
  if old.get('phase')=='HOLD':
   if not recover_pause(path,lambda nonce:root_json(ROOT_STATE/'results'/(nonce+'.json')),lambda:gate(CABINETS[old.get('cabinet_index',0)])) and not terminal_recovery(path):return 2
   old=json.loads(path.read_text())
  cab=CABINETS[old.get('cabinet_index',0)]
  state=advance(path,lambda:gate(cab),lambda:wake(cab),lambda r:None)
  print(json.dumps({'phase':state['phase'],'cabinet':cab,'wakes':state['wakes'],'last':state.get('last')}),flush=True)
  if state['phase']=='CABINET_COMPLETE':
   index=state.get('cabinet_index',0)+1
   state.update(cabinet_index=index,phase='COMPLETE' if index==len(CABINETS) else 'READY');write(path,state)
   if state['phase']=='COMPLETE':return 0
  elif state['phase']=='HOLD':
   if terminal_recovery(path):continue
   return 2
  elif state['phase']=='WAITING_UPDATE':time.sleep(15)
  elif state['phase']=='COOLDOWN':time.sleep(min(60,max(1,state['resume_not_before']-time.time())))
  elif state['phase']=='READY':time.sleep(1) # Redis remains authoritative within every portion.
  else:raise ValueError('unexpected driver state')
if __name__=='__main__':raise SystemExit(main())
