import json,tempfile,unittest
from pathlib import Path
from apps.msp_marketplace_reports import wb_page_resume as p
from apps.msp_marketplace_reports.generation_store import GenerationError
from apps.msp_marketplace_reports.wb_worker_adapter import run_one_step
ROOT=Path(__file__).resolve().parents[1]
def row(i,amount='1'):return {'reportId':601780521,'reportType':1,'rrdId':i,'amount':amount}
class UnorderedWB(unittest.TestCase):
 def test_actual_identifier_order_keeps_original_last_cursor_not_maximum(self):
  fixture=json.loads((ROOT/'tests/fixtures/wb_601780521_rrd_ids.json').read_text());rows=[row(i) for i in fixture['ids']]
  page={'schema':1,'report_id':601780521,'report_type':1,'cursor':fixture['cursor'],'next_rrd_id':rows[-1]['rrdId'],'rows':rows};page['payload_sha256']=p._sha(p._canonical(page))
  self.assertEqual(p._validate_page(page,601780521,1,fixture['cursor']),rows[-1]['rrdId'])
  self.assertLess(rows[-1]['rrdId'],max(fixture['ids']))
 def test_next_request_uses_original_last_and_identical_overlap_publishes_once(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);calls=[];answers=iter([(200,[row(11),row(30),row(20)]),(200,[row(21),row(30),row(31)]),(204,None)])
   def send(req):calls.append(req.body['rrdId']);return next(answers)
   run_one_step(root,'wb_laser_master',2026,601780521,1,send)
   run_one_step(root,'wb_laser_master',2026,601780521,1,send)
   done=run_one_step(root,'wb_laser_master',2026,601780521,1,send)
   self.assertEqual(calls,[0,20,31]);self.assertEqual(done['rows'],5)
   saved=[r for page in p.read_completed_wb_pages(root,'wb_laser_master',2026,601780521,1) for r in page]
   self.assertEqual([r['rrdId'] for r in saved],[11,30,20,21,31])
 def test_conflicting_overlap_holds_with_original_cursor_and_both_responses_retained(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);p.step_wb_detail(root,'wb_laser_master',2026,601780521,1,lambda req:(200,[row(11),row(30),row(20)]))
   folder=p._dir(root,'wb_laser_master',2026,601780521,1);old=(folder/'state.json').read_bytes()
   with self.assertRaisesRegex(GenerationError,'conflicting'):
    p.step_wb_detail(root,'wb_laser_master',2026,601780521,1,lambda req:(200,[row(30,'DIFFERENT'),row(31)]))
   self.assertEqual((folder/'state.json').read_bytes(),old);self.assertTrue((folder/'response-20.json').exists());self.assertFalse((folder/'page-20.json').exists())

