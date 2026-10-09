import copy,tempfile,unittest,json
from pathlib import Path
from apps.operator_layer.tasks import Journal
from apps.operator_layer.queue import TaskQueue,Worker
from apps.operator_layer.receipt_schema import normalize_receipt
from test_queue import SCOPE,PLAN,FixtureExecutor
LEGACY={'kind':'plan','plan':PLAN,'updates':{'mutations_performed':False,'plan_approval':'Pending','planning_only':True,'source_instructions_executed':False,'test_result':'Not determined'}}
class ReceiptTests(unittest.TestCase):
 def test_legacy_updates_explicit_metadata_not_checkpoint(self):
  r=normalize_receipt(LEGACY);self.assertEqual(r['schema_version'],1);self.assertEqual(r['updates'],{})
  self.assertEqual(r['evidence']['planning_metadata'],LEGACY['updates']);self.assertEqual(LEGACY['updates']['plan_approval'],'Pending')
 def test_unknown_field_rejected(self):
  with self.assertRaises(ValueError):normalize_receipt(LEGACY|{'surprise':1})
  with self.assertRaises(ValueError):normalize_receipt(LEGACY|{'updates':{'unexpected':1}})
 def test_version_mismatch_rejected(self):
  with self.assertRaises(ValueError):normalize_receipt(LEGACY|{'schema_version':2})
 def test_invalid_checkpoint_rejected_deterministically(self):
  for _ in range(2):
   with self.assertRaisesRegex(ValueError,'checkpoint_update_type'):normalize_receipt({'kind':'checkpoint','updates':{'next_action':[]}})
 def test_bad_task_isolated_good_task_runs_no_reconciliation_loop(self):
  with tempfile.TemporaryDirectory() as tmp:
   j=Journal(Path(tmp)/'private');self.addCleanup(j.close);q=TaskQueue(j,allowed_scope=SCOPE)
   tids=[]
   for n in range(2):
    tid=j.create(SCOPE[2],str(n),PLAN[:1]);tids.append(tid);q.submit(dict(task_id=tid,request_id=str(n),profile=SCOPE[0],owner=SCOPE[1],origin_chat=SCOPE[2],session_key=SCOPE[3],origin_platform='telegram'))
   class Ex(FixtureExecutor):
    def execute(self,*a):
     r=super().execute(*a)
     if len(self.calls)==1:r['updates']={'unknown':True}
     return r
   ex=Ex();w=Worker(q,ex,lambda *a:True,worker_id='worker');w.run_once()
   self.assertEqual(q.status(tids[0])['state'],'BLOCKED');self.assertEqual(j.get(tids[0])['last_error'],'BLOCKED_SCHEMA_MISMATCH:unknown_checkpoint_update')
   w.run_once();self.assertEqual(q.status(tids[1])['state'],'DONE');self.assertFalse(w.run_once());self.assertEqual(len(ex.calls),2)
 def test_saved_plan_normalizes_one_execution_without_model_call(self):
  from apps.operator_layer.hermes_executor import HermesExecutor
  with tempfile.TemporaryDirectory() as tmp:
   j=Journal(Path(tmp)/'private');self.addCleanup(j.close);q=TaskQueue(j,allowed_scope=SCOPE)
   from apps.operator_layer.multipart import Collector
   c=Collector(j);m=c.receive(SCOPE,'saved-fixture',None,'TASK 1/1 END\nfixture');c.assemble(m['multipart_task_id']);q.enqueue_multipart(c);tid=c.status(m['multipart_task_id'])['durable_task_id']
   class Ex(FixtureExecutor):
    def execute(self,ctx,source,rid,budget):
     self.calls.append((ctx,rid));self.records[rid]=copy.deepcopy(LEGACY);raise TimeoutError('after receipt')
   ex=Ex();w=Worker(q,ex,lambda *a:True,worker_id='saved');w.run_once();self.assertTrue(w.reconcile(tid))
   self.assertEqual(len(ex.calls),1);self.assertEqual(j.db.execute('select count(*) from task_executions').fetchone()[0],1)
   self.assertEqual(q.status(tid)['state'],'WAITING_NEXT_TURN');self.assertEqual(j.get(tid)['last_checkpoint']['schema_version'],1)
   self.assertEqual(json.loads(j.db.execute('select raw_body from receipt_normalizations').fetchone()[0]),LEGACY)
 def test_linked_status_after_collection_dispatched(self):
  from apps.operator_layer.production import receive
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'private';config={'root':str(root),'scope':SCOPE}
   r=receive(config,'fixture-only',None,'TASK 1/1 END\nfixture')
   status=receive(config,'status',None,'/task status')
   self.assertEqual(status['durable_task_id'],r['durable_task_id']);self.assertEqual(status['task_status'],'QUEUED');self.assertFalse(status['final_result_ready']);self.assertEqual(status['execution_count'],0);self.assertEqual(status['delivery_count'],0);self.assertFalse(status['duplicate_execution'])
 def test_authoritative_audit_finishes_same_execution_without_model(self):
  from apps.operator_layer.multipart import Collector
  from apps.operator_layer.multipart_audit import finish_existing_audit
  with tempfile.TemporaryDirectory() as tmp:
   j=Journal(Path(tmp)/'private');self.addCleanup(j.close);q=TaskQueue(j,allowed_scope=SCOPE);c=Collector(j)
   for n,k in enumerate(['ALPHA','BRAVO','CHARLIE'],1):m=c.receive(SCOPE,str(n),None,f"TASK {n}/3"+(' END' if n==3 else '')+f"\nE2E-MULTIPART-20261007-{k}-1000")
   c.assemble(m['multipart_task_id']);q.enqueue_multipart(c);tid=c.status(m['multipart_task_id'])['durable_task_id']
   class Ex(FixtureExecutor):
    def execute(self,ctx,source,rid,budget):
     self.calls.append((ctx,rid));r=copy.deepcopy(LEGACY);r['plan']=[b|{'goal':'Verify Multipart Collector E2E'} for b in PLAN[:2]];self.records[rid]=r;return r
   ex=Ex();w=Worker(q,ex,lambda *a:True,worker_id='audit');w.run_once();rid=ex.calls[0][1]
   proof=finish_existing_audit(j,q,tid,rid);finish_existing_audit(j,q,tid,rid)
   self.assertTrue(proof['verified']);self.assertEqual(q.status(tid)['state'],'DONE');self.assertEqual(len(ex.calls),1)
   self.assertEqual(j.db.execute('select count(*) from task_executions').fetchone()[0],1);self.assertEqual(len(j.results()),1)
 def test_bad_receipt_worker_process_survives_and_restart_skips_blocked(self):
  import subprocess,sys
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'private';j=Journal(root);self.addCleanup(j.close);q=TaskQueue(j,allowed_scope=SCOPE)
   for n in range(2):
    tid=j.create(SCOPE[2],str(n),PLAN[:1]);q.submit(dict(task_id=tid,request_id=str(n),profile=SCOPE[0],owner=SCOPE[1],origin_chat=SCOPE[2],session_key=SCOPE[3],origin_platform='telegram'))
   code=f"from apps.operator_layer.tasks import Journal\nfrom apps.operator_layer.queue import TaskQueue,Worker\nj=Journal({str(root)!r});q=TaskQueue(j,allowed_scope={SCOPE!r})\nclass Ex:\n calls=0\n def execute(self,*a):\n  self.calls+=1\n  return {{'kind':'complete','evidence':{{'verified':True}},'updates':{{'unknown':True}}}} if self.calls==1 else {{'kind':'complete','evidence':{{'verified':True}}}}\n def interrupt(self):pass\nex=Ex();w=Worker(q,ex,lambda *a:True,worker_id='child');w.run_once();w.run_once();assert ex.calls==2;assert not w.run_once();j.close()"
   subprocess.run([sys.executable,'-c',code],check=True)
   restart=f"from apps.operator_layer.tasks import Journal\nfrom apps.operator_layer.queue import TaskQueue,Worker\nj=Journal({str(root)!r});q=TaskQueue(j,allowed_scope={SCOPE!r})\nclass Ex:\n def execute(self,*a):raise AssertionError('unexpected execution')\nw=Worker(q,Ex(),lambda *a:True,worker_id='restart');assert not w.run_once();j.close()"
   subprocess.run([sys.executable,'-c',restart],check=True);self.assertEqual(j.db.execute('select count(*) from task_executions').fetchone()[0],2)
