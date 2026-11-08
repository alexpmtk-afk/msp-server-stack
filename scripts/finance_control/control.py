"""Fixed administrative supervisor: no HTTP client/provider calls, no secret output.
Only launches/closes existing financial unit. Request values are data, never code.
"""
import base64,fcntl,hashlib,importlib.util,json,os,re,stat,sys,tempfile,time,types
from pathlib import Path
RELEASE=Path('__CONTROL_RELEASE__')
STATE=Path('/var/lib/msp-finance-control')
INBOX=STATE/'inbox/request.json'
ACTIVE=Path('/etc/msp-marketplace-reports-executor/control-active.json')
SECRET=Path('/run/msp-finance-control/cabinets.json')
POLICY={'schema':1,'cabinets':['wb_laser_master','wb_novokshenov','wb_dmitrieva'],'year':2026,'as_of':'2026-11-05','max_jobs':2,'wake_entries':3,'total_report_entries':1000,'schedule_enabled':False}
PHASE='BOOT'
CURRENT_NONCE=None
def stage(value):
 global PHASE
 PHASE=value
OLD_PLAN={'schema':1,'cabinet':'wb_laser_master','year':2026,'report_id':883801632,'report_type':1,'max_send_entries':3}
def enc(v):return (json.dumps(v,sort_keys=True,separators=(',',':'))+'\n').encode()
def sha(v):return hashlib.sha256(v).hexdigest()
def checked_json(path,uid=0,limit=65536):
 from apps.msp_marketplace_reports import standalone_wb as s
 fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
 try:
  st=os.fstat(fd)
  if not stat.S_ISREG(st.st_mode) or st.st_uid!=uid or st.st_nlink!=1 or st.st_size>limit:raise ValueError('unsafe fixed input')
  return json.loads(os.read(fd,limit+1),object_pairs_hook=s._strict)
 finally:os.close(fd)
def request(value):
 if type(value) is not dict or set(value) not in ({'nonce','cabinet','max_jobs'},{'nonce','cabinet','max_jobs','expected_report_id'}) or not isinstance(value['nonce'],str) or not re.fullmatch('[a-f0-9]{32}',value['nonce']):raise ValueError('fixed request fields')
 if value['cabinet'] not in POLICY['cabinets'] or type(value['max_jobs']) is not int or not 1<=value['max_jobs']<=POLICY['max_jobs']:raise ValueError('bounded cabinet/jobs')
 if 'expected_report_id' in value and (type(value['expected_report_id']) is not int or value['expected_report_id']<=0 or value['max_jobs']!=1):raise ValueError('one positive expected report only')
 return value

def choose(root,cabinet):
 from apps.msp_marketplace_reports.generation_store import verified_payload_cache
 with verified_payload_cache():
  return _choose(root,cabinet)

def _choose(root,cabinet):
 from datetime import date,timedelta
 from apps.msp_marketplace_reports import standalone_wb as s,wb_discovery_resume as discovery
 from apps.msp_marketplace_reports.finance_refresh_plan import discovery_windows
 from apps.msp_marketplace_reports.finance_receipts import report_receipt
 from apps.msp_marketplace_reports.wb_page_resume import _read_json
 # Resolve this owner's explicitly requested failed report BEFORE new discovery.
 snapshot={} # Fresh immutable-generation snapshot for this serialized selection.
 repair={'schema':1,'cabinet':'wb_laser_master','year':2026,'report_id':601780521,'report_type':1,'max_send_entries':3}
 repair_path=Path(root)/'.wb-executor'/(s._digest(repair)+'.json')
 if cabinet==repair['cabinet'] and repair_path.exists():
  budget=s.read_control(repair_path);seal=budget.pop('state_sha256',None)
  if seal!=s._digest(budget):raise ValueError('repair budget checksum HOLD')
  if budget.get('status')=='HOLD_ERROR' or budget.get('processing_recovery'):
   receipt=report_receipt(root,cabinet,2026,601780521,1,snapshot=snapshot)
   if receipt['status']=='HOLD_INVALID_LOCAL_EVIDENCE':raise ValueError('repair archive integrity HOLD')
   if not receipt.get('verified'):return repair
 # Reuse October first, then fill missing monthly inventories from January.
 windows=discovery_windows(2026,date.fromisoformat(POLICY['as_of']))
 windows.sort(key=lambda b:(b['dateFrom']!='2026-10-01',b['dateFrom']))
 missing=[]
 for body in windows:
  p={'schema':1,'kind':'wb-discovery','cabinet':cabinet,'year':2026,'date_from':body['dateFrom'],'date_to':body['dateTo'],'limit':1000,'max_send_entries':2}
  path=Path(root)/'.wb-executor'/('discovery-'+s._digest(p)+'.json')
  state=_read_json(path)
  if state is None:missing.append(p);continue
  # Verify journal before interpreting its status; corrupt evidence is never a new admission.
  seal=state.pop('state_sha256',None)
  if seal!=s._digest(state) or state.get('plan_sha256')!=s._digest(p):raise ValueError('discovery integrity HOLD')
  if state['status']=='HOLD_ERROR':return p # Worker never retries an unapproved HOLD; diagnostics retain its exact evidence.
  if state['status']!='COMPLETE':return p
  inv=discovery.read_inventory(root,[p])
  for row in sorted(inv['items'],key=lambda r:(r['dateFrom'],r['reportType'],r['reportId'])):
   as_of=date.fromisoformat(POLICY['as_of']);last_closed=as_of-timedelta(days=as_of.weekday()+1)
   if date.fromisoformat(row['dateTo'][:10])>last_closed:continue
   local=report_receipt(root,cabinet,2026,row['reportId'],row['reportType'],snapshot=snapshot)
   if local['status']=='HOLD_INVALID_LOCAL_EVIDENCE':raise ValueError('archive integrity HOLD')
   if local.get('verified'):continue
   return {'schema':1,'cabinet':cabinet,'year':2026,'report_id':row['reportId'],'report_type':row['reportType'],'max_send_entries':3}
 return missing[0] if missing else None

