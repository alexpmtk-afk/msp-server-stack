"""Pinned independent PR99 probes: synthetic files, no credentials/network/Redis."""
import argparse,csv,io,json,os,signal,subprocess,sys,tempfile
from pathlib import Path
from unittest.mock import patch
p=argparse.ArgumentParser();p.add_argument('--checkout',type=Path,required=True);p.add_argument('--child',type=Path);a=p.parse_args();sys.path.insert(0,str(a.checkout.resolve()))
def audit(event,args):
 if event in ('socket.connect','socket.getaddrinfo'):raise AssertionError('Network forbidden')
sys.addaudithook(audit)
from apps.msp_marketplace_reports import wb_worker_adapter as w,archive as ar,generation_store as gs,versioned_archive as va
assert Path(w.__file__).resolve().is_relative_to(a.checkout.resolve())
def emit(check,**kw):print(json.dumps(dict(check=check,**kw),sort_keys=True),flush=True)
def row(kind,n=10):return dict(reportId=555,reportType=kind,rrdId=n,dateFrom='2026-10-19',dateTo='2026-10-25',amount='10')
def call(r,k,send,**kw):return w.run_one_step(r,'wb_laser_master',2026,555,k,send,**kw)
def stage(r,k):return w._dir(r,'wb_laser_master',2026,555,k)
def args(r,k):return r,w._dataset(k),'wb_laser_master','2026'
def setup(r,k):r.parent.mkdir(parents=True);call(r,k,lambda req:(200,[row(k)]));return call(r,k,lambda req:(204,None))
def snap(r):return {str(x.relative_to(r)):x.read_bytes() for x in r.rglob('*') if x.is_file()}
if a.child:
 real=os.replace
 def kill(src,dst):
  result=real(src,dst)
  if Path(dst).name=='coverage.json':os.kill(os.getpid(),signal.SIGKILL)
  return result
 os.replace=kill;call(a.child,1,lambda req:(204,None));raise AssertionError('kill not reached')
with tempfile.TemporaryDirectory(prefix='pr99-',dir=Path(__file__).parent) as td:
 base=Path(td)
 for kind in [1,2]:
  r=base/('bind-'+str(kind))/'archive';first=setup(r,kind);active=gs.read_active(*args(r,kind));files=dict(active['files']);fields,mapping=ar._rows(files['data.csv'],('reportId','rrdId'))
  for v in mapping.values():v['amount']='99'
  raw=ar._encode(fields,mapping);files['data.csv']=raw;files['data.csv.meta.json']=json.dumps(ar._metadata(raw,len(mapping),*args(r,kind)[1:]),sort_keys=True).encode();second=gs.publish_batch(*args(r,kind),files,expected_generation=active['generation'])
  coverage=stage(r,kind)/'coverage.json';doc=json.loads(coverage.read_bytes());doc.update(generation=second['generation'],manifest_sha256=second['manifest_sha256']);coverage.write_bytes((json.dumps(doc,sort_keys=True)+'\n').encode());before=snap(r);blocked=False
  try:result=call(r,kind,lambda req:(_ for _ in ()).throw(AssertionError('no HTTP')))
  except gs.GenerationError:blocked=True
  emit('R99_1_COVERAGE_PIN_VALUES',kind=kind,rejected=blocked,unchanged=snap(r)==before,staged_amount='10',published_amount='99')
 # Directory fsync failed after coverage became visible, then retry.
 for kind in [1,2]:
  r=base/('sync-'+str(kind))/'archive';r.parent.mkdir();call(r,kind,lambda req:(200,[row(kind)]));folder=stage(r,kind);coverage=folder/'coverage.json';real=os.fsync;fired=[False]
  def fail(fd):
   name=os.readlink('/proc/self/fd/'+str(fd))
   if name==str(folder) and coverage.exists() and not fired[0]:fired[0]=True;raise OSError(5,'coverage parent sync EIO')
   return real(fd)
  failed=False
  try:
   with patch.object(os,'fsync',fail):call(r,kind,lambda req:(204,None))
  except (OSError,gs.GenerationError):failed=True
  assert failed and fired[0] and coverage.exists();before=coverage.read_bytes();trace=[]
  def track(fd):trace.append(os.readlink('/proc/self/fd/'+str(fd)));return real(fd)
  with patch.object(os,'fsync',track):result=call(r,kind,lambda req:(_ for _ in ()).throw(AssertionError('no HTTP')))
  emit('R99_2_COVERAGE_RETRY',kind=kind,first_failed=failed,retry_status=result['status'],file_resynced=str(coverage) in trace,parent_resynced=str(folder) in trace,coverage_bytes_unchanged=coverage.read_bytes()==before)
 # Hard death at the same rename/fsync window.
 r=base/'kill'/'archive';r.parent.mkdir();call(r,1,lambda req:(200,[row(1)]));child=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--checkout',str(a.checkout),'--child',str(r)],capture_output=True,text=True,timeout=25);assert child.returncode==-signal.SIGKILL,child.stderr
 trace=[]
 with patch.object(os,'fsync',track):result=call(r,1,lambda req:(_ for _ in ()).throw(AssertionError('no HTTP')))
 emit('R99_2_SIGKILL_COVERAGE_RENAME',file_resynced=str(stage(r,1)/'coverage.json') in trace,parent_resynced=str(stage(r,1)) in trace)
 emit('COMPLETE',cases=5)
