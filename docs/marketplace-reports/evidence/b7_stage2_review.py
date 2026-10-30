"""Independent offline stage-two review: all data synthetic, sockets/DNS denied."""
import argparse,csv,importlib.util,json,os,signal,shutil,subprocess,sys,tempfile,threading
from pathlib import Path
from unittest.mock import patch

def audit(event,args):
 if event in ('socket.connect','socket.getaddrinfo'):raise AssertionError('Network prohibited')
sys.addaudithook(audit)
p=argparse.ArgumentParser();p.add_argument('--checkout',type=Path,required=True);p.add_argument('--child',choices=['import','quarantine']);p.add_argument('--root',type=Path);p.add_argument('--source',type=Path);p.add_argument('--dataset',default='wb_weekly_finance_main');p.add_argument('--period',default='2026');p.add_argument('--receipt',type=Path);p.add_argument('--point');a=p.parse_args();sys.path.insert(0,str(a.checkout.resolve()))
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
if a.child=='import':
 original=va.publish_batch
 def gate(*aa,**kk):print('READY',flush=True);sys.stdin.readline();return original(*aa,**kk)
 va.publish_batch=gate
 try:print(json.dumps(va.import_csv_versioned(*args(a.root,a.dataset,a.period),a.source)));sys.exit(0)
 except gs.GenerationError as e:print(json.dumps({'error':str(e)}));sys.exit(2)
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
with tempfile.TemporaryDirectory(prefix='stage2-',dir=str(Path(__file__).resolve().parent)) as td:
 base=Path(td);n=0
 def new():
  global n
  n+=1;p=base/str(n);p.mkdir();return p/'archive'
 controls=0
 for ds in ar.DATASETS:
  root=new();period='2026' if ds.startswith('wb') else '2026-01';source=src(root.parent,ds,period);r=va.import_csv_versioned(*args(root,ds,period),source);raw,pin=va.read_csv_versioned(*args(root,ds,period));old=snap(root);same=va.import_csv_versioned(*args(root,ds,period),source);assert not same['changed'] and old==snap(root)
  source=src(root.parent,ds,period,ident='2',amount='20');va.import_csv_versioned(*args(root,ds,period),source);pinned,_=va.read_csv_versioned(*args(root,ds,period),pinned_generation=pin['generation'],expected_digest=pin['manifest_sha256']);assert pinned==raw and va.verify_versioned_scope(*args(root,ds,period))['ok']
  assert not (root/'База данных').exists();controls+=1
 emit('DATASET_CONTROLS',passed=controls)
 # Static guard for CSV, metadata, and dangling links.
 legacy=[]
 for kind in ['csv','meta','csv_link','meta_dangling_link']:
  root=new();source=src(root.parent);path=ar._location(*args(root));path.parent.mkdir(parents=True)
  target=path if kind in ('csv','csv_link') else path.with_name(path.name+'.meta.json')
  if 'link' in kind:target.symlink_to(root.parent/'missing')
  else:target.write_bytes(b'legacy')
  blocked=False
  try:va.import_csv_versioned(*args(root),source)
  except ValueError:blocked=True
  legacy.append({'kind':kind,'blocked':blocked,'link_preserved':target.is_symlink() if 'link' in kind else None})
 emit('LEGACY_STATIC_GUARD',cases=legacy)
 # Normal sequential use of both public importers in the same scope.
 root=new();source=src(root.parent);v=va.import_csv_versioned(*args(root),source);other=src(root.parent,amount='99',name='legacy.csv');ar.import_csv(*args(root),other)
 emit('R96_2_SEQUENTIAL_MIX',legacy_verify=ar.verify(root)['ok'],versioned_verify=va.verify_versioned_scope(*args(root))['ok'],different_bytes=ar._location(*args(root)).read_bytes()!=va.read_csv_versioned(*args(root))[0])
 # Deterministic legacy commit after second guard, before versioned CAS.
 root=new();source=src(root.parent);legacy_source=src(root.parent,amount='99',name='legacy.csv');original=va.publish_batch
 def race(*aa,**kk):ar.import_csv(*args(root),legacy_source);return original(*aa,**kk)
 with patch.object(va,'publish_batch',race):r=va.import_csv_versioned(*args(root),source)
 emit('R96_2_LEGACY_GUARD_RACE',versioned_status=r['status'],legacy_exists=ar._location(*args(root)).exists(),legacy_verify=ar.verify(root)['ok'])
 # Real importer processes build on same parent; explicit retry preserves all.
 for ds in ['wb_weekly_finance_main','ozon_final_realization']:
  root=new();period='2026' if ds.startswith('wb') else '2026-01';va.import_csv_versioned(*args(root,ds,period),src(root.parent,ds,period));children=[];sources=[];periods=[]
  for i in [2,3]:
   pr='2026' if ds.startswith('wb') else '2026-0'+str(i);source=src(root.parent,ds,pr,ident=str(i),amount=str(i*10),name='child'+str(i)+'.csv');sources.append(source);periods.append(pr)
   children.append(subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'--checkout',str(a.checkout),'--child','import','--root',str(root),'--dataset',ds,'--period',pr,'--source',str(source)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True))
  for c in children:assert c.stdout.readline().strip()=='READY'
  for c in children:c.stdin.write('go\n');c.stdin.flush()
  codes=[]
  for c in children:out,err=c.communicate(timeout=30);codes.append(c.returncode);assert not err,err
  assert sorted(codes)==[0,2],codes
  loser=codes.index(2);va.import_csv_versioned(*args(root,ds,periods[loser]),sources[loser]);s=gs.read_active(*args(root,ds,'2026'));csvname='data.csv' if ds.startswith('wb') else 'annual.csv';assert len(ar._rows(s['files'][csvname],ar.DATASETS[ds][1])[1])==3
  emit('CONCURRENT_IMPORTERS',dataset=ds,status='PASS',codes=codes,rows_after_explicit_retry=3)
 # New defect: source-directory fsync after rename fails; retry never retries it.
 root=new();receipt,scope,candidate=setup(root);saved=snap(scope/'generations'/candidate);original_sync=gr._sync_dir;failed=[False]
 def fail_source_parent(path):
  if Path(path)==scope/'generations' and not failed[0]:failed[0]=True;raise OSError(5,'synthetic source parent fsync')
  return original_sync(path)
 uncertain=False
 try:
  with patch.object(gr,'_sync_dir',fail_source_parent):quarantine(root,receipt,[candidate])
 except gr.RecoveryUncertainError:uncertain=True
 trace=[];real=os.fsync
 def trace_fd(fd):trace.append(os.readlink('/proc/self/fd/'+str(fd)));return real(fd)
 with patch.object(os,'fsync',trace_fd):retry=quarantine(root,receipt,[candidate])
 assert snap(scope/'evidence'/candidate)==saved and gs.read_active(*args(root))['generation']==receipt['generation']
 emit('R96_1_RETRY_SKIPS_SOURCE_PARENT_SYNC',first_uncertain=uncertain,retry_status=retry['status'],source_parent_synced_on_retry=str(scope/'generations') in trace,evidence_bytes_preserved=True)
 # Real SIGKILL before/after rename/sync. Bytes retained, retry progress inspected.
 for point in ['before_evidence_rename','after_rename','before_source_sync','after_evidence_fsync']:
  root=new();receipt,scope,candidate=setup(root);saved=snap(scope/'generations'/candidate);request=root.parent/'request.json';request.write_text(json.dumps({'receipt':receipt,'candidate':candidate}));p=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--checkout',str(a.checkout),'--child','quarantine','--root',str(root),'--receipt',str(request),'--point',point],capture_output=True,text=True,timeout=30);assert p.returncode==-signal.SIGKILL,(point,p.stderr)
  trace=[]
  with patch.object(os,'fsync',trace_fd):r=quarantine(root,receipt,[candidate])
  assert snap(scope/'evidence'/candidate)==saved and gs.read_active(*args(root))['generation']==receipt['generation']
  emit('QUARANTINE_SIGKILL',point=point,status=r['status'],source_parent_synced_on_retry=str(scope/'generations') in trace,bytes_preserved=True)
 # Validation of whole batch happens too late: later collision mutates earlier entry.
 root=new();receipt,scope,candidate=setup(root);old=scope/'generations'/candidate;first='1'*32;second='2'*32;old.rename(old.with_name(first));shutil.copytree(old.with_name(first),old.with_name(second));(scope/'evidence'/second).mkdir(parents=True);before=snap(scope)
 error=None
 try:quarantine(root,receipt,[first,second])
 except Exception as e:error=type(e).__name__+':'+str(e)
 emit('R96_3_LATE_BATCH_VALIDATION',error=error,earlier_candidate_already_moved=(scope/'evidence'/first).exists(),all_files_unchanged=snap(scope)==before)
 # A previously committed generation outside rolled-back CURRENT is accepted.
 root=new();source=src(root.parent);one=va.import_csv_versioned(*args(root),source);scope=gs._scope(*args(root));pointer=(scope/'CURRENT.json').read_bytes();two=va.import_csv_versioned(*args(root),src(root.parent,ident='2'));(scope/'CURRENT.json').write_bytes(pointer)
 result=quarantine(root,one,[two['generation']]);emit('DOCUMENTED_ROLLBACK_LIMIT',known_committed_moved=result['status']=='EVIDENCE_RETAINED',operator_acknowledged=True,bytes_not_deleted=(scope/'evidence'/two['generation']).exists())
 negatives=0
 for mode in ['no_ack','wrong_pin','wrong_expected','committed_candidate','unlisted','duplicate','bad_id','missing_current','corrupt_current','evidence_link','target_file']:
  root=new();receipt,scope,candidate=setup(root);params=dict(expected_generation=receipt['generation'],expected_digest=receipt['manifest_sha256'],candidates=[candidate],acknowledged=True)
  if mode=='no_ack':params['acknowledged']=False
  elif mode=='wrong_pin':params['expected_digest']='0'*64
  elif mode=='wrong_expected':params['expected_generation']='0'*32
  elif mode=='committed_candidate':params['candidates']=[receipt['generation']]
  elif mode=='unlisted':params['candidates']=['0'*32]
  elif mode=='duplicate':params['candidates']=[candidate,candidate]
  elif mode=='bad_id':params['candidates']=['../escape']
  elif mode=='missing_current':(scope/'CURRENT.json').unlink()
  elif mode=='corrupt_current':(scope/'CURRENT.json').write_text('{')
  elif mode=='evidence_link':(scope/'evidence').symlink_to(root.parent/'outside',target_is_directory=True)
  elif mode=='target_file':
   (scope/'evidence').mkdir();(scope/'evidence'/candidate).write_bytes(b'not-a-directory')
  before=snap(root);blocked=False
  try:gr.quarantine_uncommitted(*args(root),**params)
  except (ValueError,OSError):blocked=True
  assert blocked and snap(root)==before,mode
  negatives+=1
 emit('RECOVERY_PRECONDITIONS',passed=negatives)
 emit('COMPLETE',dataset_controls=controls,legacy_static_cases=len(legacy),concurrent_importer_cases=2,quarantine_sigkill_cases=4,recovery_negative_cases=negatives)
