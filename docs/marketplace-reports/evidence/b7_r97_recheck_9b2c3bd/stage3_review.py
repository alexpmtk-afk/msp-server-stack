"""Independent CURRENT repair tests: synthetic files, network/DNS denied."""
import argparse,base64,importlib.util,json,os,signal,subprocess,sys,tempfile
from pathlib import Path
from unittest.mock import patch

def audit(event,args):
 if event in ('socket.connect','socket.getaddrinfo'):raise AssertionError('Network prohibited')
sys.addaudithook(audit)
p=argparse.ArgumentParser();p.add_argument('--checkout',type=Path,required=True);p.add_argument('--child',type=Path);p.add_argument('--point');a=p.parse_args();sys.path.insert(0,str(a.checkout.resolve()))
from apps.msp_marketplace_reports import archive as ar,generation_store as gs,current_repair as cr
assert Path(cr.__file__).resolve().is_relative_to(a.checkout.resolve())
spec=importlib.util.spec_from_file_location('fixtures',a.checkout/'tests/test_msp_marketplace_generations.py');fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
def emit(check,**kw):print(json.dumps(dict(check=check,**kw),sort_keys=True),flush=True)
def args(root,kind='wb'):return root,'wb_weekly_finance_main','wb_laser_master','2026' if kind=='wb' else '2026'
def scopeargs(root,kind):return (root,'wb_weekly_finance_main','wb_laser_master','2026') if kind=='wb' else (root,'ozon_final_realization','ozon_laser_master','2026')
def batch(kind,value):return fixture.wb_files(value) if kind=='wb' else fixture.ozon_final_files(january=value,february='7')
def snap(root):return {str(x.relative_to(root)):x.read_bytes() for x in root.rglob('*') if x.is_file()}
def repair(root,kind,params,**kw):return cr.repair_current_with_witness(*scopeargs(root,kind),**params,**kw)
if a.child:
 d=json.loads(a.child.read_text());root=Path(d['root']);kind=d['kind'];params=d['params']
 if a.point=='verified_rename':
  real=os.replace
  def kill_on_rename(source,target):
   state=None
   if Path(target).parent.name=='restore-journal':state=json.loads(Path(source).read_text()).get('state')
   r=real(source,target)
   if state=='VERIFIED':os.kill(os.getpid(),signal.SIGKILL)
   return r
  os.replace=kill_on_rename
 def fault(where):
  if where==a.point:os.kill(os.getpid(),signal.SIGKILL)
 repair(root,kind,params,fault=fault);sys.exit(0)
