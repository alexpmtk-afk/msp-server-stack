"""Upgrade WB policy only; pause coordinator, never kill/replay shared worker."""
import datetime,fcntl,hashlib,importlib.util,json,os,signal,sys,time,traceback,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import root_common as r
ROOT=Path(__file__).resolve().parent
BASE=Path('/var/lib/msp-wb-daily-weekly')
UNIT='msp-wb-daily-weekly.service'
UNIT_DIR=Path('/etc/systemd/system')
FINANCE=Path('/var/lib/msp-finance-control/controller.lock')
DROP=Path('/run/systemd/system/msp-wb-pilot.service.d/97-wb-daily-weekly.conf')
PUBLIC=BASE/'optional-policy-upgrade.json'
RULE='WB_ANY_REPORT_V2_20261113'
OWNED=False

def atomic(path,value,mode=0o644):
 if path.exists():r.trust(path,mode)
 tmp=path.with_name('.'+path.name+'.'+uuid.uuid4().hex+'.tmp');r.save(tmp,r.doc(value) if not isinstance(value,bytes) else value,mode);os.replace(tmp,path);r.syncdir(path.parent)
def state(unit):
 return dict(x.split('=',1) for x in r.run(['/usr/bin/systemctl','show',unit,'-p','ActiveState','-p','SubState','-p','PrivateNetwork','-p','DropInPaths','-p','ExecStart','-p','UnitFileState']).decode().splitlines() if '=' in x)
def verify_files(b):
 for name,pin in b['files'].items():
  p=Path(name);r.trust(p,0o644)
  if r.sha(p.read_bytes())!=pin:raise ValueError('installation wiring drift')
