"""Generated unprivileged exact-receipt recovery; never executes as root."""
import base64,hashlib,importlib.util,json,os,subprocess,time
from pathlib import Path
RELEASE='__CONTROL_RELEASE__'
CONTROL_SHA='__ROOT_CONTROL_SHA__'
DRIVER_BASE64='__DRIVER_BASE64__'
EXPECTED_NONCE='0983f5a05a704fdebc8579ec9aa48bd1'
PREVIOUS_NONCE='9b4aa59b7aaf43d4a2b320cf65effc86'
BASE=Path('/home/hermes/.local/share/msp/finance-history-driver')
STATE=Path('/home/hermes/.local/state/msp-finance-history-wb-laser-master-20261106')
ROOT=Path('/var/lib/msp-finance-control')
def validate_reconciled_timeout(prior,diagnostic,now):
 if prior.get('request_nonce')!=PREVIOUS_NONCE:raise ValueError('unexpected prior receipt')
 if diagnostic.get('request_nonce')!=EXPECTED_NONCE or diagnostic.get('status')!='READ_ONLY_PASS' or not 0<=now-diagnostic.get('checked_epoch',0)<=1800:raise ValueError('fresh exact root reconciliation required')
 recovered=diagnostic.get('interrupted_recovery',{});receipt=recovered.get('receipt',{});evidence=recovered.get('evidence',{});plan=recovered.get('plan',{})
 expected={'schema':1,'cabinet':'wb_laser_master','year':2026,'report_id':743994450,'report_type':1,'max_send_entries':3}
 if plan!=expected:raise ValueError('different interrupted plan')
 if not (evidence.get('stage_status')=='STAGED_COMPLETE' and type(evidence.get('pages')) is int and evidence['pages']>0 and type(evidence.get('budget_entries')) is int and evidence['budget_entries']>=evidence['pages']+1 and evidence.get('http_attempts')==evidence['budget_entries'] and evidence.get('unknown_outcomes')==0 and evidence.get('pending_response_present') is False):raise ValueError('terminal pages/admission not reconciled')
 statuses=evidence.get('http_statuses',[])
 if len(statuses)!=evidence['http_attempts'] or statuses[-1:]!=[204] or any(x!=200 for x in statuses[:-1]):raise ValueError('not all HTTP outcomes known')
 if receipt.get('status')=='STAGED_PUBLICATION_PENDING':
  if diagnostic.get('selected_plan')!=expected:raise ValueError('local replay must select exact interrupted report')
 elif not (receipt.get('verified') is True and receipt.get('publication_verified') is True and receipt.get('page_hashes_verified') is True and receipt.get('report_id')==743994450 and receipt.get('report_type')==1 and receipt.get('cabinet')=='wb_laser_master' and receipt.get('terminal_http_status')==204):raise ValueError('not eligible for local-only recovery')

