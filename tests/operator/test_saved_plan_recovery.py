import fcntl,hashlib,json,os,tempfile,unittest
from pathlib import Path
from apps.operator_layer.tasks import Journal,Budget
from apps.operator_layer.queue import TaskQueue,Worker
from apps.operator_layer.multipart import Collector
from apps.operator_layer.saved_plan_recovery import inspect,apply
from test_queue import SCOPE,PLAN

class SavedPlanningRecoveryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name)/'journal'
  self.j=Journal(self.root)
  self.addCleanup(self.j.close)
  self.q=TaskQueue(self.j,allowed_scope=SCOPE)
  self.collector=Collector(self.j)
  m=self.collector.receive(SCOPE,'saved-original',None,'TASK 1/1 END\ncontrol read-only answer')
  self.collector.assemble(m['multipart_task_id'])
  self.q.enqueue_multipart(self.collector)
  self.tid=self.collector.status(m['multipart_task_id'])['durable_task_id']
  self.config={'root':str(self.root),'scope':SCOPE,'devexec_write_enabled':False}
  self.rid=hashlib.sha256(f'{self.tid}:-1:0'.encode()).hexdigest()
  context=Worker(self.q,None,None,worker_id='fixture')._context(self.tid,Budget())
  original={'schema_version':1,'kind':'plan','plan':{'blocks':PLAN[:1]},'evidence':['unverified note']}
  self.raw=json.dumps(original,sort_keys=True)
  self.sha=hashlib.sha256(self.raw.encode('utf-8')).hexdigest()
  with self.j.db:
   self.j.db.execute('CREATE TABLE IF NOT EXISTS runtime_receipts(request TEXT PRIMARY KEY,body TEXT NOT NULL)')
   self.j.db.execute('INSERT INTO runtime_receipts VALUES (?,?)',(self.rid,self.raw))
   self.j.db.execute("INSERT INTO task_executions(request,execution_id,task,block,state,result,context,started,error,reconciliation) VALUES (?,? ,?,-1,'UNKNOWN',NULL,?,0,'plan_required','BLOCKED_SCHEMA_MISMATCH')",(self.rid,self.rid,self.tid,json.dumps(context)))
   self.q._transition(self.tid,'BLOCKED',last_error='BLOCKED_SCHEMA_MISMATCH:plan_required')
  fd=os.open(self.root/'worker-service.lock',os.O_CREAT|os.O_EXCL|os.O_RDWR,0o600);os.close(fd)
 def test_preflight_is_readonly_and_preserves_saved_execution(self):
  before=list(self.j.db.execute('SELECT state,result FROM task_executions WHERE task=?',(self.tid,)))
  report=inspect(self.config,self.tid,self.rid,self.sha)
  self.assertTrue(report['validated'])
  self.assertEqual(report['mode'],'READ_ONLY')
  self.assertEqual(report['plan_blocks'],1)
  self.assertEqual(list(self.j.db.execute('SELECT state,result FROM task_executions WHERE task=?',(self.tid,))),before)
  self.assertEqual(self.q.status(self.tid)['state'],'BLOCKED')
 def test_strict_wrong_hash_or_execution_id_refused(self):
  with self.assertRaisesRegex(ValueError,'saved_receipt_hash_mismatch'):
   inspect(self.config,self.tid,self.rid,'0'*64)
  with self.assertRaisesRegex(ValueError,'execution_identity_or_status_mismatch'):
   inspect(self.config,self.tid,'a'*64,self.sha)
  self.assertEqual(self.q.status(self.tid)['state'],'BLOCKED')
 def test_changed_source_blocked_without_model_call(self):
  with self.j.db:self.j.db.execute("UPDATE multipart_parts SET text='changed fixture text' WHERE task=?",(self.collector._get(self.j.get(self.tid)['input_reference']['multipart_task_id'])['multipart_task_id'],))
  with self.assertRaisesRegex(ValueError,'multipart_parts_changed'):
   inspect(self.config,self.tid,self.rid,self.sha)
  self.assertEqual(self.j.db.execute("SELECT COUNT(*) FROM task_executions WHERE task=?",(self.tid,)).fetchone()[0],1)
 def test_refuses_other_queued_task_without_changing_either(self):
  other=self.j.create(SCOPE[2],'other task',PLAN[:1])
  self.q.submit(dict(task_id=other,request_id='other-queued',profile=SCOPE[0],owner=SCOPE[1],origin_chat=SCOPE[2],session_key=SCOPE[3],origin_platform='telegram'))
  with self.assertRaisesRegex(ValueError,'other_queue_work_in_progress'):
   inspect(self.config,self.tid,self.rid,self.sha)
  with self.assertRaisesRegex(ValueError,'other_queue_work_in_progress'):
   apply(self.config,self.tid,self.rid,self.sha)
  self.assertEqual(self.q.status(other)['state'],'QUEUED')
  self.assertEqual(self.q.status(self.tid)['state'],'BLOCKED')
  self.assertEqual(self.j.db.execute('SELECT COUNT(*) FROM task_executions WHERE task=?',(self.tid,)).fetchone()[0],1)
 def test_refuses_open_multipart_collection_without_closing_it(self):
  new=self.collector.receive(SCOPE,'another-open',None,'/task begin')
  self.assertEqual(new['status'],'COLLECTING')
  with self.assertRaisesRegex(ValueError,'multipart_ingress_in_progress'):
   inspect(self.config,self.tid,self.rid,self.sha)
  with self.assertRaisesRegex(ValueError,'multipart_ingress_in_progress'):
   apply(self.config,self.tid,self.rid,self.sha)
  self.assertEqual(self.collector.status(new['multipart_task_id'])['status'],'COLLECTING')
  self.assertEqual(self.q.status(self.tid)['state'],'BLOCKED')
 def test_worker_flock_denies_apply(self):
  fd=os.open(self.root/'worker-service.lock',os.O_RDWR)
  try:
   fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
   with self.assertRaisesRegex(ValueError,'worker_running_apply_forbidden'):
    apply(self.config,self.tid,self.rid,self.sha)
   self.assertEqual(self.q.status(self.tid)['state'],'BLOCKED')
  finally:
   fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)
 def test_offline_reconciles_original_receipt_only(self):
  report=apply(self.config,self.tid,self.rid,self.sha)
  self.assertEqual(report['mode'],'APPLIED_OFFLINE')
  self.assertEqual(report['task_status'],'WAITING_NEXT_TURN')
  self.assertEqual(self.q.status(self.tid)['state'],'WAITING_NEXT_TURN')
  d=self.j.get(self.tid)
  self.assertFalse(d['requires_decomposition'])
  self.assertEqual(d['plan'],PLAN[:1])
  self.assertEqual(d['completed_blocks'],[])
  self.assertNotEqual(d['status'],'DONE')
  rows=self.j.db.execute('SELECT request,block,state FROM task_executions WHERE task=?',(self.tid,)).fetchall()
  self.assertEqual(rows,[(self.rid,-1,'VERIFIED')])
  self.assertEqual(self.j.db.execute('SELECT body FROM runtime_receipts WHERE request=?',(self.rid,)).fetchone()[0],self.raw)
  self.assertEqual(self.j.db.execute('SELECT COUNT(*) FROM outbox WHERE task=?',(self.tid,)).fetchone()[0],0)
  with self.assertRaisesRegex(ValueError,'task_not_expected_blocked_planning_state'):
   apply(self.config,self.tid,self.rid,self.sha)
