"""Root-only local saved-data import. No provider, timer or service mutation."""
import fcntl,hashlib,importlib.util,json,os,stat,subprocess,sys
from pathlib import Path
STAGE=Path(__file__).resolve().parent
BASE=Path('/var/lib/msp-wb-daily-weekly')
RECEIPT=BASE/'novokshenov-nov9-import.json'
FINANCE=Path('/var/lib/msp-finance-control/controller.lock')
def sha(raw):return hashlib.sha256(raw).hexdigest()
def trust(p,uid=0):
 p=Path(p);s=p.lstat()
 if s.st_uid!=uid or s.st_mode&0o022 or stat.S_ISLNK(s.st_mode) or (p.is_file() and s.st_nlink!=1):raise ValueError('untrusted path')
def load_module(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def show(unit):
 raw=subprocess.check_output(['/usr/bin/systemctl','show',unit,'-p','ActiveState','-p','DropInPaths','-p','PrivateNetwork'],text=True)
 return dict(x.split('=',1) for x in raw.splitlines() if '=' in x)
def main():
 if os.geteuid()!=0:raise PermissionError('Linux root console required')
 for p in (STAGE,*STAGE.parents):trust(p)
 manifest=json.loads((STAGE/'MANIFEST.json').read_text())
 for name,pin in manifest.items():
  if Path(name).is_absolute() or '..' in Path(name).parts:raise ValueError('payload scope')
  p=STAGE/name;trust(p)
  if sha(p.read_bytes())!=pin:raise ValueError('payload digest')
 cfg=json.loads((STAGE/'baseline.json').read_text());release=Path(cfg['release'])
 for p in (release,*release.parents):trust(p)
 raw=(release/'MANIFEST.json').read_bytes();trust(release/'MANIFEST.json')
 if sha(raw)!=cfg['manifest_sha256']:raise ValueError('installed manifest mismatch')
 for name,pin in json.loads(raw).items():
  p=release/name;trust(p)
  if sha(p.read_bytes())!=pin:raise ValueError('installed source mismatch')
 info=json.loads((BASE/'installation.json').read_text())
 if info['root_release']!=str(release) or info.get('report_availability_policy')!='WB_ANY_REPORT_V2_20261113':raise ValueError('unexpected installed release')
 sys.path.insert(0,str(release));c=load_module('accepted_controller_import',release/'controller.py')
 helper=load_module('saved_document_import',STAGE/'publish.py')
 source=Path(cfg['capture'])
 for p in (source,*source.parents):trust(p)
 source_raw=source.read_bytes()
 if sha(source_raw)!=cfg['capture_sha256']:raise ValueError('source capture changed')
 capture=json.loads(source_raw);rows=helper.select(capture)
 terminal=source.with_name('page-01.json');trust(terminal);end=json.loads(terminal.read_bytes())
 if end.get('status')!=204 or end.get('rows') is not None or end.get('request_cursor')!=capture['rows'][-1]['rrdId']:raise ValueError('terminal pagination not proven')
 for p in (BASE,BASE/'controller.lock',FINANCE):trust(p)
 with (BASE/'controller.lock').open('rb') as life,FINANCE.open('rb') as finance:
  fcntl.flock(life,fcntl.LOCK_EX|fcntl.LOCK_NB);fcntl.flock(finance,fcntl.LOCK_EX|fcntl.LOCK_NB)
  if show(c.UNIT)['ActiveState'] not in ('inactive','failed'):raise ValueError('coordinator active; no service stop')
  sender=show(c.r.SERVICE)
  if sender['ActiveState'] not in ('inactive','failed') or sender['DropInPaths'] or sender['PrivateNetwork']!='yes':raise ValueError('sender not isolated')
  public=json.loads(c.PUBLIC.read_bytes());matches=[]
  for path in (BASE/'cycles').glob('*.json'):
   if path.name.endswith(('.public.json','.observer.json')):continue
   trust(path);cycle=json.loads(path.read_bytes())
   if cycle.get('cycle_id')==public.get('cycle_id'):
    matches=[(path,cycle,j) for j in cycle['jobs'] if (j['cabinet'],j['period'],j['from'],j['to'])==(helper.CAB,'daily',helper.DAY,helper.DAY)]
  if len(matches)!=1:raise ValueError('exact pending cycle not found')
  path,cycle,job=matches[0]
  if job['status'] not in ('WAITING_DATA','WAITING_NEXT_RUN','VERIFIED'):raise ValueError('in-flight or uncertain job')
  if RECEIPT.exists():
   trust(RECEIPT);old=json.loads(RECEIPT.read_bytes())
   if old.get('capture_sha256')!=cfg['capture_sha256'] or old.get('cycle_id')!=cycle['cycle_id']:raise ValueError('foreign import receipt')
  else:
   backup=BASE/'nov9-import-backup';os.mkdir(backup,0o700)
   archive=c.catalog.root(helper.CAB)
   for i,p in enumerate((path,BASE/'jobs.json',c.PUBLIC,c.public_path(cycle),archive/'sources.json',archive/'CURRENT.json')):
    c.r.save(backup/('%02d.backup'%i),p.read_bytes(),0o600)
   c.replace(RECEIPT,dict(status='IMPORT_STARTED',cycle_id=cycle['cycle_id'],capture_sha256=cfg['capture_sha256'],source_replayed=False),0o644)
  selected=STAGE/'selected-rows.json'
  raw=c.catalog.doc(rows)
  if selected.exists():
   trust(selected)
   if selected.read_bytes()!=raw:raise ValueError('staged source changed')
  else:c.r.save(selected,raw,0o644)
  result=json.loads(subprocess.check_output(['/usr/sbin/runuser','-u','msp-reports','--','/usr/bin/python3','-I','-B',str(STAGE/'publish.py')],timeout=300,text=True))
  if result.get('status')!='SOURCE_PUBLISHED' or (result.get('report_id'),result.get('date'),result.get('rows'))!=(helper.RID,helper.DAY,92):raise ValueError('publisher acknowledgement')
  # Read back real source rows through the accepted reader before settlement.
  index=c.verified_index(helper.CAB)
  if index['reports'].get(helper.KEY,{}).get('sha256')!=result['csv_sha256']:raise ValueError('source verification failed')
  known=json.loads((BASE/'jobs.json').read_bytes())
  settlement=dict(status='VERIFIED',cabinet=helper.CAB,period='daily',date_from=helper.DAY,date_to=helper.DAY,source_verified=True,origin='MANUAL_SAVED_FULL_DETAIL_IMPORT',parts=[dict(type=1,status='VERIFIED',report_ids=[helper.RID]),dict(type=2,status='NOT_LISTED',report_ids=[],reason='COUNTERPART_NOT_PUBLISHED_OTHER_TYPE_VERIFIED',financial_zero_inferred=False)],view_generation=result['view_generation'],view_sha256=result['view_sha256'],source_capture_sha256=cfg['capture_sha256'],original_worker_results_unchanged=True)
  known[job['key']]=settlement;c.replace(BASE/'jobs.json',known,0o600);c.plan.settle(job,settlement,0);cycle['status']=c.plan.status(cycle);c.persist(cycle);c.publish_cycle(cycle)
  receipt=dict(result,status='IMPORTED_AND_VERIFIED',cycle_id=cycle['cycle_id'],cycle_status=cycle['status'],capture_sha256=cfg['capture_sha256'],original_attempts_preserved=job['attempts'],provider_calls=0,timers_changed=False,source_journals_preserved=True)
  c.replace(RECEIPT,receipt);print(json.dumps(receipt))
if __name__=='__main__':main()
