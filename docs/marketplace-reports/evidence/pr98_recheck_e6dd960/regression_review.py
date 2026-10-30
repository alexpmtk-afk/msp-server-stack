"""Independent offline stage-two review: all data synthetic, sockets/DNS denied."""
import argparse,contextlib,select,csv,importlib.util,json,os,signal,shutil,subprocess,sys,tempfile,threading
from pathlib import Path
from unittest.mock import patch

def audit(event,args):
 if event in ('socket.connect','socket.getaddrinfo'):raise AssertionError('Network prohibited')
sys.addaudithook(audit)
p=argparse.ArgumentParser();p.add_argument('--checkout',type=Path,required=True);p.add_argument('--child',choices=['writer','quarantine']);p.add_argument('--root',type=Path);p.add_argument('--source',type=Path);p.add_argument('--dataset',default='wb_weekly_finance_main');p.add_argument('--period',default='2026');p.add_argument('--receipt',type=Path);p.add_argument('--mode',choices=['legacy','versioned'],default='versioned');p.add_argument('--point');a=p.parse_args();sys.path.insert(0,str(a.checkout.resolve()))
from apps.msp_marketplace_reports import archive as ar,generation_store as gs,versioned_archive as va,generation_recovery as gr
assert Path(va.__file__).resolve().is_relative_to(a.checkout.resolve())
def args(root,ds='wb_weekly_finance_main',period='2026'):return root,ds,'wb_laser_master' if ds.startswith('wb') else 'ozon_laser_master',period
def snap(root):return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
def emit(check,**kw):print(json.dumps(dict(check=check,**kw),sort_keys=True),flush=True)
def src(base,ds='wb_weekly_finance_main',period='2026',ident='1',amount='10',name='source.csv'):
 if ds.startswith('wb'):fields=['reportId','rrdId','reportType','dateTo','amount'];row=[ident,ident,'1' if ds.endswith('main') else '2','2026-10-11',amount]
 elif ds=='ozon_final_realization':fields=['report_year','report_month','row_number','amount'];row=[period[:4],period,ident,amount]
 else:fields=['accrual_id' if ds.endswith('accruals') else 'posting_number','amount'];row=[ident,amount]
 path=base/name;path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('w',newline='',encoding='utf-8-sig') as f:w=csv.writer(f,delimiter=';');w.writerow(fields);w.writerow(row)
 return path

def setup(root):
 source=src(root.parent);receipt=va.import_csv_versioned(*args(root),source);active=gs.read_active(*args(root));batch=dict(active['files']);raw=batch['data.csv'].replace(b';10\n',b';20\n');batch['data.csv']=raw;batch['data.csv.meta.json']=json.dumps(ar._metadata(raw,1,*args(root)[1:])).encode()
 try:gs.publish_batch(*args(root),batch,expected_generation=receipt['generation'],fault=lambda p:(_ for _ in ()).throw(OSError('stop')) if p=='before_commit' else None)
 except OSError:pass
 scope=gs._scope(*args(root));candidate=gs.reconcile(*args(root))['uncommitted_generations'][0];return receipt,scope,candidate

def quarantine(root,receipt,candidates,**kw):return gr.quarantine_uncommitted(*args(root),expected_generation=receipt['generation'],expected_digest=receipt['manifest_sha256'],candidates=candidates,acknowledged=True,**kw)
if a.child=='writer':
 original=ar._lock
 @contextlib.contextmanager
 def gate(*aa,**kk):
  print('ATTEMPT',flush=True)
  with original(*aa,**kk):
   print('HELD',flush=True);sys.stdin.readline();yield
 target=ar if a.mode=='legacy' else va
 target._lock=gate
 try:
  fn=ar.import_csv if a.mode=='legacy' else va.import_csv_versioned
  print(json.dumps(fn(*args(a.root,a.dataset,a.period),a.source)));sys.exit(0)
 except (ValueError,OSError) as e:print(json.dumps({'error':str(e)}));sys.exit(2)
