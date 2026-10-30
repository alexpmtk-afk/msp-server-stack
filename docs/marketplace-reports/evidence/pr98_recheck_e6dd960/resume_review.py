"""Independent e6dd960 WB crash/integrity and Ozon cooldown probes; synthetic only."""
import argparse,asyncio,json,os,signal,subprocess,sys,tempfile,types
from pathlib import Path
from unittest.mock import patch

def audit(event,args):
 if event in ('socket.connect','socket.getaddrinfo'):raise AssertionError('Network forbidden')
sys.addaudithook(audit)
p=argparse.ArgumentParser();p.add_argument('--checkout',type=Path,required=True);p.add_argument('--child',type=Path);p.add_argument('--point');p.add_argument('--kind',type=int,default=1);a=p.parse_args();sys.path.insert(0,str(a.checkout.resolve()))
from apps.msp_marketplace_reports import wb_page_resume as w,quota as q,generation_store as gs
assert Path(w.__file__).resolve().is_relative_to(a.checkout.resolve())
def emit(check,**kw):print(json.dumps(dict(check=check,**kw),sort_keys=True),flush=True)
def row(kind=1,n=10):return {'reportId':555,'reportType':kind,'rrdId':n,'amount':'10'}
def call(root,send,kind=1,**kw):return w.step_wb_detail(root,'wb_laser_master',2026,555,kind,send,**kw)
def folder(root):return root/'.wb-report-stage/wb_laser_master/2026/555'
def snap(root):return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
def completed(root,kind=1):return list(w.read_completed_wb_pages(root,'wb_laser_master',2026,555,kind))
if a.child:
 real=os.replace
 def replace(src,dst):
  result=real(src,dst);target=Path(dst)
  if a.point=='page_rename' and target.name=='page-0.json':os.kill(os.getpid(),signal.SIGKILL)
  if target.name=='state.json':
   state=json.loads(target.read_bytes())
   if a.point=='state_advance_rename' and state['current_rrd_id']>0:os.kill(os.getpid(),signal.SIGKILL)
   if a.point=='complete_rename' and state['status']=='STAGED_COMPLETE':os.kill(os.getpid(),signal.SIGKILL)
  return result
 os.replace=replace
 def fault(point):
  if a.point=='after_page_checkpoint':os.kill(os.getpid(),signal.SIGKILL)
 call(a.child,lambda req:(204,None) if a.point=='complete_rename' else (200,[row(a.kind)]),kind=a.kind,fault=fault)
 raise AssertionError('SIGKILL not reached')
