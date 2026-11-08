"""One exact terminal-reconciliation handoff; no HTTP, no root execution."""
import base64,hashlib,importlib.util,json,os,subprocess,time
from pathlib import Path
RELEASE='__CONTROL_RELEASE__'
CONTROL_SHA='__ROOT_CONTROL_SHA__'
DRIVER_BASE64='__DRIVER_BASE64__'
NONCE='82bf1ab2ecf94c79810d82f739232c84'
BASE=Path('/home/hermes/.local/share/msp/finance-history-driver')
STATE=Path('/home/hermes/.local/state/msp-finance-history-wb-laser-master-20261106')
ROOT=Path('/var/lib/msp-finance-control')
def main():
 if os.geteuid()!=1001:raise ValueError('hermes only')
 if json.loads((ROOT/'INSTALL.json').read_text()).get('release')!=RELEASE:raise ValueError('expected reviewed release not installed')
 control=Path(RELEASE)/'control.py';st=control.stat()
 if st.st_uid!=0 or st.st_mode&0o022 or control.is_symlink() or hashlib.sha256(control.read_bytes()).hexdigest()!=CONTROL_SHA:raise ValueError('root controller pin mismatch')
 unit='msp-wb-laser-master-backfill-20261106.service'
 r=subprocess.run(['/usr/bin/systemctl','--user','show',unit,'-p','ActiveState','--value'],capture_output=True,text=True,check=True).stdout.strip()
 if r not in ('inactive','failed'):raise ValueError('driver active; no repeated handoff')
 raw=base64.b64decode(DRIVER_BASE64);digest=hashlib.sha256(raw).hexdigest();source=BASE/('driver-'+digest+'.py')
 if source.exists() and source.read_bytes()!=raw:raise ValueError('driver drift')
 if not source.exists():source.write_bytes(raw);source.chmod(0o600)
 spec=importlib.util.spec_from_file_location('lineage_driver',source);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 m.CABINETS=('wb_laser_master',);m.STATE=STATE;m.EXPECTED_RELEASE=RELEASE;m.ROOT_PREFLIGHT_PINS[RELEASE]=CONTROL_SHA;m.ADMISSION_PREFLIGHT=True
 path=STATE/'state.json';before=path.read_bytes();value=json.loads(before);prior=m.root_json(ROOT/'results'/(NONCE+'.json'));diag=m.root_json(ROOT/'results/diagnostics-latest.json')
 if value.get('phase')!='HOLD' or value.get('reason')!='non_pass_no_retry' or value.get('last')!=prior or prior.get('request_nonce')!=NONCE:raise ValueError('different HOLD; do not replay')
 if json.loads((ROOT/'inbox/request.json').read_text()).get('nonce')!=NONCE:raise ValueError('different current request')
 plan=diag.get('interrupted_recovery',{}).get('plan',{})
 if plan.get('report_id')!=812549574 or plan.get('report_type')!=1 or m.safe_terminal_stop(prior,diag) is None:raise ValueError('fresh exact terminal proof required')
 m.unit_closed()
 backup=BASE/'backups'/('lineage-'+hashlib.sha256(before).hexdigest());backup.mkdir(mode=0o700,exist_ok=True)
 target=BASE/'wb-laser-master-20261106.py'
 for name,payload in [('state.json',before),('wrapper.py',target.read_bytes())]:
  p=backup/name
  if p.exists() and p.read_bytes()!=payload:raise ValueError('backup conflict')
  if not p.exists():p.write_bytes(payload);p.chmod(0o600)
 wrapper='import hashlib,importlib.util\nfrom pathlib import Path\nSOURCE=Path('+repr(str(source))+')\nif hashlib.sha256(SOURCE.read_bytes()).hexdigest()!='+repr(digest)+':raise RuntimeError("driver snapshot changed")\nspec=importlib.util.spec_from_file_location("finance_driver",SOURCE)\ndriver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)\ndriver.CABINETS=("wb_laser_master",)\ndriver.STATE=Path('+repr(str(STATE))+')\ndriver.EXPECTED_RELEASE='+repr(RELEASE)+'\ndriver.ROOT_PREFLIGHT_PINS[driver.EXPECTED_RELEASE]='+repr(CONTROL_SHA)+'\ndriver.ADMISSION_PREFLIGHT=True\nif __name__=="__main__":raise SystemExit(driver.main())\n'
 temp=target.with_suffix('.lineage');temp.write_text(wrapper);temp.chmod(0o600);os.replace(temp,target)
 if not m.recover_terminal_stop(path,lambda:diag,lambda nonce:m.root_json(ROOT/'results'/(nonce+'.json')),m.unit_closed):raise ValueError('reconciliation refused; no reset')
 manifest={'cabinet':'wb_laser_master','release':RELEASE,'driver_sha256':digest,'wrapper_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'root_control_sha256':CONTROL_SHA,'root_admission_preflight':True,'daily_schedule':False,'other_cabinets':False,'state':str(STATE),'recovery_backup':str(backup)}
 (BASE/'wb-laser-master-20261106-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
 subprocess.run(['/usr/bin/systemctl','--user','restart',unit],check=True)
 r=subprocess.run(['/usr/bin/systemctl','--user','show',unit,'-p','ActiveState','--value'],capture_output=True,text=True,check=True).stdout.strip()
 if r!='active':raise ValueError('driver did not start; inspect, no replay')
 print(json.dumps({'status':'RECONCILED_DRIVER_STARTED','cabinet':'wb_laser_master','budget_reset':False,'provider_calls_by_helper':0,'report_completion':'NOT_YET_VERIFIED'}))
 return 0
if __name__=='__main__':raise SystemExit(main())