with tempfile.TemporaryDirectory(prefix='stage3-',dir=str(Path(__file__).resolve().parent)) as td:
 base=Path(td);n=0
 def setup(kind='wb',missing=False):
  global n
  n+=1;root=base/str(n)/'archive';root.parent.mkdir();one=gs.publish_batch(*scopeargs(root,kind),batch(kind,'10'));two=gs.publish_batch(*scopeargs(root,kind),batch(kind,'20'),expected_generation=one['generation']);scope=gs._scope(*scopeargs(root,kind));pointer=scope/'CURRENT.json';old=None if missing else b'{damaged CURRENT \x00\xff}\n'
  if missing:pointer.unlink()
  else:pointer.write_bytes(old)
  params=dict(generation=two['generation'],expected_digest=two['manifest_sha256'],expected_current_sha256=ar._sha(old) if old is not None else None,witness_reference='synthetic-external-operator-claim',acknowledged=True)
  return root,kind,scope,old,one,two,params
 def preserved(scope,old):
  journals=list((scope/'restore-journal').glob('*.json'));assert len(journals)==1;record=json.loads(journals[0].read_text());assert (None if record['previous_b64'] is None else base64.b64decode(record['previous_b64']))==old;return journals[0],record
 checkpoints=['after_prepare','before_switch','after_switch','after_verify','after_journal_verified'];kills=0;exceptions=0
 for kind in ['wb','ozon']:
  for missing in [True,False]:
   for point in checkpoints:
    root,_,scope,old,one,two,params=setup(kind,missing);before=snap(scope/'generations');request=root.parent/'request.json';request.write_text(json.dumps(dict(root=str(root),kind=kind,params=params)))
    child=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--checkout',str(a.checkout),'--child',str(request),'--point',point],capture_output=True,text=True,timeout=30);assert child.returncode==-signal.SIGKILL,(point,child.stderr)
    result=repair(root,kind,params);assert result['status']=='CURRENT_VERIFIED' and result['external_witness_authenticated_by_code'] is False;preserved(scope,old);assert snap(scope/'generations')==before and gs.read_active(*scopeargs(root,kind))['generation']==two['generation'];kills+=1
 for kind in ['wb','ozon']:
  for point in checkpoints:
   root,_,scope,old,one,two,params=setup(kind);before=snap(scope/'generations')
   def fault(where):
    if where==point:raise OSError('synthetic checkpoint interruption')
   try:repair(root,kind,params,fault=fault)
   except cr.RestoreUncertainError:pass
   else:raise AssertionError('fault did not fire')
   assert repair(root,kind,params)['status']=='CURRENT_VERIFIED';preserved(scope,old);assert snap(scope/'generations')==before;exceptions+=1
 emit('DECLARED_CHECKPOINTS',sigkill_passed=kills,exception_passed=exceptions)
 # R97-1: VERIFIED journal has become visible, but its directory fsync failed.
 root,kind,scope,old,one,two,params=setup();folder=scope/'restore-journal';real=os.fsync;injected=[False]
 def fail_verified_dir(fd):
  name=os.readlink('/proc/self/fd/'+str(fd))
  docs=list(folder.glob('*.json')) if folder.exists() else []
  if name==str(folder) and docs and json.loads(docs[0].read_text()).get('state')=='VERIFIED' and not injected[0]:injected[0]=True;raise OSError(5,'VERIFIED journal parent fsync failure')
  return real(fd)
 uncertain=False
 try:
  with patch.object(os,'fsync',fail_verified_dir):repair(root,kind,params)
 except cr.RestoreUncertainError:uncertain=True
 assert injected[0] and uncertain;path,record=preserved(scope,old);trace=[]
 def trace_fd(fd):trace.append(os.readlink('/proc/self/fd/'+str(fd)));return real(fd)
 with patch.object(os,'fsync',trace_fd):retry=repair(root,kind,params)
 emit('R97_1_VERIFIED_RETRY',first_uncertain=uncertain,journal_visible_state=record['state'],retry_status=retry['status'],journal_directory_resynced=str(folder) in trace)
 # Same actual process-death window between VERIFIED rename and parent fsync.
 root,kind,scope,old,one,two,params=setup();request=root.parent/'request.json';request.write_text(json.dumps(dict(root=str(root),kind=kind,params=params)));child=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--checkout',str(a.checkout),'--child',str(request),'--point','verified_rename'],capture_output=True,text=True,timeout=30);assert child.returncode==-signal.SIGKILL,child.stderr
 trace=[]
 with patch.object(os,'fsync',trace_fd):retry=repair(root,kind,params)
 preserved(scope,old);emit('R97_1_SIGKILL_VERIFIED_RENAME',retry_status=retry['status'],journal_directory_resynced=str(scope/'restore-journal') in trace)
 # R97-2 journal schema typing: accepted equality-compatible types.
 schema_results=[]
 for phase in ['PREPARED','VERIFIED']:
  for value in [True,1.0,False,'1',None,[],{},2]:
   root,kind,scope,old,one,two,params=setup()
   if phase=='PREPARED':
    try:repair(root,kind,params,fault=lambda p:(_ for _ in ()).throw(OSError('stop')) if p=='after_prepare' else None)
    except cr.RestoreUncertainError:pass
   else:repair(root,kind,params)
   path,record=preserved(scope,old);record['schema']=value;path.write_text(json.dumps(record));before=snap(scope);blocked=False;status=None
   try:status=repair(root,kind,params)['status']
   except (ValueError,OSError):blocked=True
   schema_results.append(dict(phase=phase,value=value,blocked=blocked,status=status,unchanged=snap(scope)==before))
 emit('R97_2_SCHEMA_TYPES',cases=schema_results)
 # Independent pin/CAS/lineage/orphan/witness guards: failures before journal.
 negatives=0
 for mode in ['no_ack','blank_witness','witness_control','bad_digest','bad_generation','stale_cas','healthy_rollback','extra_generation','bad_parent','bad_pointer_symlink']:
  root,kind,scope,old,one,two,params=setup();pointer=scope/'CURRENT.json'
  if mode=='no_ack':params['acknowledged']=False
  elif mode=='blank_witness':params['witness_reference']=' '
  elif mode=='witness_control':params['witness_reference']='label\nline'
  elif mode=='bad_digest':params['expected_digest']='0'*64
  elif mode=='bad_generation':params['generation']='../bad'
  elif mode=='stale_cas':params['expected_current_sha256']='0'*64
  elif mode=='healthy_rollback':pointer.write_bytes(cr._pointer_bytes(two['generation'],two['manifest_sha256']));params.update(generation=one['generation'],expected_digest=one['manifest_sha256'],expected_current_sha256=ar._sha(pointer.read_bytes()))
  elif mode=='extra_generation':(scope/'generations'/('1'*32)).mkdir()
  elif mode=='bad_parent':(scope/'generations'/one['generation']/'data.csv').write_bytes(b'corrupt')
  elif mode=='bad_pointer_symlink':pointer.unlink();outside=root.parent/'outside';outside.write_bytes(b'SENTINEL');pointer.symlink_to(outside)
  before=snap(scope);blocked=False
  try:repair(root,kind,params)
  except (ValueError,OSError):blocked=True
  assert blocked and snap(scope)==before and not (scope/'restore-journal').exists(),mode;negatives+=1
 emit('PRECONDITIONS',passed=negatives)
 # Deliberately invented operator witness can nominate a never-committed head.
 root,kind,scope,old,one,two,params=setup();pointer=scope/'CURRENT.json';pointer.write_bytes(cr._pointer_bytes(two['generation'],two['manifest_sha256']))
 try:gs.publish_batch(*scopeargs(root,kind),batch(kind,'30'),expected_generation=two['generation'],fault=lambda p:(_ for _ in ()).throw(OSError('staged')) if p=='before_commit' else None)
 except OSError:pass
 pending=gs.reconcile(*scopeargs(root,kind))['uncommitted_generations'][0];digest=ar._sha((scope/'generations'/pending/'generation.json').read_bytes());pointer.write_bytes(old);params.update(generation=pending,expected_digest=digest,witness_reference='invented-operator-label')
 result=repair(root,kind,params);emit('DOCUMENTED_WITNESS_LIMIT',never_committed_candidate_activated=result['status']=='CURRENT_VERIFIED',external_witness_authenticated_by_code=result['external_witness_authenticated_by_code'])
 emit('COMPLETE',checkpoint_sigkills=kills,checkpoint_exceptions=exceptions,verified_retry_cases=2,schema_cases=len(schema_results),negative_cases=negatives,witness_limit_cases=1)