if a.child=='quarantine':
 d=json.loads(a.receipt.read_text());receipt=d['receipt'];candidate=d['candidate'];scope=gs._scope(*args(a.root));original_replace=os.replace;original_sync=gr._sync_dir
 def replaced(source,target):
  r=original_replace(source,target)
  if a.point=='after_rename':os.kill(os.getpid(),signal.SIGKILL)
  return r
 def syncing(path):
  if a.point=='before_source_sync' and Path(path)==scope/'generations':os.kill(os.getpid(),signal.SIGKILL)
  return original_sync(path)
 gr.os.replace=replaced;gr._sync_dir=syncing
 def hook(point):
  if a.point in ('before_evidence_rename','after_evidence_fsync') and point.startswith(a.point):os.kill(os.getpid(),signal.SIGKILL)
 quarantine(a.root,receipt,[candidate],fault=hook);sys.exit(0)
with tempfile.TemporaryDirectory(prefix='repeat-',dir=str(Path(__file__).resolve().parent)) as td:
 base=Path(td);n=0
 def new():
  global n
  n+=1;p=base/str(n);p.mkdir();return p/'archive'
 sync_cases=0
 for which in ['source','target']:
  root=new();receipt,scope,candidate=setup(root);saved=snap(scope/'generations'/candidate);original=gr._sync_dir;failedpath=scope/('generations' if which=='source' else 'evidence')
  def fail(path):
   if Path(path)==failedpath:raise OSError(5,'synthetic fsync')
   return original(path)
  for attempt in range(2):
   uncertain=None
   try:
    with patch.object(gr,'_sync_dir',fail):quarantine(root,receipt,[candidate])
   except gr.RecoveryUncertainError as e:uncertain=e
   assert uncertain and (scope/'evidence'/candidate).exists()
  trace=[];real=os.fsync
  def auditfd(fd):trace.append(os.readlink('/proc/self/fd/'+str(fd)));return real(fd)
  with patch.object(os,'fsync',auditfd):r=quarantine(root,receipt,[candidate])
  assert str(scope/'generations') in trace and str(scope/'evidence') in trace
  assert snap(scope/'evidence'/candidate)==saved and gs.read_active(*args(root))['generation']==receipt['generation']
  emit('R96_1_SYNC_RETRY',target=which,status=r['status'],both_synced=True,repeated_failure_uncertain=True);sync_cases+=1
 kill_cases=0
 for point in ['before_evidence_rename','after_rename','before_source_sync','after_evidence_fsync']:
  root=new();receipt,scope,candidate=setup(root);saved=snap(scope/'generations'/candidate);request=root.parent/'request.json';request.write_text(json.dumps({'receipt':receipt,'candidate':candidate}));p=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--checkout',str(a.checkout),'--child','quarantine','--root',str(root),'--receipt',str(request),'--point',point],capture_output=True,text=True,timeout=30);assert p.returncode==-signal.SIGKILL,(point,p.stderr)
  trace=[]
  with patch.object(os,'fsync',auditfd):r=quarantine(root,receipt,[candidate])
  assert str(scope/'generations') in trace and str(scope/'evidence') in trace and snap(scope/'evidence'/candidate)==saved
  assert gs.read_active(*args(root))['generation']==receipt['generation']
  emit('R96_1_SIGKILL',point=point,both_synced=True,bytes_preserved=True);kill_cases+=1
 sequential=0;static=0;mixed=0;controls=0
 for ds in ar.DATASETS:
  period='2026' if ds.startswith('wb') else '2026-01'
  for first in ['legacy','versioned']:
   root=new();source=src(root.parent,ds,period);fn=ar.import_csv if first=='legacy' else va.import_csv_versioned;second=va.import_csv_versioned if first=='legacy' else ar.import_csv
   r=fn(*args(root,ds,period),source);old=snap(root);blocked=False
   try:second(*args(root,ds,period),source)
   except ValueError:blocked=True
   assert blocked and snap(root)==old
   sequential+=1
  for kind in ['csv','meta','csv_link','meta_link']:
   root=new();source=src(root.parent,ds,period);file=ar._location(*args(root,ds,period));file.parent.mkdir(parents=True);target=file if kind.startswith('csv') else file.with_name(file.name+'.meta.json')
   if kind.endswith('link'):target.symlink_to(root.parent/'missing')
   else:target.write_bytes(b'legacy')
   blocked=False
   try:va.import_csv_versioned(*args(root,ds,period),source)
   except ValueError:blocked=True
   assert blocked and not (root/'.b7-generations').exists();static+=1
  # Deliberately injected mixed state: both verification entrypoints reject it.
  root=new();source=src(root.parent,ds,period);va.import_csv_versioned(*args(root,ds,period),source);file=ar._location(*args(root,ds,period));file.parent.mkdir(parents=True);raw=source.read_bytes();file.write_bytes(raw);file.with_name(file.name+'.meta.json').write_text(json.dumps(ar._metadata(raw,1,*args(root,ds,period)[1:])))
  assert not ar.verify(root)['ok'] and not va.verify_versioned_scope(*args(root,ds,period))['ok'];mixed+=1
  root=new();source=src(root.parent,ds,period);r=va.import_csv_versioned(*args(root,ds,period),source);old=snap(root);assert not va.import_csv_versioned(*args(root,ds,period),source)['changed'] and snap(root)==old
  raw,pin=va.read_csv_versioned(*args(root,ds,period));va.import_csv_versioned(*args(root,ds,period),src(root.parent,ds,period,ident='2',amount='20'));assert va.read_csv_versioned(*args(root,ds,period),pinned_generation=pin['generation'],expected_digest=pin['manifest_sha256'])[0]==raw
  assert va.verify_versioned_scope(*args(root,ds,period))['ok'];controls+=1
 emit('R96_2_SEQUENTIAL_STATIC_MIXED',sequential_passed=sequential,static_passed=static,mixed_detection_passed=mixed,normal_controls=controls)
 # Real mixed-writer races. Pause first writer immediately after common flock.
 def start(root,ds,period,mode,source):
  return subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'--checkout',str(a.checkout),'--child','writer','--root',str(root),'--dataset',ds,'--period',period,'--mode',mode,'--source',str(source)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 races=0
 for ds in ['wb_weekly_finance_main','ozon_current_orders_fbo','ozon_final_realization']:
  period='2026' if ds.startswith('wb') else '2026-01'
  for first in ['legacy','versioned']:
   root=new();source=src(root.parent,ds,period);other='versioned' if first=='legacy' else 'legacy';one=start(root,ds,period,first,source);assert one.stdout.readline().strip()=='ATTEMPT' and one.stdout.readline().strip()=='HELD'
   two=start(root,ds,period,other,source);assert two.stdout.readline().strip()=='ATTEMPT';assert not select.select([two.stdout],[],[],0.15)[0],'second writer bypassed lock'
   one.stdin.write('go\n');one.stdin.flush();o,e=one.communicate(timeout=30);assert one.returncode==0,(o,e)
   assert two.stdout.readline().strip()=='HELD';two.stdin.write('go\n');two.stdin.flush();o,e=two.communicate(timeout=30);assert two.returncode==2,(o,e)
   if first=='legacy':assert ar.verify(root)['ok'] and not (root/'.b7-generations').exists()
   else:assert va.verify_versioned_scope(*args(root,ds,period))['ok'] and not ar._location(*args(root,ds,period)).exists()
   races+=1
 emit('R96_2_MULTIPROCESS_RACES',passed=races)
 # Two cooperative versioned writers now serialize, both changes survive.
 parallel=0
 for ds in ['wb_weekly_finance_main','ozon_final_realization']:
  period='2026' if ds.startswith('wb') else '2026-01';root=new();va.import_csv_versioned(*args(root,ds,period),src(root.parent,ds,period));p2='2026' if ds.startswith('wb') else '2026-02';p3='2026' if ds.startswith('wb') else '2026-03'
  one=start(root,ds,p2,'versioned',src(root.parent,ds,p2,ident='2',name='two.csv'));assert one.stdout.readline().strip()=='ATTEMPT' and one.stdout.readline().strip()=='HELD';two=start(root,ds,p3,'versioned',src(root.parent,ds,p3,ident='3',name='three.csv'));assert two.stdout.readline().strip()=='ATTEMPT';assert not select.select([two.stdout],[],[],0.15)[0]
  one.stdin.write('go\n');one.stdin.flush();o,e=one.communicate(timeout=30);assert one.returncode==0,(o,e)
  assert two.stdout.readline().strip()=='HELD';two.stdin.write('go\n');two.stdin.flush();o,e=two.communicate(timeout=30);assert two.returncode==0,(o,e)
  active=gs.read_active(*args(root,ds,'2026'));name='data.csv' if ds.startswith('wb') else 'annual.csv';assert len(ar._rows(active['files'][name],ar.DATASETS[ds][1])[1])==3;parallel+=1
 emit('VERSIONED_IMPORTERS_SERIALIZED',passed=parallel)
 # Full-plan rejection is mutation-free, including a later candidate collision.
 validation=0;partial=0
 for kind in ['target_file','both_directories','missing_candidate']:
  root=new();receipt,scope,candidate=setup(root);original=scope/'generations'/candidate;first='1'*32;second='2'*32;original.rename(original.with_name(first))
  if kind!='missing_candidate':shutil.copytree(original.with_name(first),original.with_name(second))
  if kind=='target_file':(scope/'evidence').mkdir();(scope/'evidence'/second).write_bytes(b'bad')
  elif kind=='both_directories':(scope/'evidence'/second).mkdir(parents=True)
  before=snap(scope);blocked=False
  try:quarantine(root,receipt,[first,second])
  except gr.GenerationError:blocked=True
  assert blocked and snap(scope)==before and not (scope/'evidence'/first).exists();validation+=1
 for kind in ['before_second','second_rename_error','second_rename_after_effect']:
  root=new();receipt,scope,candidate=setup(root);original=scope/'generations'/candidate;first='1'*32;second='2'*32;original.rename(original.with_name(first));shutil.copytree(original.with_name(first),original.with_name(second));saved={c:snap(scope/'generations'/c) for c in [first,second]};realreplace=os.replace
  def replace(source,target):
   if Path(source).name==second and kind=='second_rename_error':raise OSError('second rename')
   r=realreplace(source,target)
   if Path(source).name==second and kind=='second_rename_after_effect':raise OSError('lost response to rename')
   return r
  def hook(point):
   if kind=='before_second' and point=='before_evidence_rename:'+second:raise OSError('before second')
  error=None
  try:
   with patch.object(os,'replace',replace):quarantine(root,receipt,[first,second],fault=hook)
  except gr.RecoveryUncertainError as e:error=e
  assert error is not None and error.moved_in_attempt==(first,) and error.candidate==second
  r=quarantine(root,receipt,[first,second]);assert r['status']=='EVIDENCE_RETAINED'
  for c in [first,second]:assert snap(scope/'evidence'/c)==saved[c]
  assert gs.read_active(*args(root))['generation']==receipt['generation'];partial+=1
 emit('R96_3_BATCH_VALIDATION_AND_PARTIAL',preflight_passed=validation,partial_retry_passed=partial)
 emit('COMPLETE',sync_retry_cases=sync_cases,sigkill_cases=kill_cases,sequential_cases=sequential,static_cases=static,mixed_cases=mixed,controls=controls,race_cases=races,versioned_parallel=parallel,preflight_cases=validation,partial_cases=partial)
