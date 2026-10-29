"""Pinned synthetic G1-G4 re-review; network/DNS denied, no production paths."""
import argparse,importlib.util,json,os,signal,subprocess,sys,tempfile
from pathlib import Path
from unittest.mock import patch

def emit(check,**kw):print(json.dumps(dict(check=check,**kw),sort_keys=True),flush=True)
def audit(event,args):
 if event in ('socket.connect','socket.getaddrinfo'):raise AssertionError('Network prohibited')
sys.addaudithook(audit)
ap=argparse.ArgumentParser();ap.add_argument('--checkout',type=Path,required=True);ap.add_argument('--before',type=Path);ap.add_argument('--child',type=Path);ap.add_argument('--dataset',default='wb');ap.add_argument('--point');ap.add_argument('--expected');a=ap.parse_args()
checkout=a.checkout.resolve();sys.path.insert(0,str(checkout))
from apps.msp_marketplace_reports import generation_store as g
from apps.msp_marketplace_reports import archive as ar
spec=importlib.util.spec_from_file_location('fixture_module',checkout/'tests/test_msp_marketplace_generations.py');fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
assert Path(g.__file__).resolve().is_relative_to(checkout)
def args(root,ds='wb',period='2026'):return (root,'wb_weekly_finance_main','wb_laser_master',period) if ds=='wb' else (root,'ozon_final_realization','ozon_laser_master',period)
def files(ds='wb',amount='10',year='2026'):
 batch=fixture.wb_files(amount) if ds=='wb' else fixture.ozon_final_files(january=amount,february='7')
 if year!='2026':batch={k:v.replace(b'2026',year.encode()) for k,v in batch.items()}
 return batch

def scope(root,ds='wb',year='2026'):return g._scope(*args(root,ds,year))
def snapshot(root):return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
def rejected(fn):
 try:fn()
 except (ValueError,TypeError,OSError):return True
 return False
if a.child:
 if a.point=='init_parent_sync':
  real=g._sync_dir
  def die_before_sync(path):
   if Path(path)==a.child.parent and a.child.exists():os.kill(os.getpid(),signal.SIGKILL)
   return real(path)
  g._sync_dir=die_before_sync
 def kill(where):
  if where==a.point:os.kill(os.getpid(),signal.SIGKILL)
 g.publish_batch(*args(a.child,a.dataset),files(a.dataset,'20'),expected_generation=a.expected,fault=kill)
 sys.exit(0)
