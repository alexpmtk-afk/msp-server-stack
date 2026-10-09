import tempfile,unittest
from pathlib import Path
from apps.operator_layer.tasks import Journal
from apps.operator_layer.multipart import Collector
from apps.operator_layer.queue import TaskQueue,Worker

SCOPE=('default','owner','telegram:fixture','fixture-session')
PLAN=[dict(goal=f'block-{i}',acceptance=['verified'],allowed_mutations=[],expected_output='proof',dependencies=list(range(i)),readback='fixture proof',rollback='none') for i in range(3)]
class FixtureExecutor:
 def __init__(self):self.calls=[];self.records={};self.fail=False
 def execute(self,context,source,request_id,budget):
  self.calls.append((context,request_id));r={'kind':'complete','evidence':{'verified':True},'thread_id':'new-thread','updates':{'tests_status':'PASS'}};self.records[request_id]=r
  if self.fail:self.fail=False;raise TimeoutError('turn timed out after 600s')
  return r
 def readback(self,request_id,context):return self.records.get(request_id)
class QueueTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.j=Journal(Path(self.tmp.name)/'private');self.addCleanup(self.j.close)
  self.q=TaskQueue(self.j,allowed_scope=SCOPE);self.executor=FixtureExecutor()
  self.tid=self.j.create(SCOPE[2],'fixture',PLAN)
  self.spec={'task_id':self.tid,'request_id':'fixture:'+self.tid,'profile':SCOPE[0],'owner':SCOPE[1],'origin_chat':SCOPE[2],'session_key':SCOPE[3],'origin_platform':'telegram'}
 def submit(self):return self.q.submit(self.spec)
 def worker(self):return Worker(self.q,self.executor,lambda ctx,r:r.get('evidence',{}).get('verified') is True,worker_id='fixture-worker')
 def test_three_turns_done_origin_idempotent(self):
  self.submit();self.submit()
  w=self.worker()
  for _ in range(3):self.assertTrue(w.run_once())
  self.assertEqual(len(self.executor.calls),3)
  self.assertEqual(self.q.status(self.tid)['state'],'DONE');self.assertFalse(w.run_once())
  self.assertEqual(self.j.results()[0]['origin_chat'],SCOPE[2])
  self.assertEqual(self.j.db.execute('SELECT COUNT(*) FROM task_queue').fetchone()[0],1)
 def test_second_worker_and_live_expired_lease_fenced(self):
  self.submit()
  with self.q.claim('first') as claim:
   self.assertIsNotNone(claim)
   with TaskQueue(self.j,allowed_scope=SCOPE).claim('second') as other:self.assertIsNone(other)
   self.j.db.execute('UPDATE task_queue SET lease_expires=0');self.j.db.commit()
   with self.q.claim('third') as other:self.assertIsNone(other)
 def test_timeout_readback_reconciles_not_reexecutes(self):
  self.submit();self.executor.fail=True;w=self.worker()
  w.run_once();self.assertEqual(self.q.status(self.tid)['state'],'INTERRUPTED')
  self.assertFalse(w.run_once());self.assertEqual(len(self.executor.calls),1)
  self.assertTrue(w.reconcile(self.tid));self.assertEqual(self.q.status(self.tid)['state'],'WAITING_NEXT_TURN')
  w.run_once();self.assertEqual(len(self.executor.calls),2)
  self.assertEqual(self.executor.calls[1][0]['current_block'],1)
 def test_no_result_is_blocked_without_blind_retry(self):
  self.submit();self.executor.fail=True;w=self.worker();w.run_once();self.executor.records.clear()
  self.assertFalse(w.reconcile(self.tid));self.assertEqual(self.q.status(self.tid)['state'],'BLOCKED')
  self.assertFalse(w.run_once());self.assertEqual(len(self.executor.calls),1)
 def test_process_success_without_acceptance_is_not_done(self):
  self.submit();w=Worker(self.q,self.executor,lambda ctx,r:False,worker_id='w');w.run_once()
  self.assertEqual(self.q.status(self.tid)['state'],'BLOCKED')
  self.assertEqual(self.j.get(self.tid)['completed_blocks'],[])
 def test_incomplete_and_complete_multipart_submission(self):
  c=Collector(self.j);a=c.receive(SCOPE,'1',1,'TASK 1/2\nALPHA')
  self.assertEqual(c.recover(),[])
  self.assertFalse(self.worker().run_once())
  c.receive(SCOPE,'2',2,'TASK 2/2 END\nBRAVO');c.assemble(a['multipart_task_id'])
  self.q.enqueue_multipart(c);self.q.enqueue_multipart(c)
  self.assertEqual(self.j.db.execute('SELECT COUNT(*) FROM task_queue').fetchone()[0],1)
  self.assertEqual(c.status(a['multipart_task_id'])['status'],'DISPATCHED')
 def test_scope_and_flags_rejected(self):
  with self.assertRaises(ValueError):self.q.submit(self.spec|{'root_command':'whoami'})
  with self.assertRaises(ValueError):self.q.submit(self.spec|{'owner':'other'})
 def test_lease_recovery_without_execution(self):
  self.submit()
  with self.q.claim('dead') as claim:self.assertIsNotNone(claim)
  self.assertTrue(self.worker().run_once())
  self.assertEqual(len(self.executor.calls),1)
 def test_journal_checkpoint_after_unknown_blocks_resume(self):
  self.submit()
  self.worker().run_once()
  self.q.recover();self.assertEqual(self.q.status(self.tid)['state'],'WAITING_NEXT_TURN')

