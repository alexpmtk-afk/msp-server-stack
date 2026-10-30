"""OFFLINE wiring proof, NOT an installed worker or second queue.

Uses actual pinned page staging/versioned publication; fake provider and one
in-memory scheduling fixture. No credentials, Redis or HTTP. Production
not-before, scheduler bindings, correction and retention policy are not here.
"""
import argparse,asyncio,csv,json,os,sys,tempfile
from pathlib import Path
from unittest.mock import patch
p=argparse.ArgumentParser();p.add_argument('--checkout',type=Path,required=True);a=p.parse_args();sys.path.insert(0,str(a.checkout.resolve()))
def audit(event,args):
 if event in ('socket.connect','socket.getaddrinfo'):raise AssertionError('Network forbidden')
sys.addaudithook(audit)
from apps.msp_marketplace_reports import wb_page_resume as w,archive as ar,generation_store as gs,versioned_archive as va,ingest as ing
assert Path(w.__file__).resolve().is_relative_to(a.checkout.resolve())
def emit(**kw):print(json.dumps(kw,sort_keys=True),flush=True)
def spool(root,kind,path):
 # Two bounded passes, never aggregate every financial row. Finish reader
 # generator/admission lock before calling the publisher using that lock.
 fields={'reportId','rrdId','reportType'}
 for page in w.read_completed_wb_pages(root,'wb_laser_master',2026,555,kind):
  for row in page:fields.update(row)
 names=['reportId','rrdId','reportType']+sorted(fields-{'reportId','rrdId','reportType','_raw_json'})+['_raw_json'];count=0
 fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
 with os.fdopen(fd,'w',encoding='utf-8-sig',newline='') as fh:
  writer=csv.DictWriter(fh,fieldnames=names,delimiter=';',lineterminator='\n');writer.writeheader()
  for page in w.read_completed_wb_pages(root,'wb_laser_master',2026,555,kind):
   for row in page:
    values={name:ing._cell(row.get(name)) for name in names};values['_raw_json']=json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(',',':'));writer.writerow(values);count+=1
  fh.flush();os.fsync(fh.fileno())
 return count
async def prepare(root,kind):
 sent=[];turn=[0]
 def fake_send(req):
  sent.append(req.body['rrdId']);turn[0]+=1
  if turn[0]==2:raise w.ProviderError('API DOWNLOAD PAUSED: shared quota busy; retry later')
  cursor=req.body['rrdId']
  if cursor>=20:return 204,None
  row={'reportId':555,'rrdId':10 if cursor==0 else 20,'reportType':kind,'dateFrom':'2025-12-29','dateTo':'2026-01-04','amount':'10'}
  if cursor:row['extra_second_page']='preserved'
  return 200,[row]
 while True:
  result=await asyncio.to_thread(w.step_wb_detail,root,'wb_laser_master',2026,555,kind,fake_send)
  if result['status']=='STAGED_COMPLETE':break
 # Synthetic fixture advances immediately; NOT the real WAITING scheduler.
 assert sent==[0,10,10,20]
 return sent
with tempfile.TemporaryDirectory(prefix='bridge-proof-',dir=Path(__file__).parent) as td:
 base=Path(td)
 for kind in [1,2]:
  for failure in ['none','after_archive_commit','before_coverage']:
   place=base/(str(kind)+'-'+failure);place.mkdir();root=place/'archive';requests=asyncio.run(prepare(root,kind));source=place/'report.csv';assert spool(root,kind,source)==2
   dataset='wb_weekly_finance_main' if kind==1 else 'wb_weekly_finance_buyout';args=(root,dataset,'wb_laser_master','2026');coverage=place/'proof-coverage.json';real=va.publish_batch
   if failure=='after_archive_commit':
    def fault(label):
     if label=='after_commit':raise OSError('synthetic lost commit response')
    def uncertain(*aa,**kk):return real(*aa,**kk,fault=fault)
    with patch.object(va,'publish_batch',uncertain):
     try:va.import_csv_versioned(*args,source)
     except gs.CommitUncertainError:pass
     else:raise AssertionError('fault missed')
    assert not coverage.exists()
   receipt=va.import_csv_versioned(*args,source);active=gs.read_generation(*args,receipt['generation'],expected_digest=receipt['manifest_sha256']);_,rows=ar._rows(active['files']['data.csv'],('reportId','rrdId'));assert len(rows)==2 and all(row['reportType']==str(kind) for row in rows.values());pin=receipt['generation']
   if failure=='before_coverage':
    assert not coverage.exists();retry=va.import_csv_versioned(*args,source);assert retry['generation']==pin and not retry['changed']
   stage=json.loads((w._dir(root,'wb_laser_master',2026,555)/'state.json').read_bytes());assert stage['status']=='STAGED_COMPLETE'
   record={'schema':1,'source':'synthetic provider fixture ONLY','cabinet':'wb_laser_master','dataset':dataset,'report_id':555,'report_type':kind,'year':2026,'terminal_cursor':stage['current_rrd_id'],'page_hashes':[x['sha256'] for x in stage['pages']],'generation':pin,'manifest_sha256':receipt['manifest_sha256'],'status':'SYNTHETIC_PUBLICATION_VERIFIED','provider_coverage_proven':False}
   ar._safe_write(coverage,(json.dumps(record,sort_keys=True)+'\n').encode());assert json.loads(coverage.read_bytes())==record
   before=coverage.read_bytes();calls=[];assert w.step_wb_detail(root,'wb_laser_master',2026,555,kind,lambda req:calls.append(req))['status']=='STAGED_COMPLETE';again=va.import_csv_versioned(*args,source);assert not calls and again['generation']==pin and not again['changed'] and coverage.read_bytes()==before
   emit(check='VERTICAL_SLICE',kind=kind,failure=failure,requests=requests,rows=2,pinned_publication_verified=True,no_repeat_provider=True,status='PASS')
 emit(check='COMPLETE',cases=6,production_wiring=False)