with tempfile.TemporaryDirectory(prefix='g1g4-fixtures-',dir=str(Path(__file__).resolve().parent)) as temp:
 work=Path(temp);index=0
 def new():
  global index
  index+=1;return work/str(index)
 old=None
 if a.before:
  spec=importlib.util.spec_from_file_location('apps.msp_marketplace_reports.old_gs',a.before/'apps/msp_marketplace_reports/generation_store.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
 for label,m in [('before',old),('after',g)]:
  if m is None:continue
  # G1: original exact fully-staged candidate, including forged caller pin.
  root=new();one=m.publish_batch(*args(root),files());before=m.read_active(*args(root))
  try:m.publish_batch(*args(root),files(amount='20'),expected_generation=one['generation'],fault=lambda p:(_ for _ in ()).throw(OSError('stop')) if p=='before_commit' else None)
  except OSError:pass
  candidate=m.reconcile(*args(root))['uncommitted_generations'][0];digest=ar._sha((scope(root)/'generations'/candidate/'generation.json').read_bytes())
  blocked=rejected(lambda:m.read_generation(*args(root),candidate,**({'expected_digest':digest} if label=='after' else {})))
  assert blocked==(label=='after')
  assert m.read_active(*args(root))['files']==files()
  emit('G1_ORIGINAL',version=label,public_candidate_blocked=blocked,private_validator_accepts_candidate=m._read_generation(scope(root),candidate,digest)['files']==files(amount='20'))
  # G2: two committed snapshots, then missing receipt.
  root=new();one=m.publish_batch(*args(root),files());two=m.publish_batch(*args(root),files(amount='20'),expected_generation=one['generation']);(scope(root)/'CURRENT.json').unlink();s=m.reconcile(*args(root))
  assert s['status']==('PENDING' if label=='before' else 'UNKNOWN_COMMIT_STATE')
  emit('G2_ORIGINAL',version=label,status=s['status'],committed_mislabeled_as_uncommitted='uncommitted_generations' in s)
  # G3: repack A consistently, leave CURRENT and child B unchanged.
  root=new();one=m.publish_batch(*args(root),files());pin=m.read_active(*args(root))['manifest_sha256'];two=m.publish_batch(*args(root),files(amount='20'),expected_generation=one['generation']);p=scope(root)/'generations'/one['generation'];replacement=files(amount='99')
  for name,raw in replacement.items():(p/name).write_bytes(raw)
  desc=json.loads((p/'generation.json').read_text())
  for entry in desc['files']:entry['sha256']=ar._sha(replacement[entry['path']]);entry['bytes']=len(replacement[entry['path']])
  (p/'generation.json').write_text(json.dumps(desc));forged=ar._sha((p/'generation.json').read_bytes())
  blocked=rejected(lambda:m.read_generation(*args(root),one['generation'],**({'expected_digest':pin} if label=='after' else {})))
  assert blocked==(label=='after')
  emit('G3_ORIGINAL',version=label,old_read_blocked=blocked,reconcile_status=m.reconcile(*args(root))['status'],forged_pin_also_blocked=rejected(lambda:m.read_generation(*args(root),one['generation'],expected_digest=forged)) if label=='after' else None)
  # G4 original: sync every new ancestor in parent, no failures yet.
  root=new();syncs=[];real=os.fsync
  def trace(fd):syncs.append(os.readlink('/proc/self/fd/'+str(fd)));return real(fd)
  with patch.object(os,'fsync',trace):m.publish_batch(*args(root),files())
  required=[root.parent,root,root/'.b7-generations',root/'.b7-generations/wb_weekly_finance_main',scope(root).parent]
  missing=[p for p in required if str(p) not in syncs]
  assert bool(missing)==(label=='before')
  emit('G4_ORIGINAL_NORMAL_TRACE',version=label,missing_parent_sync_count=len(missing))
 # Wrong/missing pins on active and committed ancestor.
 pin_cases=0
 root=new();one=g.publish_batch(*args(root),files());two=g.publish_batch(*args(root),files(amount='20'),expected_generation=one['generation'])
 for receipt in [one,two]:
  assert g.read_generation(*args(root),receipt['generation'],expected_digest=receipt['manifest_sha256'])['generation']==receipt['generation']
  for pin in [None,True,False,1,1.0,b'x','', '0'*63,'A'*64,'g'*64,'0'*64]:
   assert rejected(lambda:g.read_generation(*args(root),receipt['generation'],expected_digest=pin));pin_cases+=1
  assert rejected(lambda:g.read_generation(*args(root),receipt['generation']));pin_cases+=1
 emit('PIN_NEGATIVE_CASES',passed=pin_cases)
 pointer_cases=0
 for mode in ['missing','truncated','null','duplicate','bad_schema','bad_digest','unknown_generation','wrong_digest']:
  root=new();one=g.publish_batch(*args(root),files());two=g.publish_batch(*args(root),files(amount='20'),expected_generation=one['generation']);p=scope(root)/'CURRENT.json';d=json.loads(p.read_text())
  if mode=='missing':p.unlink()
  elif mode=='truncated':p.write_text('{')
  elif mode=='null':p.write_text('null')
  elif mode=='duplicate':p.write_text('{"schema":true,'+p.read_text()[1:])
  else:
   d[{'bad_schema':'schema','bad_digest':'sha256','wrong_digest':'sha256','unknown_generation':'generation'}[mode]]={'bad_schema':True,'bad_digest':'x','wrong_digest':'0'*64,'unknown_generation':'0'*32}[mode];p.write_text(json.dumps(d))
  before=snapshot(root);assert rejected(lambda:g.read_active(*args(root)))
  assert g.reconcile(*args(root))['status'] in ('UNKNOWN_COMMIT_STATE','RECOVERY_REQUIRED')
  try:g.publish_batch(*args(root),files(amount='30'),expected_generation=two['generation'])
  except (ValueError,OSError):pass
  else:raise AssertionError('write after corrupt pointer')
  assert snapshot(root)==before;pointer_cases+=1
 emit('POINTER_CASES',passed=pointer_cases)
 # New G4 counterexample: mkdir succeeds, its parent fsync fails, retry skips it.
 retry_cases=[]
 for level in range(6):
  root=new();chain=[root,root/'.b7-generations',root/'.b7-generations/wb_weekly_finance_main',scope(root).parent,scope(root),scope(root)/'generations'];created=chain[level];real=g._sync_dir;failed=[False]
  def fail_parent(path):
   if Path(path)==created.parent and created.exists() and not failed[0]:failed[0]=True;raise OSError(5,'synthetic parent fsync failure')
   return real(path)
  try:
   with patch.object(g,'_sync_dir',fail_parent):g.publish_batch(*args(root),files())
  except OSError:pass
  else:raise AssertionError('failure not reached')
  trace=[]
  def record(path):trace.append(Path(path));return real(path)
  with patch.object(g,'_sync_dir',record):receipt=g.publish_batch(*args(root),files())
  case=dict(level=level,created=str(created.relative_to(root)) if created!=root else '.',retry_status=receipt['status'],previously_failed_parent_retried=created.parent in trace)
  assert created.parent in trace,case
  retry_cases.append(case)
 emit('G4_RETRY_AFTER_FAILED_PARENT_SYNC',cases=retry_cases)
 # After several commits, introduce a new year and fail its containing-dir sync.
 root=new();one=g.publish_batch(*args(root),files());two=g.publish_batch(*args(root),files(amount='20'),expected_generation=one['generation']);three=g.publish_batch(*args(root),files(amount='30'),expected_generation=two['generation']);s=scope(root,year='2027');real=g._sync_dir;failed=[False]
 def fail_year_parent(path):
  if Path(path)==s.parent and s.exists() and not failed[0]:failed[0]=True;raise OSError('new year parent sync')
  return real(path)
 try:
  with patch.object(g,'_sync_dir',fail_year_parent):g.publish_batch(*args(root,period='2027'),files(year='2027'))
 except OSError:pass
 trace=[]
 def rec(path):trace.append(Path(path));return real(path)
 with patch.object(g,'_sync_dir',rec):r=g.publish_batch(*args(root,period='2027'),files(year='2027'))
 assert s.parent in trace
 emit('G4_NEW_YEAR_RETRY',retry_status=r['status'],failed_parent_retried=s.parent in trace,previous_year_unchanged=g.read_active(*args(root))['generation']==three['generation'])
 # Real process death after mkdir but before its containing parent fsync.
 root=new()
 child=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--checkout',str(checkout),'--child',str(root),'--point','init_parent_sync'],capture_output=True,text=True,timeout=30)
 assert child.returncode==-signal.SIGKILL and root.exists()
 real=g._sync_dir;trace=[]
 def record_retry(path):trace.append(Path(path));return real(path)
 with patch.object(g,'_sync_dir',record_retry):receipt=g.publish_batch(*args(root),files())
 assert root.parent in trace
 emit('G4_SIGKILL_INIT_RETRY',returncode=child.returncode,retry_status=receipt['status'],missing_parent_retried=root.parent in trace)
 # Existing store: each fsync failure after three successful commits.
 root=new();r=None
 for amount in ['10','20','30']:r=g.publish_batch(*args(root),files(amount=amount),expected_generation=r['generation'] if r else None)
 real=os.fsync;calls=[]
 def count(fd):calls.append(fd);return real(fd)
 with patch.object(os,'fsync',count):g.publish_batch(*args(root),files(amount='40'),expected_generation=r['generation'])
 io_cases=0
 for nth in range(len(calls)):
  root=new();r=None
  for amount in ['10','20','30']:r=g.publish_batch(*args(root),files(amount=amount),expected_generation=r['generation'] if r else None)
  old=snapshot(scope(root)/'generations');n=[0]
  def fail(fd):
   i=n[0];n[0]+=1
   if i==nth:raise OSError(5,'synthetic fsync')
   return real(fd)
  try:
   with patch.object(os,'fsync',fail):g.publish_batch(*args(root),files(amount='40'),expected_generation=r['generation'])
  except (OSError,g.CommitUncertainError):pass
  else:raise AssertionError('expected fsync failure')
  active=g.read_active(*args(root));assert active['files'] in (files(amount='30'),files(amount='40'))
  for path,data in old.items():assert (scope(root)/'generations'/path).read_bytes()==data
  io_cases+=1
 emit('EXISTING_STORE_FSYNC_FAILURES',passed=io_cases)
 # Fresh initialization: fail every actual fsync call, require no COMMITTED.
 root=new();real=os.fsync;calls=[]
 def count_initial(fd):calls.append(fd);return real(fd)
 with patch.object(os,'fsync',count_initial):g.publish_batch(*args(root),files())
 initial_io_cases=0
 for nth in range(len(calls)):
  root=new();n=[0];caught=False
  def fail_initial(fd):
   i=n[0];n[0]+=1
   if i==nth:raise OSError(5,'synthetic initializer fsync')
   return real(fd)
  try:
   with patch.object(os,'fsync',fail_initial):g.publish_batch(*args(root),files())
  except (OSError,g.CommitUncertainError):caught=True
  assert caught
  # Final directory sync can fail after pointer replacement: uncertainty is
  # expected, not a false assertion that the commit never occurred.
  current=scope(root)/'CURRENT.json'
  if current.exists():assert g.read_active(*args(root))['files']==files()
  initial_io_cases+=1
 emit('FIRST_INIT_ALL_FSYNC_FAILURES',passed=initial_io_cases)
 # Actual SIGKILL on all declared checkpoints, both datasets, first/update.
 kills=0
 for ds in ['wb','ozon']:
  points=['after_stage_dir',*['after_file:'+f for f in sorted(files(ds))],'after_descriptor','before_commit','after_commit']
  for initial in [True,False]:
   for point in points:
    root=new();prev=None
    if not initial:prev=g.publish_batch(*args(root,ds),files(ds))
    old=snapshot(scope(root,ds)/'generations'/prev['generation']) if prev else {}
    cmd=[sys.executable,'-B',str(Path(__file__).resolve()),'--checkout',str(checkout),'--child',str(root),'--dataset',ds,'--point',point]
    if prev:cmd+=['--expected',prev['generation']]
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=30);assert p.returncode==-signal.SIGKILL,(point,p.stderr)
    state=g.reconcile(*args(root,ds))
    if point=='after_commit':assert g.read_active(*args(root,ds))['files']==files(ds,'20') and state['status']=='ACTIVE_VERIFIED'
    elif initial:assert state['status']=='UNKNOWN_COMMIT_STATE' and rejected(lambda:g.read_active(*args(root,ds)))
    else:assert state['status']=='RECOVERY_REQUIRED' and g.read_active(*args(root,ds))['generation']==prev['generation']
    if prev:assert snapshot(scope(root,ds)/'generations'/prev['generation'])==old
    kills+=1
 emit('SIGKILL_CASES',passed=kills)
 emit('COMPLETE',pin_negative=pin_cases,pointer_cases=pointer_cases,retry_parent_cases=len(retry_cases),new_year_retry_cases=1,existing_store_fsync_cases=io_cases,initial_fsync_cases=initial_io_cases,sigkill_cases=kills,initializer_sigkill_cases=1)
