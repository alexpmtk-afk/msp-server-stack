import tempfile,unittest
from pathlib import Path
from apps.operator_layer.tasks import Journal,Budget
from apps.operator_layer.queue import TaskQueue,Worker
from apps.operator_layer.sandbox import SandboxAction
from test_queue import SCOPE,PLAN
class BoundaryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.j=Journal(Path(self.tmp.name)/'private');self.addCleanup(self.j.close)
  self.q=TaskQueue(self.j,allowed_scope=SCOPE);plan=[b|{'allowed_mutations':['sandbox_marker']} for b in PLAN[:2]]
  self.tid=self.j.create(SCOPE[2],'sandbox boundaries',plan);self.q.submit(dict(task_id=self.tid,request_id='boundary',profile=SCOPE[0],owner=SCOPE[1],origin_chat=SCOPE[2],session_key=SCOPE[3],origin_platform='telegram'))
  self.now=0
 def action(self,step=0):return SandboxAction(self.j.root,{'task_id':self.tid,'current_block':step,'block':self.j.get(self.tid)['plan'][step],'budget':Budget(started=0,now=lambda:self.now).context()},now=lambda:self.now)
 def test_a_soft_boundary_checkpoint_no_second_mutation(self):
  a=self.action();self.assertTrue(a.execute()['verified']);self.now=480;b=self.action(1)
  self.assertEqual(b.execute()['kind'],'checkpoint');self.assertIsNone(b.readback())
  class Ex:
   sandbox_enabled=True  # Explicit legacy marker-only permission.
   def execute(_,c,s,r,budget):return {'kind':'checkpoint','updates':{'next_action':'resume operation after soft boundary'}}
   def interrupt(_):pass
  w=Worker(self.q,Ex(),lambda *a:True,worker_id='deadline');w.run_once();self.assertEqual(self.q.status(self.tid)['state'],'WAITING_NEXT_TURN')
  self.now=0;self.assertTrue(self.action(1).execute()['verified']);self.assertFalse(self.action(1).execute()['execute'])
 def test_b_receipt_and_after_checkpoint(self):
  a=self.action();r=a.execute();self.assertTrue(r['verified']);self.assertEqual(a.readback()['mutation_count'],1)
  kinds=[r[0] for r in self.j.db.execute("select kind from events where task=?",(self.tid,))]
  self.assertIn('sandbox_before_operation',kinds);self.assertIn('sandbox_after_readback',kinds)
 def test_c_unknown_result_readback_before_any_repeat(self):
  a=self.action()
  def crash():raise RuntimeError('crash during operation')
  a.mutate=crash
  with self.assertRaises(RuntimeError):a.execute()
  self.assertEqual(self.j.db.execute('select state from operations').fetchone()[0],'UNKNOWN')
  self.assertEqual(self.action().execute()['state'],'RECONCILIATION_REQUIRED')
  self.assertEqual(self.j.db.execute('select state from operations').fetchone()[0],'UNKNOWN')
 def test_after_mutation_crash_readback_settles_without_repeat(self):
  a=self.action();finish=a.after_readback
  def crash(r):raise RuntimeError('crash after target commit')
  a.after_readback=crash
  with self.assertRaises(RuntimeError):a.execute()
  b=self.action();r=b.execute();self.assertTrue(r['verified']);self.assertFalse(r['execute']);self.assertEqual(b.readback()['mutation_count'],1)

 def test_worker_a_deferred_step_requeues_once(self):
  outer=self
  class Ex:
   sandbox_enabled=True
   def execute(_,context,source,request,budget):
    context['budget']=Budget(started=0,now=lambda:outer.now).context()
    a=SandboxAction(outer.j.root,context,now=lambda:outer.now)
    r=a.execute()
    if r.get('kind')=='checkpoint':return {'kind':'checkpoint','updates':{'next_action':'next budget'}}
    return {'kind':'complete','evidence':{'verified':r['verified']}}
   def interrupt(_):pass
  w=Worker(self.q,Ex(),lambda *a:True,worker_id='boundary-worker')
  w.run_once();self.now=480;w.run_once()
  self.assertEqual(self.q.status(self.tid)['state'],'WAITING_NEXT_TURN');self.assertEqual(self.j.get(self.tid)['current_block'],1)
  self.now=0;w.run_once();self.assertEqual(self.q.status(self.tid)['state'],'DONE');self.assertFalse(w.run_once())
  import sqlite3
  with sqlite3.connect(self.j.root/'sandbox.sqlite') as db:self.assertEqual(db.execute('select count(*) from markers').fetchone()[0],2)
 def test_unknown_execution_reconcile_reads_target_without_mutation(self):
  from apps.operator_layer.hermes_executor import HermesExecutor
  outer=self
  class Ex(HermesExecutor):
   calls=0
   def execute(_,context,source,request,budget):
    _.calls+=1
    a=SandboxAction(outer.j.root,context)
    def crash(receipt):raise RuntimeError('process lost after commit before receipt')
    a.after_readback=crash;a.execute()
  ex=Ex(self.j.root,profile='default',sandbox_enabled=True);w=Worker(self.q,ex,ex.verify,worker_id='recovery')
  w.run_once();self.assertEqual(self.q.status(self.tid)['state'],'INTERRUPTED');self.assertFalse(w.run_once())
  self.assertTrue(w.reconcile(self.tid));self.assertEqual(self.q.status(self.tid)['state'],'WAITING_NEXT_TURN');self.assertEqual(ex.calls,1)
  self.assertEqual(self.action().readback()['mutation_count'],1)
