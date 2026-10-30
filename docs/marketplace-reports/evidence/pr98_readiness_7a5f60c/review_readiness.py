"""Independent PR98/readiness probes. Synthetic only; socket and DNS denied."""
import argparse,ast,base64,contextlib,csv,hashlib,importlib.util,io,json,os,sys,tempfile,types
from datetime import date
from pathlib import Path
from unittest.mock import patch
p=argparse.ArgumentParser();p.add_argument('--checkout',type=Path,required=True);p.add_argument('--legacy',type=Path,required=True);a=p.parse_args();sys.path.insert(0,str(a.checkout.resolve()))
def audit(event,args):
 if event in ('socket.connect','socket.getaddrinfo'):raise AssertionError('Network prohibited')
sys.addaudithook(audit)
from apps.msp_marketplace_reports import archive as ar,backfill_plan as bp,generation_store as gs,versioned_archive as va,providers as pv,quota as q,runtime as rt
assert all(Path(x.__file__).resolve().is_relative_to(a.checkout.resolve()) for x in [ar,bp,gs,va,pv,q,rt])
spec=importlib.util.spec_from_file_location('fixture',a.checkout/'tests/test_msp_marketplace_generations.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
def emit(check,**kw):print(json.dumps(dict(check=check,**kw),sort_keys=True),flush=True)
def snapshot(root):return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
def inv(items):return {'wb_laser_master':dict(cabinet='wb_laser_master',year=2026,status='DISCOVERED_NOT_DOWNLOADED',items=items)}
def item(id=11,kind=1):return dict(reportId=id,reportType=kind,dateFrom='2026-10-05',dateTo='2026-10-11')
with tempfile.TemporaryDirectory(prefix='readiness-',dir=Path(__file__).parent) as td:
 base=Path(td);root=base/'empty'
 # Date boundaries for all months, previous year, Jan 1. Six cabinets and no writes.
 n=0
 for year,day in [(2026,date(2026,m,15)) for m in range(1,13)]+[(2026,date(2027,1,1)),(2025,date(2026,10,30))]:
  data=bp.build_backfill_plan(root,year=year,as_of=day);closed=[t for t in data['tasks'] if t.get('dataset')=='ozon_final_realization'];current=[t for t in data['tasks'] if t.get('dataset','').startswith('ozon_current_')]
  months=12 if year<day.year else day.month-1
  assert len(closed)==3*months and len(current)==(9 if year==day.year else 0)
  assert len({t['cabinet'] for t in data['tasks']})==6 and data['provider_coverage_proven'] is False and not root.exists();n+=1
 emit('CALENDAR_AND_SIX_CABINETS',cases=n,status='PASS')
 n=0
 for writer in [ar.import_csv,va.import_csv_versioned]:
  r=base/(writer.__name__);source=r.parent/(writer.__name__+'.csv')
  for kind in [1,2]:
   source.write_text('\ufeffreportId;rrdId;reportType;dateTo\n'+f'{10+kind};1;{kind};2026-10-11\n',encoding='utf8');ds='wb_weekly_finance_'+('main' if kind==1 else 'buyout');writer(r,ds,'wb_laser_master','2026',source)
  before=snapshot(r);data=bp.build_backfill_plan(r,year=2026,as_of=date(2026,10,30),wb_discoveries=inv([item(11,1),item(12,2),item(13,1),item(14,2)]));tasks=[t for t in data['tasks'] if t['cabinet']=='wb_laser_master'];assert len(tasks)==4
  assert {t['report_id']:t['action'] for t in tasks}=={11:'VERIFY_PROVIDER_COVERAGE',12:'VERIFY_PROVIDER_COVERAGE',13:'DOWNLOAD_REPORT_DETAIL',14:'DOWNLOAD_REPORT_DETAIL'};assert snapshot(r)==before;n+=1
 emit('WB_BOTH_TYPES_LAYOUTS',cases=n,status='PASS')
 # Missing CURRENT is UNKNOWN according to generation reconciliation, not MISSING data.
 for kind in ['wb','ozon']:
  r=base/('missing-current-'+kind);args=(r,'wb_weekly_finance_main','wb_laser_master','2026') if kind=='wb' else (r,'ozon_final_realization','ozon_laser_master','2026');gs.publish_batch(*args,f.wb_files('10') if kind=='wb' else f.ozon_final_files());scope=gs._scope(*args);(scope/'CURRENT.json').unlink();before=snapshot(r)
  state=gs.reconcile(*args)['status'];data=bp.build_backfill_plan(r,year=2026,as_of=date(2026,10,30),wb_discoveries=inv([item()]));tasks=[t for t in data['tasks'] if t.get('dataset')==args[1] and t['cabinet']==args[2]];assert state=='UNKNOWN_COMMIT_STATE' and snapshot(r)==before
  emit('MISSING_CURRENT_FAIL_CLOSED',kind=kind,reconcile=state,planned_actions=sorted(set(t['action'] for t in tasks)),planned_statuses=sorted(set(t['status'] for t in tasks)))
 # FINAL's legacy existence test misses dangling annual files and manifests.
 for suffix in ['', '.meta.json']:
  r=base/('dangling-'+('meta' if suffix else 'csv'));args=(r,'ozon_final_realization','ozon_laser_master','2026');gs.publish_batch(*args,f.ozon_final_files());annual=ar._ozon_annual_path(r,'ozon_laser_master','2026');annual.parent.mkdir(parents=True);link=annual.with_name(annual.name+suffix);link.symlink_to(base/'nonexistent');state=bp._archived(r,args[1],args[2],'2026-01')[0];blocked=False
  try:va._assert_no_legacy(r,args[1],args[2],'2026-01')
  except gs.GenerationError:blocked=True
  emit('R98_1_DANGLING_FINAL',file='manifest' if suffix else 'csv',planner_state=state,importer_blocks=blocked)
 # An empty legacy directory is not a mixed financial archive to the importer.
 r=base/'empty-legacy-dir';args=(r,'ozon_final_realization','ozon_laser_master','2026');gs.publish_batch(*args,f.ozon_final_files());ar._location(r,args[1],args[2],'2026-01').parent.mkdir(parents=True);va._assert_no_legacy(r,args[1],args[2],'2026-01');emit('R98_1_EMPTY_LEGACY_DIRECTORY',planner_state=bp._archived(r,args[1],args[2],'2026-01')[0],importer_blocks=False)
 # Real local pacing vs additional shared 65-second safety. No Redis or flags.
 clock=[1000.0];grants=[]
 class FakeQuota:
  def _approved_url(self):return 'synthetic-only'
  def reserve(self,request):
   if grants and clock[0]-grants[-1]<q.WB_EXTRA_INTERVAL:raise pv.ProviderError('API DOWNLOAD PAUSED: synthetic shared quota busy')
   grants.append(clock[0]);return []
 class Reply:
  status=200
  def __enter__(self):return self
  def __exit__(self,*aa):pass
  def read(self,*aa):return b'[{"reportId":11,"rrdId":1,"reportType":1}]'
 class Opener:
  calls=0
  def open(self,*aa,**kk):self.calls+=1;return Reply()
 sender=object.__new__(rt.ReadOnlyHTTP);sender.cabinet='wb_laser_master';sender.marketplace='wb';sender.headers={};sender.quota=FakeQuota();sender.state_root=base/'pacing';sender.opener=Opener()
 with patch.object(rt.time,'time',lambda:clock[0]),patch.object(rt.time,'sleep',lambda t:clock.__setitem__(0,clock[0]+t)):
  failed=False
  try:pv.wb_detail(sender,11,1)
  except pv.ProviderError as ex:failed=True;error=str(ex)
 assert failed and sender.opener.calls==1
 emit('LIVE_BLOCKER_63_VS_65',elapsed=clock[0]-1000,local_wait=rt.WB_WAIT_SECONDS,shared_safety=q.WB_EXTRA_INTERVAL,requests_sent=sender.opener.calls,error=error)
 # Busy on page 2 loses in-memory page 1; repeated call restarts at zero.
 requests=[]
 def send(req):
  requests.append(req.body['rrdId'])
  if req.body['rrdId']==0:return 200,[dict(reportId=11,rrdId=1,reportType=1)]
  raise pv.ProviderError('synthetic busy')
 for _ in range(2):
  try:pv.wb_detail(send,11,1)
  except pv.ProviderError:pass
 assert requests==[0,1,0,1];emit('LIVE_BLOCKER_NO_CHECKPOINT',requested_cursors=requests)
 # Year discovery request starts Jan 1, unlike the old boundary-week contract.
 requests=[]
 pv.wb_discover_all(lambda req:(requests.append(req) or (200,[])),2026,today=date(2026,10,30))
 emit('WB_BOUNDARY_DISCOVERY',new_start=requests[0].body['dateFrom'],old_documented_start='2025-12-29',provider_boundary_semantics='NOT_VERIFIED')
 # Identity/key equivalence and mismatch, no controller instantiation.
 tree=ast.parse((a.legacy/'core/client.py').read_text());method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_quota_key');method.decorator_list=[];ns=dict(hashlib=hashlib,json=json,base64=base64,binascii=__import__('binascii'));exec(compile(ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[])),'legacy_quota_identity','exec'),ns)
 token='synthetic.'+base64.urlsafe_b64encode(json.dumps({'sid':'synthetic-seller'}).encode()).decode().rstrip('=')+'.synthetic';creds={'token':token};oldowner=ns['_quota_key'](types.SimpleNamespace(name='wb'),creds);newowner=q.stable_owner_key('wb',creds);assert oldowner==newowner
 old=q.build_rules(service='wb',cabinet_key=oldowner,host=q.WB_HOST,operation_id='wb_finance_sales_reports_list',scope='finance',catalog_rate_limit='1 req/min');new=q.request_rules('wb',creds,pv.Request('wb',pv.WB_LIST,{}));emit('P01_WB_KEYS',owner_equal=True,old=[dict(key=x.key,interval=x.interval_seconds) for x in old],new=[dict(key=x.key,interval=x.interval_seconds) for x in new],common_keys=sorted({x.key for x in old}&{x.key for x in new}))
 cid={'client_id':'123456'};assert ns['_quota_key'](types.SimpleNamespace(name='ozon'),cid)==q.stable_owner_key('ozon',cid)
 denied=[]
 for path in [pv.OZON_FINAL,pv.OZON_FBO,pv.OZON_FBS,pv.OZON_ACCRUAL]:
  try:q.request_rules('ozon',cid,pv.Request('ozon',path,{}))
  except pv.ProviderError:denied.append(path)
 assert len(denied)==4;emit('P01_OZON_IDENTITY_AND_DENIAL',owner_equal=True,blocked_paths=denied)
 # Pure legacy/new controller copy: exact functions and Lua code, no env reads/runtime calls.
 body=(a.checkout/'apps/msp_marketplace_reports/shared_rate_limit.py').read_bytes();legacy=(a.legacy/'core/rate_limit.py').read_bytes();assert body[body.index(b'"""Process-wide'):]==legacy
 emit('P01_CONTROLLER_SOURCE',exact_copy=True,legacy_sha='0510a409ab589c639930fbca35afb3e68d874f81')
 emit('COMPLETE',synthetic_only=True)