class SavedProcessingRecovery(unittest.TestCase):
 def test_replay_saved_response_spends_zero_then_terminal_request_extends_same_budget(self):
  import importlib.util
  from unittest.mock import patch
  spec=importlib.util.spec_from_file_location('apps.msp_marketplace_reports.unordered_overlay',ROOT/'scripts/finance_control/overlays/standalone_wb.py');s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
  plan={'schema':1,'cabinet':'wb_laser_master','year':2026,'report_id':601780521,'report_type':1,'max_send_entries':3}
  evidence=json.loads((ROOT/'tests/fixtures/wb_601780521_rrd_ids.json').read_text());original=json.loads((ROOT/'tests/fixtures/wb_601780521_hold.json').read_text())
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);p.step_wb_detail(root,plan['cabinet'],2026,601780521,1,lambda req:(200,[row(evidence['cursor'])]))
   stage=p._dir(root,plan['cabinet'],2026,601780521,1);prefix=(stage/'page-0.json').read_bytes()
   raw={'schema':1,'report_id':601780521,'report_type':1,'cursor':evidence['cursor'],'next_rrd_id':evidence['ids'][-1],'rows':[row(i) for i in evidence['ids']]};raw['payload_sha256']=p._sha(p._canonical(raw));raw_bytes=p._canonical(raw)
   pending=stage/('response-'+str(evidence['cursor'])+'.json');pending.write_bytes(raw_bytes)
   folder=root/'.wb-executor';folder.mkdir();budget=folder/(s._digest(plan)+'.json');budget.write_bytes(s._encode({**original,'state_sha256':s._digest(original)}))
   journal=folder/('control-'+32*'a'+'-events.jsonl');journal.write_text(''.join(json.dumps({'event':event,'plan':plan,**values})+'\n' for _ in range(3) for event,values in [('HTTP_DISPATCH_ATTEMPT',{}),('HTTP_RESPONSE',{'status':200})]))
   auth={'schema':1,'plan_sha256':s._digest(plan),'code_sha256':s.code_digest(),'archive_root':str(root),'expires_epoch':9999999999,'owner_api_pilot_authorized':True,'shared_quota_verified':True,'conflicting_clients_excluded':True,'evidence_reference':'OFFLINE_CAPTURED_PAGE_REPLAY'}
   before_budget=budget.read_bytes()
   bad=json.loads(raw_bytes);bad['rows'][0]['amount']='TAMPERED';bad.pop('payload_sha256');bad['payload_sha256']=p._sha(p._canonical(bad));pending.write_bytes(p._canonical(bad))
   with patch.object(s,'CAPTURED_RESPONSE_SHA256',p._sha(raw_bytes)),patch.object(s,'CAPTURED_PREFIX_SHA256',p._sha(prefix)):
    with self.assertRaises(s.PilotBlocked):s.run_step(root,plan,auth,lambda:self.fail('no HTTP for tampered pending response'),now=1000.,admission_ceiling=1000,policy_sha256='c'*64)
   self.assertEqual(budget.read_bytes(),before_budget);pending.write_bytes(raw_bytes)
   extra=folder/('control-'+32*'b'+'-events.jsonl');extra.write_text(json.dumps({'event':'HTTP_OUTCOME_UNKNOWN','plan':plan})+'\n')
   with patch.object(s,'CAPTURED_RESPONSE_SHA256',p._sha(raw_bytes)),patch.object(s,'CAPTURED_PREFIX_SHA256',p._sha(prefix)):
    with self.assertRaises(s.PilotBlocked):s.run_step(root,plan,auth,lambda:self.fail('no HTTP for uncertain prior nonce'),now=1000.,admission_ceiling=1000,policy_sha256='c'*64)
   self.assertEqual(budget.read_bytes(),before_budget);extra.unlink()
   with patch.object(s,'CAPTURED_RESPONSE_SHA256',p._sha(raw_bytes)),patch.object(s,'CAPTURED_PREFIX_SHA256',p._sha(prefix)):
    out=s.run_step(root,plan,auth,lambda:self.fail('replay must not invoke sender'),now=1000.,admission_ceiling=1000,policy_sha256='c'*64)
   self.assertEqual(out['status'],'PAGE_STAGED');self.assertEqual(out['send_entries'],3)
   state=json.loads((stage/'state.json').read_text());self.assertEqual(state['current_rrd_id'],evidence['ids'][-1]);self.assertEqual(len(state['pages']),2)
   self.assertEqual((stage/'page-0.json').read_bytes(),prefix);self.assertEqual(pending.read_bytes(),raw_bytes)
   self.assertEqual((stage/('page-'+str(evidence['cursor'])+'.json')).read_bytes(),raw_bytes)
   calls=[]
   def sender(req):calls.append(req.body['rrdId']);return 204,None
   unchanged=budget.read_bytes();hidden=pending.with_suffix('.held');pending.rename(hidden)
   with patch.object(s,'CAPTURED_RESPONSE_SHA256',p._sha(raw_bytes)),patch.object(s,'CAPTURED_PREFIX_SHA256',p._sha(prefix)):
    with self.assertRaises(GenerationError):s.run_step(root,plan,auth,lambda:self.fail('lost retained response must not refetch'),now=2000.,admission_ceiling=1000,policy_sha256='c'*64)
   self.assertEqual(budget.read_bytes(),unchanged);hidden.rename(pending)
   with patch.object(s,'CAPTURED_RESPONSE_SHA256',p._sha(raw_bytes)),patch.object(s,'CAPTURED_PREFIX_SHA256',p._sha(prefix)):
    done=s.run_step(root,plan,auth,lambda:sender,now=2000.,admission_ceiling=1000,policy_sha256='c'*64)
   self.assertEqual(done['status'],'DONE');self.assertEqual(done['send_entries'],4);self.assertEqual(calls,[evidence['ids'][-1]])