def old_controller(oldroot):
 spec=importlib.util.spec_from_file_location('wb_accepted_handoff',oldroot/'controller.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def pause_and_close(oldroot,deadline=None):
 deadline=deadline or time.monotonic()+180
 r.run(['/usr/bin/systemctl','stop','--no-block',UNIT])
 while state(UNIT)['ActiveState'] not in ('inactive','failed'):
  if time.monotonic()>=deadline:raise ValueError('coordinator pause unconfirmed')
  time.sleep(1)
 # No other sender is stopped or started here. Existing WB requests may finish.
 while True:
  s=state(r.SERVICE)
  if s['ActiveState'] in ('inactive','failed'):break
  if s['DropInPaths'].split()!=[str(DROP)]:raise ValueError('foreign live worker; no cleanup')
  if time.monotonic()>=deadline:raise ValueError('worker still live; preserve activation')
  time.sleep(1)
 controls=sorted(set((BASE/'runs').rglob('activation.json'))|set((BASE/'runs').rglob('activation-intent.json')))
 if controls:
  old=old_controller(oldroot);cycles=[]
  for path in (BASE/'cycles').glob('*.json'):
   if path.name.endswith(('.public.json','.observer.json')):continue
   r.trust(path,0o600);cycles.append(json.loads(path.read_bytes()))
  for parent in sorted({p.parent for p in controls}):
   found=[]
   for cycle in cycles:
    for job in cycle['jobs']:
     expected=BASE/'runs'/cycle['cycle_id']/job['cabinet']/job['period']/(job['from']+'-'+job['to'])/('attempt-%02d'%job['attempts'])
     if expected==parent:found.append((cycle,job))
   if len(found)!=1:raise ValueError('unmatched retained activation')
   cycle,job=found[0];r.trust(parent/'claim.json',0o600)
   claim=json.loads((parent/'claim.json').read_bytes())
   if not __import__('re').fullmatch('[0-9a-f]{32}',claim.get('nonce','')):raise ValueError('retained claim identity')
   old.context(cycle,job)
   if old.LEDGER!=parent:raise ValueError('handoff context mismatch')
   old.finish_intent();old.reconcile_after_boot();old.close_inactive()
 s=state(r.SERVICE)
 if s['ActiveState'] not in ('inactive','failed') or s['PrivateNetwork']!='yes' or s['DropInPaths']:raise ValueError('shared executor not isolated after owned handoff')
 if (oldroot/'cabinets.json').exists():raise ValueError('unreconciled old credential artifact')


def main():
 global OWNED
 if os.geteuid()!=0:raise PermissionError('Linux root console required')
 r.verify_payload();r.validate_platform();b=json.loads((ROOT/'upgrade-baseline.json').read_bytes());oldroot=Path(b['old_root']);r.trust(oldroot)
 installed=BASE/'installation.json';r.trust(installed,0o644);info=json.loads(installed.read_bytes())
 if info.get('optional_buyout_policy')==RULE:
  active=Path(info['root_release']);r.trust(active)
  if r.sha((active/'MANIFEST.json').read_bytes())!=r.sha((ROOT/'MANIFEST.json').read_bytes()):raise ValueError('different active policy release')
  if str(active/'controller.py') not in state(UNIT)['ExecStart']:raise ValueError('active policy wiring drift')
  print(json.dumps({'status':'ALREADY_UPGRADED','root_release':str(active),'source_replayed':False}));return
 if PUBLIC.exists():raise ValueError('partial policy upgrade exists; reconcile before replay')
 r.trust(oldroot/'MANIFEST.json',0o644)
 if r.sha((oldroot/'MANIFEST.json').read_bytes())!=b['old_manifest_sha256']:raise ValueError('old source manifest drift')
 for name,pin in json.loads((oldroot/'MANIFEST.json').read_bytes()).items():
  path=oldroot/name;r.trust(path,0o644)
  if r.sha(path.read_bytes())!=pin:raise ValueError('installed source drift')
 verify_files(b)
 if info.get('status')!='INSTALLED' or info['root_release']!=str(oldroot):raise ValueError('unexpected installed release')
 for p in (BASE,UNIT_DIR):r.trust(p,0o755)
 r.trust(BASE/'controller.lock',0o600);finance=FINANCE;r.trust(finance,0o600)
 atomic(PUBLIC,{'status':'PAUSING_OWN_COORDINATOR','old_release':str(oldroot),'candidate':str(ROOT)})
 OWNED=True
 pause_and_close(oldroot)
 with (BASE/'controller.lock').open('rb') as life,finance.open('rb') as slot:
  fcntl.flock(life,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(slot,fcntl.LOCK_EX|fcntl.LOCK_NB)
  verify_files(b)
  s=state(r.SERVICE)
  if s['ActiveState'] not in ('inactive','failed') or s['PrivateNetwork']!='yes' or s['DropInPaths']:raise ValueError('executor changed after pause')
  backup=BASE/('optional-policy-backups-'+ROOT.name);os.mkdir(backup,0o755);os.chmod(backup,0o755);r.syncdir(BASE)
  for i,name in enumerate(b['changed_files']):r.save(backup/('%02d.backup'%i),Path(name).read_bytes(),0o600)
  r.save(backup/'targets.json',r.doc(b),0o600)
  unit=UNIT_DIR/UNIT;raw=unit.read_bytes();needle=str(oldroot/'controller.py').encode()
  if raw.count(needle)!=1:raise ValueError('controller target not exact')
  newunit=raw.replace(needle,str(ROOT/'controller.py').encode());atomic(unit,newunit)
  for path in (BASE/'schedule.json',installed):
   doc=json.loads(path.read_bytes());doc.update(root_release=str(ROOT),optional_buyout_policy=RULE,report_availability_policy=RULE);atomic(path,doc)
  r.run(['/usr/bin/systemctl','daemon-reload'])
  if unit.read_bytes()!=newunit or str(ROOT/'controller.py') not in state(UNIT)['ExecStart']:raise ValueError('new controller readback mismatch')
  timer=state('msp-wb-daily-weekly.timer')
  if timer['ActiveState']!='active' or timer['UnitFileState']!='enabled':raise ValueError('existing timer not enabled')
 # The same saved cycle, nonces, attempts, source pages and HTTP budgets resume.
 r.run(['/usr/bin/systemctl','start','--no-block',UNIT])
 proof=state(UNIT)
 if str(ROOT/'controller.py') not in proof['ExecStart']:raise ValueError('new service target not observed')
 result={'status':'UPGRADED','root_release':str(ROOT),'policy':RULE,'wb_time_moscow':'08:45','ozon_changed':False,'source_replayed':False,'request_budgets_reset':False,'initial_backfill_restarted':False,'service_state':proof['ActiveState'],'old_journals_preserved':True}
 atomic(PUBLIC,result);print(json.dumps(result))

if __name__=='__main__':
 try:main()
 except Exception as exc:
  if os.geteuid()==0 and OWNED and BASE.exists():
   frames=[{'file':Path(x.filename).name,'function':x.name,'line':x.lineno} for x in traceback.extract_tb(exc.__traceback__)[-6:]]
   atomic(PUBLIC,{'status':'UPGRADE_HOLD','error_type':type(exc).__name__,'frames':frames,'source_replay_forbidden':True})
  else:print(json.dumps({'status':'PREFLIGHT_REFUSED','error_type':type(exc).__name__,'no_installation_writes':True}))
  raise SystemExit(2)