def main():
 if os.geteuid()!=1001:raise ValueError('hermes only')
 installed=json.loads((ROOT/'INSTALL.json').read_text())
 if installed.get('release')!=RELEASE:raise ValueError('expected reviewed release not installed')
 control=Path(RELEASE)/'control.py';st=control.stat()
 if st.st_uid!=0 or st.st_mode&0o022 or control.is_symlink() or hashlib.sha256(control.read_bytes()).hexdigest()!=CONTROL_SHA:raise ValueError('root controller pin mismatch')
 raw=base64.b64decode(DRIVER_BASE64);digest=hashlib.sha256(raw).hexdigest();source=BASE/('driver-'+digest+'.py')
 if source.exists() and source.read_bytes()!=raw:raise ValueError('driver snapshot drift')
 if not source.exists():source.write_bytes(raw);source.chmod(0o600)
 spec=importlib.util.spec_from_file_location('recovered_discovery_driver',source);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 m.CABINETS=('wb_laser_master',);m.STATE=STATE;m.EXPECTED_RELEASE=RELEASE;m.ROOT_PREFLIGHT_PINS[RELEASE]=CONTROL_SHA;m.ADMISSION_PREFLIGHT=True
 path=STATE/'state.json';before=path.read_bytes();value=json.loads(before)
 if value.get('phase')!='HOLD' or value.get('last',{}).get('request_nonce')!=PREVIOUS_NONCE:raise ValueError('known hold no longer current; reconcile, do not replay')
 req=json.loads((ROOT/'inbox/request.json').read_text());prior=m.root_json(ROOT/'results'/(PREVIOUS_NONCE+'.json'))
 if req.get('nonce')!=EXPECTED_NONCE or value['last']!=prior:raise ValueError('foreign/changed execution, no retry')
 if value.get('reason')!='TimeoutExpired' or m.safe_budget_pause(prior) is None:raise ValueError('not the exact verified prior normal pause')
 diagnostic=m.root_json(ROOT/'results/diagnostics-latest.json')
 validate_reconciled_timeout(prior,diagnostic,time.time())
 m.unit_closed()
 running=subprocess.run(['/usr/bin/systemctl','--user','show','msp-wb-laser-master-backfill-20261106.service','-p','ActiveState','--value'],capture_output=True,text=True,check=True).stdout.strip()
 if running not in ('inactive','failed'):raise ValueError('driver active; no concurrent state repair')
 backup=BASE/'backups'/('memory-recovery-'+hashlib.sha256(before).hexdigest());backup.mkdir(mode=0o700,exist_ok=True)
 for name,payload in [('state.json',before),('wrapper.py',(BASE/'wb-laser-master-20261106.py').read_bytes())]:
  target=backup/name
  if target.exists():
   if target.read_bytes()!=payload:raise ValueError('existing recovery backup differs')
  else:target.write_bytes(payload);target.chmod(0o600)
 wrapper='import hashlib,importlib.util\nfrom pathlib import Path\nSOURCE=Path('+repr(str(source))+')\nif hashlib.sha256(SOURCE.read_bytes()).hexdigest()!='+repr(digest)+':raise RuntimeError("driver snapshot changed")\nspec=importlib.util.spec_from_file_location("finance_driver",SOURCE)\ndriver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)\ndriver.CABINETS=("wb_laser_master",)\ndriver.STATE=Path('+repr(str(STATE))+')\ndriver.EXPECTED_RELEASE='+repr(RELEASE)+'\ndriver.ROOT_PREFLIGHT_PINS[driver.EXPECTED_RELEASE]='+repr(CONTROL_SHA)+'\ndriver.ADMISSION_PREFLIGHT=True\nif __name__=="__main__":raise SystemExit(driver.main())\n'
 target=BASE/'wb-laser-master-20261106.py';temp=target.with_suffix('.recovery');temp.write_text(wrapper);temp.chmod(0o600);os.replace(temp,target)
 value.update(phase='DISPATCHING',wakes=value['wakes']+1,reason='owner_authorized_verified_timeout_recovery')
 m.write(path,value) # durable before allocating a new nonce; never repeat on uncertain launch
 try:
  result=m.wake('wb_laser_master');value['last']=result
  if result.get('status')=='PASS':value.update(phase='COOLDOWN',reason='memory_recovery_complete',resume_not_before=time.time()+70)
  else:value.update(phase='HOLD',reason='timeout_recovery_requires_inspection')
 except Exception as exc:
  value.update(phase='HOLD',reason='recovery_uncertain_no_retry',failure=m.failure_location(exc,'timeout_recovery'));m.write(path,value);raise
 m.write(path,value)
 manifest={'cabinet':'wb_laser_master','release':RELEASE,'driver_sha256':digest,'wrapper_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'root_control_sha256':CONTROL_SHA,'root_admission_preflight':True,'daily_schedule':False,'other_cabinets':False,'state':str(STATE),'recovery_backup':str(backup)}
 (BASE/'wb-laser-master-20261106-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 print(json.dumps({'recovery_status':value['phase'],'request_nonce':result['request_nonce'],'budget_reset':False}))
 if value['phase']=='COOLDOWN':subprocess.run(['/usr/bin/systemctl','--user','restart','msp-wb-laser-master-backfill-20261106.service'],check=True)
 else:return 2
 return 0
if __name__=='__main__':raise SystemExit(main())