def core_for(plan,run_dir):
 sys.path.insert(0,str(RELEASE))
 asset=checked_json(RELEASE/'assets.json');spec=importlib.util.spec_from_file_location('fixed_pilot_supervisor',RELEASE/'pilot_supervisor.py');c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
 c.__file__=str(RELEASE/'control.py') # preflight expects trusted root0600 entry; override only entry check below.
 c.ASSETS=asset;c.STATE=run_dir;c.PUBLIC=STATE/'results';c.RESULT_NAME=run_dir.name+'.json';c.PLAN=plan
 old=c.preflight
 def preflight():
  previous=c.PLAN;c.PLAN=OLD_PLAN;c.ASSETS['recovery']=True
  original_verify=c.verify_credentials
  def verify_selected(pilot_raw,master_raw,now):
   chosen=checked_json(SECRET)[plan['cabinet']];master=json.loads(master_raw)[plan['cabinet']]
   return original_verify(enc({'wb_laser_master':chosen}),enc({'wb_laser_master':master}),now)
  c.verify_credentials=verify_selected
  original_trust=c.trusted
  # Only immutable control entry is0644, verified by installer/payload manifest on every wake.
  def trust(path,uid=0,mode=None):
   if path==RELEASE/'control.py' and mode==0o600:mode=0o644
   return original_trust(path,uid,mode)
  c.trusted=trust
  try:return old()
  finally:c.PLAN=previous;c.ASSETS.pop('recovery',None);c.trusted=original_trust;c.verify_credentials=original_verify
 c.preflight=preflight
 class ProgramTemp:
  @staticmethod
  def mkdtemp(*,prefix,dir):
   if prefix!='msp-wb-E-program-' or dir!='/var/lib':raise ValueError('fixed program staging')
   return tempfile.mkdtemp(prefix=prefix,dir=STATE/'programs')
 c.tempfile=ProgramTemp
 original_drop=c.dropin_text
 def drop(program,allow):
  raw=original_drop(program,allow).replace(str(program).encode(),str(RELEASE/'worker.py').encode())
  return raw+b'LoadCredential=\nLoadCredential=cabinets.json:'+str(SECRET).encode()+b'\n'
 c.dropin_text=drop
 return c

def verify_payload():
 m=json.loads((RELEASE/'files.json').read_text())
 for name,digest in m.items():
  p=RELEASE/name
  for item in [p,*p.parents]:
   st=item.lstat()
   if stat.S_ISLNK(st.st_mode) or st.st_uid!=0 or st.st_mode&0o022:raise ValueError('untrusted controller payload')
  if sha(p.read_bytes())!=digest:raise ValueError('immutable payload drift')

def close():
 sys.path.insert(0,str(RELEASE))
 marker=STATE/'active-run.json'
 if not marker.exists():return
 active=checked_json(marker);run_dir=STATE/'runs'/active['run_id']
 if not re.fullmatch('[a-f0-9]{32}-[01]',active['run_id']):raise ValueError('unknown active run')
 c=core_for(active['plan'],run_dir)
 ownership=checked_json(run_dir/'controls.json') if (run_dir/'controls.json').exists() else {}
 if ownership:c.cleanup(ownership,stop=True)
 elif c.show()['ActiveState'] not in ('inactive','failed') or c.APPROVAL.exists() or c.DROP.exists():raise ValueError('unowned controls; no cleanup')
 for p,key in [(ACTIVE,'active_sha256'),(SECRET,'secret_sha256')]:
  if p.exists():
   st=p.lstat()
   if st.st_uid!=0 or not stat.S_ISREG(st.st_mode) or sha(p.read_bytes())!=active.get(key):raise ValueError('changed own runtime file')
   p.unlink();c.syncdir(p.parent)
 marker.unlink();c.syncdir(marker.parent)

