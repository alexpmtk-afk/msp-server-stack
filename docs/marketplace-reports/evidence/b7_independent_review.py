"""Synthetic independent B7 review of pinned checkout. No network or live data."""
import argparse,importlib.util,json,os,signal,subprocess,sys,tempfile,threading,time
from pathlib import Path
from unittest.mock import patch

def emit(check,**kw):print(json.dumps(dict(check=check,**kw),sort_keys=True),flush=True)
def audit(event,args):
 if event in ('socket.connect','socket.getaddrinfo'):raise AssertionError('Network prohibited')
sys.addaudithook(audit)
ap=argparse.ArgumentParser();ap.add_argument('--checkout',type=Path,required=True);ap.add_argument('--child',type=Path);ap.add_argument('--dataset',default='wb');ap.add_argument('--point');ap.add_argument('--expected');ap.add_argument('--amount',default='20');a=ap.parse_args()
checkout=a.checkout.resolve();sys.path.insert(0,str(checkout))
from apps.msp_marketplace_reports import generation_store as g
from apps.msp_marketplace_reports import archive as ar
spec=importlib.util.spec_from_file_location('fixture_module',checkout/'tests/test_msp_marketplace_generations.py');fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
assert Path(g.__file__).resolve().is_relative_to(checkout)
def args(root,ds='wb'):return (root,'wb_weekly_finance_main','wb_laser_master','2026') if ds=='wb' else (root,'ozon_final_realization','ozon_laser_master','2026')
def files(ds='wb',amount='10'):return fixture.wb_files(amount) if ds=='wb' else fixture.ozon_final_files(january=amount,february='7')
def scope(root,ds='wb'):return g._scope(*args(root,ds))
def snapshot(root):return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
if a.child:
 def kill(point):
  if point==a.point:os.kill(os.getpid(),signal.SIGKILL)
 g.publish_batch(*args(a.child,a.dataset),files(a.dataset,a.amount),expected_generation=a.expected,fault=kill)
 sys.exit(0)
