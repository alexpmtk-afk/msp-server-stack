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
resumed=w.execute(root,legacy,legacy_auth,lambda:lambda req:(204,None),'a'*64,clock=lambda:now[0],sleep=sleep)
record=json.loads(legacy_path.read_text());assert resumed['report_detail_complete'] and record['send_entries']==4 and record['admission_extension']['prior_state_sha256']==old_record['state_sha256']
print(json.dumps({'two_bounded_portions':'PASS','entries':[3,6],'same_plan_hash':s._digest(plan),'rows':5,'completed_replay_no_dispatch':True,'crash_spent_entry_preserved':1,'legacy_exhausted_counter_after_resume':4,'legacy_original_seal_retained':True,'provider_calls':0}))
