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
 emit('COMPLETE',core_cases=4)