with tempfile.TemporaryDirectory(prefix='b7-fixtures-',dir=str(Path(__file__).resolve().parent)) as temp:
 work=Path(temp);index=0
 def new():
  global index
  index+=1;return work/str(index)
 counts={'exception_points':0,'sigkill_points':0,'io_failures':0,'validation_negative':0}
 for kind in ['exception','sigkill']:
  for ds in ['wb','ozon']:
   points=['after_stage_dir',*['after_file:'+f for f in sorted(files(ds))],'after_descriptor','before_commit','after_commit']
   for initial in [True,False]:
    for point in points:
     root=new();prev=None
     if not initial:prev=g.publish_batch(*args(root,ds),files(ds))['generation']
     prior=snapshot(scope(root,ds)/'generations'/prev) if prev else {}
     if kind=='exception':
      def fail(where):
       if where==point:raise OSError('synthetic interruption')
      try:g.publish_batch(*args(root,ds),files(ds,'20'),expected_generation=prev,fault=fail)
      except (OSError,g.CommitUncertainError):pass
      else:raise AssertionError('fault not reached')
     else:
      cmd=[sys.executable,'-B',str(Path(__file__).resolve()),'--checkout',str(checkout),'--child',str(root),'--dataset',ds,'--point',point]
      if prev:cmd+=['--expected',prev]
      child=subprocess.run(cmd,capture_output=True,text=True,timeout=25)
      assert child.returncode==-signal.SIGKILL,(point,child.returncode,child.stderr)
     active=g.read_active(*args(root,ds));state=g.reconcile(*args(root,ds))
     if point=='after_commit':assert active['files']==files(ds,'20') and state['status']=='ACTIVE_VERIFIED'
     else:
      assert (active is None) if initial else (active['generation']==prev and active['files']==files(ds))
      assert state['status']==('PENDING' if initial else 'RECOVERY_REQUIRED')
     if prev:assert snapshot(scope(root,ds)/'generations'/prev)==prior
     counts['exception_points' if kind=='exception' else 'sigkill_points']+=1
 emit('ALL_CHECKPOINT_CRASHES',**counts)
 # Every os.replace/os.fsync point encountered in a normal update.
 for opname in ['replace','fsync']:
  root=new();first=g.publish_batch(*args(root),files())['generation'];original=getattr(os,opname);trace=[]
  def record(*aa,**kk):trace.append(aa);return original(*aa,**kk)
  with patch.object(os,opname,record):g.publish_batch(*args(root),files(amount='20'),expected_generation=first)
  for position in range(len(trace)):
   root=new();prev=g.publish_batch(*args(root),files())['generation'];n=[0]
   def failing(*aa,**kk):
    i=n[0];n[0]+=1
    if i==position:raise OSError(28 if opname=='replace' else 5,'synthetic IO failure')
    return original(*aa,**kk)
   raised=None
   try:
    with patch.object(os,opname,failing):g.publish_batch(*args(root),files(amount='20'),expected_generation=prev)
   except (OSError,g.CommitUncertainError) as e:raised=type(e).__name__
   assert raised
   active=g.read_active(*args(root));assert active['files'] in (files(),files(amount='20'))
   assert g.read_generation(*args(root),prev)['files']==files()
   counts['io_failures']+=1
  emit('IO_OPERATION_FAILURES',operation=opname,points=len(trace))
 # Concurrent processes: same expected parent, only one changing writer wins.
 root=new();prev=g.publish_batch(*args(root),files())['generation'];children=[]
 for amount in ['20','30']:
  children.append(subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'--checkout',str(checkout),'--child',str(root),'--amount',amount,'--expected',prev],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True))
 results=[]
 for child in children:
  out,err=child.communicate(timeout=25);results.append(child.returncode)
 assert sorted(results)==[0,1] and g.read_active(*args(root))['files'] in (files(amount='20'),files(amount='30'))
 emit('MULTIPROCESS_STALE_WRITER',returncodes=results,status='PASS')
 # Readers race pointer switch; one read returns only complete old or new bytes.
 root=new();prev=g.publish_batch(*args(root,'ozon'),files('ozon'))['generation'];start=threading.Event();proceed=threading.Event();reader_values=[];errors=[]
 def writer():
  try:
   def hook(where):
    if where=='before_commit':start.set();assert proceed.wait(20)
   g.publish_batch(*args(root,'ozon'),files('ozon','20'),expected_generation=prev,fault=hook)
  except BaseException as e:errors.append(repr(e))
 t=threading.Thread(target=writer);t.start();assert start.wait(20)
 for i in range(20):reader_values.append(g.read_active(*args(root,'ozon'))['files'])
 proceed.set()
 for i in range(20):reader_values.append(g.read_active(*args(root,'ozon'))['files'])
 t.join(20);assert not t.is_alive() and not errors
 assert all(v in (files('ozon'),files('ozon','20')) for v in reader_values)
 emit('CONCURRENT_READER',reads=len(reader_values),status='PASS')
 # Candidate fully formed but never published is accepted by public read_generation.
 root=new();prev=g.publish_batch(*args(root),files())['generation']
 try:g.publish_batch(*args(root),files(amount='20'),expected_generation=prev,fault=lambda p:(_ for _ in ()).throw(OSError('stop')) if p=='before_commit' else None)
 except OSError:pass
 rec=g.reconcile(*args(root));pending=rec['uncommitted_generations'][0];candidate=g.read_generation(*args(root),pending)
 emit('G1_UNCOMMITTED_PUBLIC_READER',reconcile_status=rec['status'],candidate_accepted=candidate['files']==files(amount='20'),current_still_old=g.read_active(*args(root))['generation']==prev)
 # Loss of only commit receipt mislabels known prior committed generations.
 root=new();one=g.publish_batch(*args(root),files())['generation'];two=g.publish_batch(*args(root),files(amount='20'),expected_generation=one)['generation'];(scope(root)/'CURRENT.json').unlink();rec=g.reconcile(*args(root))
 emit('G2_MISSING_POINTER_CLASSIFICATION',reconcile=rec,known_committed_ids=[one,two])
 # Historical pinned descriptor lacks a digest anchored by its child.
 root=new();one=g.publish_batch(*args(root),files())['generation'];two=g.publish_batch(*args(root),files(amount='20'),expected_generation=one)['generation'];gen=scope(root)/'generations'/one;replacement=files(amount='99')
 for name,raw in replacement.items():(gen/name).write_bytes(raw)
 desc=g._descriptor('2026',one,None,replacement);(gen/'generation.json').write_text(json.dumps(desc))
 emit('G3_UNANCHORED_PARENT',old_pinned_changed=g.read_generation(*args(root),one)['files']==replacement,current_is_new=g.read_active(*args(root))['generation']==two,reconcile=g.reconcile(*args(root)))
 # Precise durability coverage of newly-created directories.
 root=new();syncs=[];original=os.fsync
 def trace_fsync(fd):
  syncs.append(os.readlink('/proc/self/fd/'+str(fd)));return original(fd)
 with patch.object(os,'fsync',trace_fsync):g.publish_batch(*args(root),files())
 required=[root.parent,root,root/'.b7-generations',root/'.b7-generations/wb_weekly_finance_main',root/'.b7-generations/wb_weekly_finance_main/wb_laser_master']
 emit('G4_FIRST_SCOPE_FSYNC',missing_parent_directory_fsync=[str(p.relative_to(work)) if p.is_relative_to(work) else str(p) for p in required if str(p) not in syncs],synced_paths=[str(Path(p).relative_to(root)) for p in syncs if Path(p).is_relative_to(root)])
 # Invalid file names, links, malformed control documents fail closed.
 for badname in ['../escape.csv','/abs.csv','monthly/../escape.csv','monthly/2026-13.csv','data.csv/../evil','data.csv.meta.json/evil']:
  root=new();batch=files();batch[badname]=b'bad'
  try:g.publish_batch(*args(root),batch)
  except ValueError:counts['validation_negative']+=1
  else:raise AssertionError(badname)
  assert not root.exists()
 for target in ['CURRENT.json','generation.json','data.csv.meta.json']:
  for kind in ['duplicate','bool','float','badjson','nan']:
   root=new();one=g.publish_batch(*args(root),files())['generation'];s=scope(root);p=s/'CURRENT.json' if target=='CURRENT.json' else s/'generations'/one/target
   raw=p.read_text();d=json.loads(raw)
   if kind=='duplicate':raw='{"schema":true,'+raw.lstrip()[1:]
   elif kind=='badjson':raw='{'
   else:d['schema']={'bool':True,'float':1.0,'nan':float('nan')}[kind];raw=json.dumps(d)
   p.write_text(raw);before=snapshot(root)
   try:g.read_active(*args(root))
   except ValueError:counts['validation_negative']+=1
   else:raise AssertionError([target,kind])
   assert g.reconcile(*args(root))['status']=='RECOVERY_REQUIRED' and snapshot(root)==before
 emit('VALIDATION_NEGATIVE',passed=counts['validation_negative'])
 # Root symlink is resolved away rather than rejected; document policy ambiguity.
 outside=new();outside.mkdir();root=new();root.symlink_to(outside,target_is_directory=True);g.publish_batch(*args(root),files())
 emit('ROOT_SYMLINK_POLICY',accepted=True,outside_contains_store=(outside/'.b7-generations').exists())
 emit('COMPLETE',**counts)
