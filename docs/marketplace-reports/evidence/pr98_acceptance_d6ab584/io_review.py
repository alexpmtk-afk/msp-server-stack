"""Independent actual fsync failures/retries and ingest preflight tests; no network."""
import argparse,importlib.util,json,os,sys,tempfile
from pathlib import Path
from unittest.mock import patch
from datetime import datetime
p=argparse.ArgumentParser();p.add_argument('--checkout',type=Path,required=True);a=p.parse_args();sys.path.insert(0,str(a.checkout.resolve()))
def audit(event,args):
 if event in ('socket.connect','socket.getaddrinfo'):raise AssertionError('Network forbidden')
sys.addaudithook(audit)
from apps.msp_marketplace_reports import wb_page_resume as w,archive as ar,generation_store as gs,versioned_archive as va,ingest as ing
assert Path(w.__file__).resolve().is_relative_to(a.checkout.resolve())
spec=importlib.util.spec_from_file_location('f',a.checkout/'tests/test_msp_marketplace_generations.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
def row(kind):return {'reportId':555,'reportType':kind,'rrdId':10,'amount':'10'}
def call(root,kind,send):return w.step_wb_detail(root,'wb_laser_master',2026,555,kind,send)
def folder(root):return root/'.wb-report-stage/wb_laser_master/2026/555'
def emit(check,**kw):print(json.dumps(dict(check=check,**kw),sort_keys=True),flush=True)
with tempfile.TemporaryDirectory(prefix='io-',dir=Path(__file__).parent) as td:
 base=Path(td);n=0
 for kind in [1,2]:
  for mode in ['page_file','page_dir','advance_file','advance_dir','complete_file','complete_dir']:
   n+=1;r=base/str(n)/'archive';r.parent.mkdir();target=folder(r)
   if mode.startswith('complete'):call(r,kind,lambda req:(200,[row(kind)]))
   original=os.fsync;fired=[False]
   def fail(fd):
    path=Path(os.readlink('/proc/self/fd/'+str(fd)));doc=None
    if path.is_file() and path.name.startswith('.incoming-'):
     try:doc=json.loads(path.read_bytes())
     except ValueError:pass
    state=target/'state.json';record=json.loads(state.read_bytes()) if state.exists() else {}
    hit=(mode=='page_file' and doc is not None and 'rows' in doc or
         mode=='page_dir' and path==target and (target/'page-0.json').exists() and record.get('current_rrd_id')==0 or
         mode=='advance_file' and doc is not None and doc.get('current_rrd_id')==10 and doc.get('status')=='RUNNING' or
         mode=='advance_dir' and path==target and record.get('current_rrd_id')==10 and record.get('status')=='RUNNING' or
         mode=='complete_file' and doc is not None and doc.get('status')=='STAGED_COMPLETE' or
         mode=='complete_dir' and path==target and record.get('status')=='STAGED_COMPLETE')
    if hit and not fired[0]:fired[0]=True;raise OSError(5,'synthetic fsync EIO')
    return original(fd)
   with patch.object(os,'fsync',fail):
    try:call(r,kind,lambda req:(204,None) if mode.startswith('complete') else (200,[row(kind)]))
    except OSError:pass
    else:raise AssertionError('fault missed '+mode)
   assert fired[0]
   requests=[]
   def send(req):requests.append(req.body['rrdId']);return (200,[row(kind)]) if req.body['rrdId']==0 else (204,None)
   result=call(r,kind,send)
   if result['status']!='STAGED_COMPLETE':result=call(r,kind,send)
   assert result['status']=='STAGED_COMPLETE' and list(w.read_completed_wb_pages(r,'wb_laser_master',2026,555,kind))==[[row(kind)]]
   assert requests==([0,10] if mode=='page_file' else ([10] if not mode.startswith('complete') else ([] if mode=='complete_dir' else [10])))
   emit('FSYNC_FAILURE_RETRY',kind=kind,mode=mode,requests=requests,status='PASS')
 # B7 conflict preflight must send zero provider calls for every ingestion family.
 class FixedDatetime(datetime):
  @classmethod
  def now(cls,tz=None):return cls(2026,10,30,tzinfo=tz)
 cases=0
 for dataset in ['wb_weekly_finance_main','wb_weekly_finance_buyout','ozon_final_realization','ozon_current_orders_fbo','ozon_current_orders_fbs','ozon_current_accruals']:
  r=base/dataset/'archive';r.parent.mkdir();source=r.parent/'source.csv';wb=dataset.startswith('wb');cabinet='wb_laser_master' if wb else 'ozon_laser_master';period='2026' if wb else ('2026-01' if dataset=='ozon_final_realization' else '2026-10')
  if wb:source.write_text('\ufeffreportId;rrdId;reportType\n555;10;'+('2' if dataset.endswith('buyout') else '1')+'\n')
  elif dataset=='ozon_final_realization':source.write_text('\ufeffreport_year;report_month;row_number\n2026;2026-01;1\n')
  else:source.write_text('\ufeff'+('accrual_id' if dataset.endswith('accruals') else 'posting_number')+'\nsynthetic-1\n')
  va.import_csv_versioned(r,dataset,cabinet,period,source);calls=[]
  def factory(**kwargs):
   def send(req):calls.append(req);raise AssertionError('provider must not be called')
   return send
  args=['--root',str(r),'--creds-file','/synthetic-not-read']
  if wb:args+=['wb-one','--cabinet',cabinet,'--year','2026','--report-id','555','--report-type','2' if dataset.endswith('buyout') else '1']
  elif dataset=='ozon_final_realization':args+=['ozon-final-one','--cabinet',cabinet,'--period',period]
  else:args+=['ozon-current','--cabinet',cabinet]
  with patch.object(ing,'datetime',FixedDatetime):
   try:ing.run(args,factory=factory)
   except (ValueError,gs.GenerationError):pass
   else:raise AssertionError('did not refuse B7 conflict')
  assert not calls;cases+=1
 emit('PREFLIGHT_ALL_FAMILIES',cases=cases,status='PASS')
 emit('COMPLETE',fsync_cases=n,preflight_cases=cases)