with tempfile.TemporaryDirectory(prefix='resume-',dir=Path(__file__).parent) as td:
 base=Path(td);n=0
 def root():
  global n
  n+=1;r=base/str(n)/'archive';r.parent.mkdir();return r
 def pending(r,kind=1):
  def stop(_):raise OSError('stop after durable page before state')
  try:call(r,lambda req:(200,[row(kind)]),kind=kind,fault=stop)
  except OSError:pass
  assert (folder(r)/'page-0.json').exists() and json.loads((folder(r)/'state.json').read_bytes())['current_rrd_id']==0
 # Actual process death, unlike exception-only developer fixtures.
 kills=0
 for kind in [1,2]:
  for point in ['page_rename','after_page_checkpoint','state_advance_rename','complete_rename']:
   r=root()
   if point=='complete_rename':call(r,lambda req:(200,[row(kind)]),kind=kind)
   child=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--checkout',str(a.checkout),'--child',str(r),'--kind',str(kind),'--point',point],capture_output=True,text=True,timeout=20)
   assert child.returncode==-signal.SIGKILL,(point,child.stderr)
   before=(folder(r)/'page-0.json').read_bytes();requests=[]
   if point in ('page_rename','after_page_checkpoint'):
    replay=call(r,lambda req:(_ for _ in ()).throw(AssertionError('no page refetch')),kind=kind);assert replay['provider_calls']==0 and replay['cursor']==10
   def end(req):requests.append(req.body['rrdId']);return 204,None
   result=call(r,end,kind=kind);assert result['status']=='STAGED_COMPLETE' and requests==([] if point=='complete_rename' else [10]);assert completed(r,kind)==[[row(kind)]] and (folder(r)/'page-0.json').read_bytes()==before;kills+=1
 emit('REAL_SIGKILL_REPLAY',cases=kills,status='PASS')
 # Two-page busy, transport failure, final 204, repeated completion.
 positives=0
 for kind in [1,2]:
  for mode in ['busy','429','transport']:
   r=root();call(r,lambda req:(200,[row(kind)]),kind=kind);statefile=folder(r)/'state.json'
   def fail(req):
    if mode=='busy':raise w.ProviderError('API DOWNLOAD PAUSED: shared quota busy; retry later')
    if mode=='transport':raise w.ProviderError('provider transport unavailable; retry with saved cursor')
    return 429,None
   try:result=call(r,fail,kind=kind)
   except w.ProviderError:assert mode=='transport'
   assert json.loads(statefile.read_bytes())['current_rrd_id']==10
   requests=[]
   def nextpage(req):requests.append(req.body['rrdId']);return 200,[row(kind,20)]
   call(r,nextpage,kind=kind);assert requests==[10];call(r,lambda req:(204,None),kind=kind);assert completed(r,kind)==[[row(kind)],[row(kind,20)]]
   assert call(r,lambda req:(_ for _ in ()).throw(AssertionError('no refetch')),kind=kind)['status']=='STAGED_COMPLETE';positives+=1
 emit('BUSY_TRANSPORT_COMPLETION',cases=positives,status='PASS')
 # Committed-in-state page corruption is rejected before HTTP, without rewrites.
 negatives=0
 for mode in ['missing','changed','bad_schema','bad_cursor']:
  r=root();call(r,lambda req:(200,[row()]));file=folder(r)/'page-0.json';statefile=folder(r)/'state.json'
  if mode=='missing':file.unlink()
  elif mode=='changed':file.write_bytes(file.read_bytes().replace(b'"amount":"10"',b'"amount":"99"'))
  else:
   state=json.loads(statefile.read_bytes());state['schema' if mode=='bad_schema' else 'current_rrd_id']=True if mode=='bad_schema' else 20;statefile.write_bytes(w._canonical(state))
  before=snap(r)
  try:call(r,lambda req:(_ for _ in ()).throw(AssertionError('must not send')))
  except gs.GenerationError:pass
  else:raise AssertionError(mode)
  assert snap(r)==before;negatives+=1
 emit('INDEXED_PAGE_STATE_CORRUPTION',cases=negatives,status='PASS')
 # Counterexample: orphan page lacks persisted independent digest; retry blesses modified financial bytes.
 r=root();pending(r);file=folder(r)/'page-0.json';data=json.loads(file.read_bytes());data['rows'][0]['amount']='99';file.write_bytes(w._canonical(data));before=file.read_bytes();replay=call(r,lambda req:(_ for _ in ()).throw(AssertionError('no HTTP')));state=json.loads((folder(r)/'state.json').read_bytes());call(r,lambda req:(204,None));values=completed(r)
 emit('R98_2_ORPHAN_REHASH',accepted_modified_amount=values[0][0]['amount'],cursor_advanced=replay['cursor'],state_hash_matches_changed_file=state['pages'][0]['sha256']==w._sha(before))
 # Even whitespace on orphan becomes an indexed hash inconsistent with actual bytes.
 r=root();pending(r);file=folder(r)/'page-0.json';file.write_bytes(file.read_bytes()+b' ');call(r,lambda req:(_ for _ in ()).throw(AssertionError('no HTTP')));blocked=False
 try:call(r,lambda req:(204,None))
 except gs.GenerationError:blocked=True
 emit('R98_2_ORPHAN_CANONICAL_HASH',cursor_after_replay=json.loads((folder(r)/'state.json').read_bytes())['current_rrd_id'],next_step_blocked=blocked)
 # Write/read cap mismatch is demonstrated at a scaled constant, not using huge financial data.
 r=root();big=row();big['synthetic_padding']='X'*5000
 with patch.object(w,'MAX_STAGE_BYTES',4096):
  try:call(r,lambda req:(200,[big]))
  except gs.GenerationError:pass
  else:raise AssertionError('oversize was accepted')
  page=folder(r)/'page-0.json';assert page.stat().st_size>4096;blocked=False
  try:call(r,lambda req:(_ for _ in ()).throw(AssertionError('no HTTP')))
  except gs.GenerationError:blocked=True
 emit('R98_3_SIZE_MISMATCH',written_bytes=page.stat().st_size,scaled_read_cap=4096,cursor=json.loads((folder(r)/'state.json').read_bytes())['current_rrd_id'],retry_blocked=blocked)
 # Additional safety rule makes inherited defer() choose specific keys, excluding shared Ozon global.
 real_env=dict(os.environ);cooldowns=[]
 for path in sorted(q.OZON_APPROVED_PATHS):
  # Replace q's namespace ONLY, no changes to process environment or production approvals.
  with patch.object(q,'os',types.SimpleNamespace(environ={q.OZON_REQUIRED_METHOD_APPROVAL:'YES'})):
   rules=q.request_rules('ozon',{'client_id':'123456'},w.Request('ozon',path,{}))
  ctl=object.__new__(q.GlobalRateController);ctl.redis_url='synthetic-no-connect'
  async def capture(keys,seconds):cooldowns.append({'path':path,'keys':keys,'seconds':seconds})
  ctl._defer_redis=capture;asyncio.run(ctl.defer(rules,q.retry_delay({'Retry-After':'120'},rules)));globalkey=next(x.key for x in rules if x.key.endswith(':global'))
  emit('R98_4_OZON_COOLDOWN',path=path,global_key_deferred=globalkey in cooldowns[-1]['keys'],deferred_key_suffixes=[x.split(':')[-1] for x in cooldowns[-1]['keys']],seconds=cooldowns[-1]['seconds'])
 assert dict(os.environ)==real_env
 emit('COMPLETE',sigkill_cases=kills,positive_cases=positives,corruption_cases=negatives,orphan_cases=2,size_cases=1,ozon_cooldown_cases=4)
