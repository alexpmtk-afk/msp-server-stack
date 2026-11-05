"""Isolated overlaid accepted loader: actual durable pages/budgets, fake HTTP only."""
import ast,base64,importlib.util,json,sys,tempfile
from pathlib import Path
bundle=Path(sys.argv[1]);repo=Path(sys.argv[2]);folder=Path(sys.argv[3])
node=next(n for n in ast.parse(bundle.read_bytes()).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PACKAGE' for t in n.targets));p=ast.literal_eval(node.value)
for name,raw in p['files'].items():
 if name.startswith('apps/'):
  target=folder/'code'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(base64.b64decode(raw))
sys.path.insert(0,str(folder/'code'))
def no_network(event,args):
 if event in ('socket.connect','socket.getaddrinfo'):raise AssertionError('network denied')
sys.addaudithook(no_network)
from apps.msp_marketplace_reports import standalone_wb as s
from apps.msp_marketplace_reports.finance_receipts import report_receipt
spec=importlib.util.spec_from_file_location('tested_worker',repo/'scripts/finance_control/worker.py');w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
root=folder/'archive';root.mkdir();now=[1000.];calls=[]
plan={'schema':1,'cabinet':'wb_laser_master','year':2026,'report_id':865431404,'report_type':1,'max_send_entries':3}
auth={'schema':1,'plan_sha256':s._digest(plan),'code_sha256':s.code_digest(),'archive_root':str(root),'expires_epoch':9999999999,'owner_api_pilot_authorized':True,'shared_quota_verified':True,'conflicting_clients_excluded':True,'evidence_reference':'OFFLINE_CONTROL_POLICY'}
answers=iter([(200,[{'reportId':865431404,'reportType':1,'rrdId':n}]) for n in range(1,6)]+[(204,None)])
def factory():
 def send(req):calls.append(req.body['rrdId']);return next(answers)
 return send
def sleep(t):now[0]+=t
first=w.execute(root,plan,auth,factory,'a'*64,clock=lambda:now[0],sleep=sleep)
path=root/'.wb-executor'/(s._digest(plan)+'.json');journal=json.loads(path.read_text())
assert len(calls)==3 and journal['send_entries']==3 and journal['approved_total_entries']==1000,(calls,journal)
second=w.execute(root,plan,auth,factory,'a'*64,clock=lambda:now[0],sleep=sleep)
assert second['report_detail_complete'] and second['receipt']['rows']==5,second
assert json.loads(path.read_text())['send_entries']==6 and calls==[0,1,2,3,4,5],calls
before=path.read_bytes();third=w.execute(root,plan,auth,factory,'a'*64,clock=lambda:now[0],sleep=sleep);assert third['report_detail_complete'] and path.read_bytes()==before and len(calls)==6
# Interrupted pre-factory admission preserves the spent count on reconstruction.
crash_plan={**plan,'report_id':865431405};crash_auth={**auth,'plan_sha256':s._digest(crash_plan)}
def fault(where):
 if where=='after_budget_before_sender':raise RuntimeError('injected crash')
try:s.run_step(root,crash_plan,crash_auth,lambda:(_ for _ in ()).throw(AssertionError('factory forbidden')),now=now[0],fault=fault,admission_ceiling=1000,policy_sha256='a'*64)
except RuntimeError:pass
crash_path=root/'.wb-executor'/(s._digest(crash_plan)+'.json');assert json.loads(crash_path.read_text())['send_entries']==1
# Existing exhausted legacy budget is extended in-place, never re-keyed/reset.
legacy={**plan,'report_id':865431406};legacy_auth={**auth,'plan_sha256':s._digest(legacy)}
old_answers=iter([(200,[{'reportId':865431406,'reportType':1,'rrdId':n}]) for n in range(1,4)])
legacy_out=s.run_bounded(root,legacy,legacy_auth,lambda:lambda req:next(old_answers),clock=lambda:now[0],sleep=sleep)
legacy_path=root/'.wb-executor'/(s._digest(legacy)+'.json');old_record=json.loads(legacy_path.read_text());assert old_record['send_entries']==3
(root/'.wb-executor'/('control-'+('e'*32)+'-events.jsonl')).write_text((json.dumps({'event':'HTTP_DISPATCH_ATTEMPT','plan':legacy})+'\n')*3)
resumed=w.execute(root,legacy,legacy_auth,lambda:lambda req:(204,None),'a'*64,clock=lambda:now[0],sleep=sleep)
record=json.loads(legacy_path.read_text());assert resumed['report_detail_complete'] and record['send_entries']==4 and record['admission_extension']['prior_state_sha256']==old_record['state_sha256']
proof={'two_bounded_portions':'PASS','entries':[3,6],'same_plan_hash':s._digest(plan),'rows':5,'completed_replay_no_dispatch':True,'crash_spent_entry_preserved':1,'legacy_exhausted_counter_after_resume':4,'legacy_original_seal_retained':True,'provider_calls':0}
# Lost original budget must never be inferred as zero, across prior nonce logs.
negative_count=0
for case in ('missing_dispatch','missing_unknown','missing_page','corrupt_budget','understated_budget','legacy_http','multi_nonce','orphan_state','corrupt_seal','legacy_other','truncated_http'):
 r=folder/('negative-'+case);r.mkdir();e=r/'.wb-executor';e.mkdir()
 a={**auth,'archive_root':str(r)};bp=e/(s._digest(plan)+'.json')
 if case in ('missing_page','orphan_state'):
  stage=r/'.wb-report-stage'/plan['cabinet']/'2026'/'865431404-type-1';stage.mkdir(parents=True);(stage/('state.json' if case=='orphan_state' else 'page-0.json')).write_text('{}')
 else:
  event={'event':'HTTP_OUTCOME_UNKNOWN' if case=='missing_unknown' else 'HTTP_DISPATCH_ATTEMPT','plan':plan}
  name='history-next-865431404-events.jsonl' if case=='legacy_http' else 'control-'+('b'*32)+'-events.jsonl'
  if case=='legacy_http':event={'event':'HTTP_DISPATCH_ATTEMPT','method_scope':'detail'}
  (e/name).write_text(json.dumps(event)+'\n')
 if case=='legacy_other':
  (e/name).unlink();(e/'E-883801632-events.jsonl').write_text(json.dumps({'event':'HTTP_DISPATCH_ATTEMPT','rrdId':0})+'\n')
 if case=='truncated_http':(e/name).write_text('{broken')
 if case=='corrupt_budget':bp.write_text('{broken')
 if case in ('understated_budget','multi_nonce','corrupt_seal'):
  v={'schema':1,'plan_sha256':s._digest(plan),'send_entries':(1 if case=='multi_nonce' else 0),'status':'READY'};bp.write_bytes(s._encode({**v,'state_sha256':s._digest(v)}))
 if case=='multi_nonce':(e/('control-'+('c'*32)+'-events.jsonl')).write_text(json.dumps({'event':'HTTP_DISPATCH_ATTEMPT','plan':plan})+'\n')
 if case=='corrupt_seal':
  v=json.loads(bp.read_text());v['state_sha256']='0'*64;bp.write_text(json.dumps(v))
 def forbidden():raise AssertionError('NEW HTTP FACTORY AFTER LOST BUDGET: '+case)
 for entry in ('worker','overlay'):
  before={str(p.relative_to(r)):p.read_bytes() for p in r.rglob('*') if p.is_file()}
  try:
   if entry=='worker':w.execute(r,plan,a,forbidden,'a'*64,clock=lambda:1000.,sleep=lambda t:None)
   else:s.run_step(r,plan,a,forbidden,now=1000.,admission_ceiling=1000,policy_sha256='a'*64)
  except (s.PilotBlocked,ValueError,OSError):pass
  else:raise AssertionError('lost budget not blocked: '+case+' '+entry)
  after={str(p.relative_to(r)):p.read_bytes() for p in r.rglob('*') if p.is_file()}
  assert before==after,('evidence mutated',case,entry)
  negative_count+=1

# The transport boundary also refuses a budget removed AFTER durable admission.
r=folder/'transport-boundary';r.mkdir();e=r/'.wb-executor';e.mkdir()
bp=e/(s._digest(plan)+'.json');v={'schema':1,'plan_sha256':s._digest(plan),'send_entries':1,'status':'DISPATCH_UNCERTAIN'}
bp.write_bytes(s._encode({**v,'state_sha256':s._digest(v)}))
log=e/('control-'+('d'*32)+'-events.jsonl');log.write_text(json.dumps({'event':'HTTP_DISPATCH_ATTEMPT','plan':plan})+'\n');bp.unlink()
class NoHTTP:
 def open(self,*a,**k):raise AssertionError('transport called after lost budget')
import urllib.request
try:w.Audit(NoHTTP(),log,'https://finance-api.wildberries.ru/test',plan).open(urllib.request.Request('https://finance-api.wildberries.ru/test',data=b'{}'),1)
except (s.PilotBlocked,OSError):pass
else:raise AssertionError('transport boundary did not HOLD')
negative_count+=1
# Real persisted page/cursor followed by loss of its original budget.
r=folder/'real-page-loss';r.mkdir();a={**auth,'archive_root':str(r)};sent=[]
def one_page():
 def send(req):sent.append(req.body['rrdId']);return (200,[{'reportId':865431404,'reportType':1,'rrdId':5}])
 return send
s.run_step(r,plan,a,one_page,now=1000.,admission_ceiling=1000,policy_sha256='a'*64)
(r/'.wb-executor'/(s._digest(plan)+'.json')).unlink()
try:w.execute(r,plan,a,one_page,'a'*64,clock=lambda:2000.,sleep=lambda t:None)
except (s.PilotBlocked,OSError):pass
else:raise AssertionError('real staged page lost-budget path not blocked')
assert sent==[0],sent
negative_count+=1
proof.update(lost_budget_negative_scenarios=negative_count,new_http_in_negative_scenarios=0,all_nonce_logs_checked=True)
print(json.dumps(proof))