class QueueProcessTests(unittest.TestCase):
 def test_crash_after_lease_and_unknown_runtime_start(self):
  import subprocess,sys
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'private';j=Journal(root);self.addCleanup(j.close);q=TaskQueue(j,allowed_scope=SCOPE)
   tid=j.create(SCOPE[2],'fixture',PLAN)
   spec=dict(task_id=tid,request_id='crash:'+tid,profile=SCOPE[0],owner=SCOPE[1],origin_chat=SCOPE[2],session_key=SCOPE[3],origin_platform='telegram');q.submit(spec)
   prefix=f"from apps.operator_layer.tasks import Journal\nfrom apps.operator_layer.queue import TaskQueue,Worker\nimport os\nj=Journal({str(root)!r});q=TaskQueue(j,allowed_scope={SCOPE!r})\n"
   self.assertEqual(subprocess.run([sys.executable,'-c',prefix+"with q.claim('dead') as claim:\n os._exit(99)" ]).returncode,99)
   q.recover();self.assertEqual(q.status(tid)['state'],'QUEUED')
   crash=prefix+"class Ex:\n def execute(self,*a):os._exit(98)\nw=Worker(q,Ex(),lambda *a:True,worker_id='dead-runtime');w.run_once()"
   self.assertEqual(subprocess.run([sys.executable,'-c',crash]).returncode,98)
   q.recover();self.assertEqual(q.status(tid)['state'],'INTERRUPTED')
   ex=FixtureExecutor();w=Worker(q,ex,lambda *a:True,worker_id='new');self.assertFalse(w.run_once())
   self.assertFalse(w.reconcile(tid));self.assertEqual(ex.calls,[])
 def test_same_request_cannot_target_second_task(self):
  with tempfile.TemporaryDirectory() as tmp:
   j=Journal(Path(tmp)/'private');self.addCleanup(j.close);q=TaskQueue(j,allowed_scope=SCOPE)
   a=j.create(SCOPE[2],'one',PLAN);b=j.create(SCOPE[2],'two',PLAN)
   spec=dict(task_id=a,request_id='same',profile=SCOPE[0],owner=SCOPE[1],origin_chat=SCOPE[2],session_key=SCOPE[3],origin_platform='telegram');q.submit(spec)
   with self.assertRaises(ValueError):q.submit(spec|{'task_id':b})