class ReadonlyOverlapReceipt(unittest.TestCase):
 def test_actual_readonly_receipt_counts_unique_rows_without_writable_lock(self):
  import importlib.util,os,errno
  from unittest.mock import patch
  spec=importlib.util.spec_from_file_location('apps.msp_marketplace_reports.overlap_receipt',ROOT/'scripts/finance_control/overlays/finance_receipts.py');receipt=importlib.util.module_from_spec(spec);spec.loader.exec_module(receipt)
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);answers=iter([(200,[row(11),row(30),row(20)]),(200,[row(21),row(30),row(31)]),(204,None)])
   for _ in range(3):run_one_step(root,'wb_laser_master',2026,601780521,1,lambda req:next(answers))
   original=os.open
   def readonly(path,flags,*args,**kwargs):
    if flags&(os.O_CREAT|os.O_WRONLY|os.O_RDWR|os.O_TRUNC|os.O_APPEND):raise OSError(errno.EROFS,'read only')
    return original(path,flags,*args,**kwargs)
   with patch.object(os,'open',readonly):out=receipt.report_receipt(root,'wb_laser_master',2026,601780521,1)
   self.assertTrue(out['verified'],out);self.assertEqual(out['rows'],5)

class ExpectedReportScope(unittest.TestCase):
 def test_expected_report_cannot_dispatch_another_report_or_discovery(self):
  import importlib.util
  spec=importlib.util.spec_from_file_location('scoped_control',ROOT/'scripts/finance_control/control.py');c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
  req={'nonce':32*'a','cabinet':'wb_laser_master','max_jobs':1,'expected_report_id':601780521};seen=[]
  out=c.process(req,lambda cabinet:{'report_id':601780521},lambda *args:seen.append('send') or {'status':'PASS'},lambda *args:None)
  self.assertEqual(seen,['send']);self.assertEqual(len(out),1)
  for candidate in ({'report_id':601780522},{'kind':'wb-discovery'}):
   with self.assertRaises(ValueError):c.process(req,lambda cabinet:candidate,lambda *args:self.fail('wrong report dispatched'),lambda *args:None)
  for bad in (True,0,-1,'601780521'):
   with self.assertRaises(ValueError):c.request({**req,'expected_report_id':bad})
  with self.assertRaises(ValueError):c.request({**req,'max_jobs':2})