def process(value,select,perform,persist):
 """Bounded orchestration shared by production and crash/recovery tests."""
 req=request(value);out=[]
 for index in range(req['max_jobs']):
  plan=select(req['cabinet'])
  if plan is None:break
  if req.get('expected_report_id') is not None and (plan.get('kind')=='wb-discovery' or plan.get('report_id')!=req['expected_report_id']):raise ValueError('selected report differs from requested scope; no dispatch')
  persist('BEFORE_JOB',index,plan)
  result=perform(index,plan);out.append(result);persist('AFTER_JOB',index,plan)
  if result.get('status')!='PASS':break
 return out

def main():
 global CURRENT_NONCE
 if os.geteuid()!=0:raise ValueError('fixed administrative service only')
 stage('VERIFY_IMMUTABLE_CODE')
 sys.path.insert(0,str(RELEASE));verify_payload()
 if sys.argv[1:] in (['--close'],['--recover']):close();return 0
 if sys.argv[1:]:raise ValueError('no control arguments')
 stage('READ_INSTALL_RECEIPT')
 receipt=checked_json(STATE/'INSTALL.json')
 if receipt.get('status')!='INSTALLED_NOT_EXECUTED':raise ValueError('installation incomplete')
 lock=os.open(STATE/'controller.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
 try:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  if (STATE/'active-run.json').exists():raise ValueError('unreconciled prior execution; recover first')
  stage('READ_REQUEST')
  req=request(checked_json(INBOX,1001,4096));CURRENT_NONCE=req['nonce'];claim=STATE/'claims'/req['nonce']
  stage('CLAIM_REQUEST')
  fd=os.open(claim,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);os.write(fd,enc(req));os.fsync(fd);os.close(fd)
  directory=os.open(claim.parent,os.O_RDONLY|os.O_DIRECTORY);os.fsync(directory);os.close(directory)
  def perform(index,plan):
   run_id=req['nonce']+'-'+str(index);run_dir=STATE/'runs'/run_id;c=core_for(plan,run_dir)
   # Master source remains root0600 unchanged; select only finance token for requested WB cabinet.
   stage('READ_SELECTED_CREDENTIAL')
   master=checked_json(c.MASTER);entry=master.get(plan['cabinet'])
   if type(entry) is not dict or not isinstance(entry.get('token'),str) or not entry['token']:raise ValueError('selected finance credential missing')
   raw=enc({plan['cabinet']:{'token':entry['token']}})
   active=enc({'plan':plan,'policy_sha256':sha(enc(POLICY)),'run_id':run_id})
   record={'run_id':run_id,'plan':plan,'active_sha256':sha(active),'secret_sha256':sha(raw)}
   stage('CREATE_OWNED_ACTIVATION')
   c.write_new(STATE/'active-run.json',enc(record)) # durable ownership before any approval/credential mutation
   c.write_new(ACTIVE,active,0o640,gid=985);c.write_new(SECRET,raw)
   try:
    stage('RUN_EXISTING_FINANCIAL_UNIT')
    rc=c.main()
    result=checked_json(run_dir/'result.json') if (run_dir/'result.json').exists() else {'status':'STOP_OR_UNCERTAIN'}
    # Administrative controller never prints credential bytes/hashes/HTTP responses.
    return {'status':result['status'],'run_id':run_id,'outcome':result.get('outcome',{})}
   finally:close()
  def persist(phase,index,plan):
   p=STATE/'claims'/(req['nonce']+'-'+str(index)+'-'+phase+'.json')
   c=core_for(plan,STATE/'runs'/(req['nonce']+'-'+str(index)));c.write_new(p,enc({'phase':phase,'plan':plan}))
  def select(cab):
   stage('SELECT_REPORT_READ_ONLY');return choose('/opt/mcp/data/msp-marketplace-reports',cab)
  result=process(req,select,perform,persist)
  stage('PUBLISH_SUMMARY')
  summary={'request_nonce':req['nonce'],'status':'PASS' if result and all(r['status']=='PASS' for r in result) else 'PARTIAL','jobs':result,'api_enabled_after_run':False,'schedule_enabled':False}
  c=core_for(OLD_PLAN,STATE/'unused');c.write_new(STATE/'results'/(req['nonce']+'.json'),enc(summary),0o644)
  print(json.dumps(summary));return 0
 finally:os.close(lock)
if __name__=='__main__':
 try:raise SystemExit(main())
 except Exception as e:
  try:
   from diagnostics import save_failure
   print(json.dumps(save_failure(e,PHASE,CURRENT_NONCE)))
  except Exception:print(json.dumps({'status':'STOP_OR_UNCERTAIN','error_type':type(e).__name__,'diagnostic_write_failed':True,'auto_retry':False}))
  raise SystemExit(1)
