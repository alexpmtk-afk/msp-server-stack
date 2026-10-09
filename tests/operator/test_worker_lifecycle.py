import json,os,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from apps.operator_layer.tasks import Journal
from apps.operator_layer.queue import TaskQueue
from apps.operator_layer.worker_service import migrate, quarantine_probes, Outbox
from test_queue import SCOPE,PLAN
class LifecycleTests(unittest.TestCase):
 def test_migration_quarantine_outbox(self):
  with tempfile.TemporaryDirectory() as tmp:
   j=Journal(Path(tmp)/'private');self.addCleanup(j.close)
   migrate(j);migrate(j);quarantine_probes(j);quarantine_probes(j)
   self.assertEqual(j.db.execute('select count(*) from recovery_tombstones').fetchone()[0],5)
   q=TaskQueue(j,allowed_scope=SCOPE)
   tid='47fc93fd-4d76-4e9f-b34c-18c752762a1a'
   d=j.task_document(SCOPE[2],'old probe',PLAN,tid);j.save(d,'fixture')
   with self.assertRaises(ValueError):q.submit(dict(task_id=tid,request_id='old',profile=SCOPE[0],owner=SCOPE[1],origin_chat=SCOPE[2],session_key=SCOPE[3],origin_platform='telegram'))
   tid=j.create(SCOPE[2],'delivery',PLAN)
   j.db.execute('insert into outbox(task,origin,body) values (?,?,?)',(tid,SCOPE[2],'{}'));j.db.commit()
   o=Outbox(j);m=o.acquire();self.assertIsNotNone(m);self.assertIsNone(o.acquire())
   o.ack(m['task_id'],'local-receipt');self.assertIsNone(o.acquire())
 def test_worker_survives_launcher_exit_and_restart(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'private';j=Journal(root);migrate(j)
   config=Path(tmp)/'config.json';config.write_text(json.dumps(dict(root=str(root),scope=SCOPE,poll=.05,test_only=True)))
   worker=subprocess.Popen([sys.executable,'-m','apps.operator_layer.worker_service','--config',str(config),'--test-fixture'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   try:
    # A different process enqueues and exits; it does not create/own worker.
    code=f"from apps.operator_layer.tasks import Journal\nfrom apps.operator_layer.queue import TaskQueue\nj=Journal({str(root)!r});q=TaskQueue(j,allowed_scope={SCOPE!r});tid=j.create({SCOPE[2]!r},'fixture',{PLAN!r});q.submit(dict(task_id=tid,request_id='launcher:'+tid,profile={SCOPE[0]!r},owner={SCOPE[1]!r},origin_chat={SCOPE[2]!r},session_key={SCOPE[3]!r},origin_platform='telegram'));print(tid)"
    launch=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,check=True);tid=launch.stdout.strip()
    end=time.time()+10
    while time.time()<end and j.get(tid)['status']!='DONE':time.sleep(.05)
    self.assertEqual(j.get(tid)['status'],'DONE');self.assertIsNone(worker.poll())
    self.assertEqual(j.db.execute('select count(*) from task_executions where task=?',(tid,)).fetchone()[0],3)
    self.assertEqual(len(j.results()),1)
    worker.terminate();worker.wait(timeout=5)
    worker=subprocess.Popen([sys.executable,'-m','apps.operator_layer.worker_service','--config',str(config),'--test-fixture'])
    time.sleep(.2);self.assertEqual(j.db.execute('select count(*) from task_executions').fetchone()[0],3)
   finally:worker.terminate();worker.wait(timeout=5);j.close()

class AtomicTests(unittest.TestCase):
 def test_receipt_survives_failed_journal_transaction(self):
  from test_queue import FixtureExecutor
  from apps.operator_layer.queue import Worker
  from apps.operator_layer.hermes_executor import HermesExecutor
  with tempfile.TemporaryDirectory() as tmp:
   j=Journal(Path(tmp)/'private');self.addCleanup(j.close);q=TaskQueue(j,allowed_scope=SCOPE)
   tid=j.create(SCOPE[2],'atomic',PLAN[:1]);q.submit(dict(task_id=tid,request_id='atomic',profile=SCOPE[0],owner=SCOPE[1],origin_chat=SCOPE[2],session_key=SCOPE[3],origin_platform='telegram'))
   ex=FixtureExecutor();w=Worker(q,ex,lambda *a:True,worker_id='atomic')
   save=j.save
   def fail(d,k):
    save(d,k)
    if k=='checkpoint' and d['status']=='DONE':raise RuntimeError('journal commit crash')
   j.save=fail;w.run_once();j.save=save
   self.assertEqual(j.get(tid)['completed_blocks'],[])
   self.assertEqual(j.results(),[])
   self.assertTrue(w.reconcile(tid));self.assertEqual(q.status(tid)['state'],'DONE');self.assertEqual(len(ex.calls),1)
 def test_heartbeat_and_stale_fencing(self):
  with tempfile.TemporaryDirectory() as tmp:
   j=Journal(Path(tmp)/'private');self.addCleanup(j.close);q=TaskQueue(j,allowed_scope=SCOPE)
   tid=j.create(SCOPE[2],'fence',PLAN);q.submit(dict(task_id=tid,request_id='fence',profile=SCOPE[0],owner=SCOPE[1],origin_chat=SCOPE[2],session_key=SCOPE[3],origin_platform='telegram'))
   with q.claim('one') as c:
    c.heartbeat();self.assertIsNotNone(j.db.execute('select heartbeat_at from task_queue').fetchone()[0])
   with q.claim('two') as newer:
    with self.assertRaises(ValueError):c.fence()

 def test_soft_checkpoint_requeues_same_task_new_execution(self):
  from apps.operator_layer.queue import Worker
  from apps.operator_layer.tasks import Budget
  class Ex:
   calls=0
   def execute(self,c,s,r,b):
    self.calls+=1
    if self.calls==1:
     simulated=Budget(started=0,now=lambda:480)
     assert not simulated.can_start()
     return {'kind':'checkpoint','updates':{'next_action':'continue same block after soft boundary'}}
    return {'kind':'complete','evidence':{'verified':True},'thread_id':'replacement-thread'}
   def interrupt(self):pass
  with tempfile.TemporaryDirectory() as tmp:
   j=Journal(Path(tmp)/'private');self.addCleanup(j.close);q=TaskQueue(j,allowed_scope=SCOPE)
   tid=j.create(SCOPE[2],'soft',PLAN[:1]);q.submit(dict(task_id=tid,request_id='soft',profile=SCOPE[0],owner=SCOPE[1],origin_chat=SCOPE[2],session_key=SCOPE[3],origin_platform='telegram'))
   w=Worker(q,Ex(),lambda *a:True,worker_id='soft');w.run_once()
   self.assertEqual(q.status(tid)['state'],'WAITING_NEXT_TURN');self.assertEqual(j.get(tid)['current_block'],0)
   w.run_once();self.assertEqual(q.status(tid)['state'],'DONE')
   self.assertEqual(j.db.execute('select count(*) from task_executions').fetchone()[0],2)