class PackagedOrderRecovery(unittest.TestCase):
 def test_exact_package_replays_then_downloads_overlap_and_publishes_unique_rows(self):
  import subprocess,sys
  script=r'''
import ast,base64,sys,json,importlib.util
from pathlib import Path
from unittest.mock import patch
repo=Path(sys.argv[1]);tmp=Path(sys.argv[2]);bundle=repo/'docs/marketplace-reports/autonomous-control-20261105/install.py'
node=next(n for n in ast.parse(bundle.read_bytes()).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PACKAGE' for t in n.targets));package=ast.literal_eval(node.value)
for name,raw in package['files'].items():
 if name.startswith('apps/') or name in ('worker.py','rrd_profile.py'):
  target=tmp/'code'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(base64.b64decode(raw))
sys.path.insert(0,str(tmp/'code'))
from apps.msp_marketplace_reports import standalone_wb as s,wb_page_resume as p
from apps.msp_marketplace_reports.finance_receipts import report_receipt
spec=importlib.util.spec_from_file_location('exact_worker',tmp/'code/worker.py');worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
fixture=json.loads((repo/'tests/fixtures/wb_601780521_rrd_ids.json').read_text());old=json.loads((repo/'tests/fixtures/wb_601780521_hold.json').read_text())
plan={'schema':1,'cabinet':'wb_laser_master','year':2026,'report_id':601780521,'report_type':1,'max_send_entries':3}
def row(i):return {'reportId':601780521,'reportType':1,'rrdId':i,'amount':'1'}
root=tmp/'archive';root.mkdir();p.step_wb_detail(root,plan['cabinet'],2026,601780521,1,lambda req:(200,[row(fixture['cursor'])]))
stage=p._dir(root,plan['cabinet'],2026,601780521,1);prefix=(stage/'page-0.json').read_bytes()
raw={'schema':1,'report_id':601780521,'report_type':1,'cursor':fixture['cursor'],'next_rrd_id':fixture['ids'][-1],'rows':[row(i) for i in fixture['ids']]};raw['payload_sha256']=p._sha(p._canonical(raw));raw=p._canonical(raw)
pending=stage/('response-'+str(fixture['cursor'])+'.json');pending.write_bytes(raw)
folder=root/'.wb-executor';folder.mkdir();budget=folder/(s._digest(plan)+'.json');budget.write_bytes(s._encode({**old,'state_sha256':s._digest(old)}))
(folder/('control-'+32*'a'+'-events.jsonl')).write_text(''.join(json.dumps({'event':event,'plan':plan,**values})+'\n' for _ in range(3) for event,values in [('HTTP_DISPATCH_ATTEMPT',{}),('HTTP_RESPONSE',{'status':200})]))
auth={'schema':1,'plan_sha256':s._digest(plan),'code_sha256':s.code_digest(),'archive_root':str(root),'expires_epoch':9999999999,'owner_api_pilot_authorized':True,'shared_quota_verified':True,'conflicting_clients_excluded':True,'evidence_reference':'OFFLINE_EXACT_PACKAGE'}
now=[1000.];calls=[];last=fixture['ids'][-1];maximum=max(fixture['ids']);overlap=sorted(i for i in fixture['ids'] if i>last)
answers=iter([(200,[row(i) for i in overlap]+[row(maximum+1)]),(204,None)])
def sender(req):calls.append(req.body['rrdId']);return next(answers)
with patch.object(s,'CAPTURED_RESPONSE_SHA256',p._sha(raw)),patch.object(s,'CAPTURED_PREFIX_SHA256',p._sha(prefix)):
 result=worker.execute(root,plan,auth,lambda:sender,'e'*64,clock=lambda:now[0],sleep=lambda t:now.__setitem__(0,now[0]+t))
assert calls==[last,maximum+1],calls
assert result['report_detail_complete'],result
receipt=report_receipt(root,plan['cabinet'],2026,601780521,1)
assert receipt['verified'] and receipt['rows']==1002 and receipt['budget_entries']==5,receipt
assert (stage/'page-0.json').read_bytes()==prefix and pending.read_bytes()==raw
print(json.dumps({'status':'OFFLINE_PACKAGE_PASS','original_rows':1000,'overlap_rows':len(overlap),'unique_rows':receipt['rows'],'new_mock_http_calls':len(calls),'counter':receipt['budget_entries'],'replay_http_calls':0}))
'''
  with tempfile.TemporaryDirectory() as tmp:
   result=subprocess.run([sys.executable,'-I','-B','-c',script,str(ROOT),tmp],capture_output=True,text=True)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
   self.assertIn('OFFLINE_PACKAGE_PASS',result.stdout)
