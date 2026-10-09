import tempfile,unittest
from pathlib import Path
from apps.operator_layer.tasks import Journal
from apps.operator_layer.multipart import Collector

SCOPE=('default','owner','telegram:fixture','session-fixture')
class MultipartTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name)/'private';self.j=Journal(self.root);self.addCleanup(self.j.close)
  self.c=Collector(self.j)
 def send(self,text,n,at=None):return self.c.receive(SCOPE,str(n),n,text,received_at=at)
 def tasks(self):return self.j.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]
 def test_numbered_pauses_restart_and_checkpoint_boundary(self):
  a=self.send('TASK 1/3\nALPHA',1,100)
  self.assertTrue(a['consumed']);self.assertEqual(self.tasks(),0)
  self.c=Collector(self.j)
  b=self.send('TASK 2/3\nBRAVO',2,120)
  self.assertEqual(a['multipart_task_id'],b['multipart_task_id']);self.assertEqual(self.tasks(),0)
  z=self.send('TASK 3/3 END\nCHARLIE',3,140)
  self.assertEqual(z['status'],'COMPLETE')
  self.c.assemble(z['multipart_task_id'])
  item=self.c.pending()[0];tid=item['durable_task_id'];text=self.c.input_for(tid)
  self.assertEqual(text,'ALPHA\n\nBRAVO\n\nCHARLIE');self.assertEqual(self.tasks(),1)
  with self.j.turn(tid,'thread-a') as t:t.checkpoint('tests',{'tests_status':'PASS'})
  with self.j.turn(tid,'thread-b') as t:
   self.assertTrue(t.context()['recovery_required'])
   t.checkpoint('recovery',{'next_action':'plan collected input'})
  self.assertEqual(self.c.input_for(tid),text)
 def test_missing_out_of_order_and_no_end(self):
  a=self.send('TASK 1/3\nA',1)
  b=self.send('TASK 3/3 END\nC',3)
  self.assertEqual(b['missing_parts'],[2]);self.assertEqual(self.tasks(),0)
  z=self.send('TASK 2/3\nB',2);self.assertEqual(z['status'],'COMPLETE')
  self.c.assemble(a['multipart_task_id']);self.assertEqual(self.c.input_for(self.c.pending()[0]['durable_task_id']),'A\n\nB\n\nC')
 def test_duplicates_conflicts(self):
  a=self.send('TASK 1/3\nA',1);self.send('TASK 2/3\nB',2)
  self.send('TASK 2/3\nB',2);self.send('TASK 2/3\nB',22)
  z=self.send('TASK 2/3\nDIFFERENT',23)
  self.assertEqual(z['status'],'ERROR');self.send('TASK 3/3 END\nC',3)
  with self.assertRaises(ValueError):self.c.assemble(a['multipart_task_id'])
  self.assertEqual(self.tasks(),0)
 def test_begin_end_cancel_and_repeat_end(self):
  self.send('/task begin',1)
  for n in (2,3,4):self.send(f'part-{n}',n)
  a=self.send('/task end',5);self.c.assemble(a['multipart_task_id'])
  self.send('/task end',5);self.send('/task end',6)
  self.c.assemble(a['multipart_task_id']);self.assertEqual(self.tasks(),1)
  req=self.c.prepare_dispatch(a['multipart_task_id']);self.c.confirm_dispatch(a['multipart_task_id'],{'request_id':req['request_id'],'task_id':req['task_id'],'accepted':True})
  self.send('/task begin',7);self.send('DO NOT EXECUTE',8);z=self.send('/task cancel',9)
  self.assertEqual(z['status'],'CANCELLED');self.assertEqual(self.tasks(),1)
 def test_normal_passthrough_and_no_second_collection(self):
  self.assertFalse(self.send('hello',1)['consumed'])
  self.send('/task begin',2)
  self.assertEqual(self.send('/task begin',3)['reason'],'collection_already_open')
  self.assertEqual(self.send('TASK 1/2\nother',4)['reason'],'mode_conflict')
  self.assertEqual(self.send('/task status',5)['status'],'COLLECTING')
 def test_recovery_exactly_once_and_scope(self):
  a=self.send('TASK 1/1 END\nA',1)
  for _ in range(3):self.c.assemble(a['multipart_task_id'])
  self.assertEqual(self.tasks(),1)
  self.assertEqual(len(self.c.pending()),1)
  self.assertFalse(self.c.receive(('default','someone-else','telegram:fixture','session-fixture'),'2',2,'hello')['consumed'])
 def test_expiration_never_executes(self):
  a=self.send('TASK 1/2\nA',1)
  self.c.expire(a['multipart_task_id'])
  self.assertEqual(self.c.status(a['multipart_task_id'])['status'],'EXPIRED')
  self.assertEqual(self.tasks(),0)
 def test_terminal_number_without_end_and_update_replay(self):
  a=self.send('TASK 1/2\nA',1);self.send('TASK 2/2\nB',2)
  self.assertEqual(self.c.status(a['multipart_task_id'])['status'],'COLLECTING')
  self.send('TASK 2/2 END\nB',3)
  self.assertEqual(self.c.status(a['multipart_task_id'])['status'],'COMPLETE')
  self.c.assemble(a['multipart_task_id'])
  self.assertTrue(self.send('TASK 1/2\nA',1)['consumed']);self.assertEqual(self.tasks(),1)
if __name__=='__main__':unittest.main()

class DispatchTests(unittest.TestCase):
 setUp=MultipartTests.setUp
 send=MultipartTests.send
 tasks=MultipartTests.tasks
 def test_unknown_dispatch_requires_readback(self):
  a=self.send('TASK 1/1 END\nALPHA',1);self.c.assemble(a['multipart_task_id'])
  req=self.c.prepare_dispatch(a['multipart_task_id'])
  self.assertEqual(req['operation'],'submit_operator_task')
  self.assertEqual(self.c.status(a['multipart_task_id'])['status'],'ASSEMBLED')
  with self.assertRaises(ValueError):self.c.prepare_dispatch(a['multipart_task_id'])
  receipt=dict(request_id=req['request_id'],task_id=req['task_id'],accepted=True)
  self.c.confirm_dispatch(a['multipart_task_id'],receipt)
  self.c.confirm_dispatch(a['multipart_task_id'],receipt)
  self.assertEqual(self.c.status(a['multipart_task_id'])['status'],'DISPATCHED')
  self.assertEqual(self.c.pending(),[])
 def test_cancel_or_conflict_after_assembly_stops_pending_dispatch(self):
  a=self.send('TASK 1/1 END\nA',1);self.c.assemble(a['multipart_task_id'])
  z=self.send('/task cancel',2);self.assertEqual(z['status'],'CANCELLED')
  self.assertEqual(self.c.pending(),[])
  with self.assertRaises(ValueError):
   with self.j.turn(self.c.status(a['multipart_task_id'])['durable_task_id'],'cancelled-executor'):pass
  with self.assertRaises(ValueError):self.c.prepare_dispatch(a['multipart_task_id'])
 def test_manual_late_input_cannot_be_silently_lost(self):
  self.send('/task begin',1);self.send('A',2);a=self.send('/task end',3)
  self.c.assemble(a['multipart_task_id'])
  self.assertEqual(self.send('late part',4)['reason'],'collection_already_complete')
 def test_receipt_invalid_does_not_mark_dispatched(self):
  a=self.send('TASK 1/1 END\nA',1);self.c.assemble(a['multipart_task_id']);self.c.prepare_dispatch(a['multipart_task_id'])
  with self.assertRaises(ValueError):self.c.confirm_dispatch(a['multipart_task_id'],{'accepted':True,'task_id':'other','request_id':'bad'})
  self.assertEqual(self.c.status(a['multipart_task_id'])['status'],'ASSEMBLED')

class ProcessTests(unittest.TestCase):
 def test_process_restart_and_atomic_assembly_crash(self):
  import subprocess,sys
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'private';j=Journal(root);self.addCleanup(j.close);c=Collector(j)
   a=c.receive(SCOPE,'1',1,'TASK 1/3\nALPHA',100)
   code=f"from apps.operator_layer.tasks import Journal\nfrom apps.operator_layer.multipart import Collector\nimport os\nj=Journal({str(root)!r});c=Collector(j);scope={SCOPE!r}\nc.receive(scope,'2',2,'TASK 2/3\\nBRAVO',120)\nc.receive(scope,'3',3,'TASK 3/3 END\\nCHARLIE',140)\nos._exit(77)"
   self.assertEqual(subprocess.run([sys.executable,'-c',code]).returncode,77)
   self.assertEqual(c.status(a['multipart_task_id'])['status'],'COMPLETE')
   # Kill the worker inside the same transaction AFTER the task INSERT.
   crash=f"from apps.operator_layer.tasks import Journal\nfrom apps.operator_layer.multipart import Collector\nimport os\nj=Journal({str(root)!r});c=Collector(j)\nj.db.create_function('crash',0,lambda:os._exit(78))\nj.db.execute(\"CREATE TEMP TRIGGER crash_insert AFTER INSERT ON tasks BEGIN SELECT crash(); END\")\nc.assemble({a['multipart_task_id']!r})"
   self.assertEqual(subprocess.run([sys.executable,'-c',crash]).returncode,78)
   self.assertEqual(j.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0],0)
   for _ in range(3):c.recover()
   self.assertEqual(j.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0],1)
   self.assertEqual(len(c.pending()),1)
   tid=c.pending()[0]['durable_task_id']
   self.assertEqual(c.input_for(tid),'ALPHA\n\nBRAVO\n\nCHARLIE')
 def test_assembled_task_decomposes_then_three_separate_turns(self):
  from test_tasks import PLAN
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'private';j=Journal(root);self.addCleanup(j.close);c=Collector(j)
   a=c.receive(SCOPE,'1',1,'TASK 1/1 END\nwhole task');c.assemble(a['multipart_task_id'])
   tid=c.pending()[0]['durable_task_id']
   with j.turn(tid,'planning') as t:
    with self.assertRaises(ValueError):t.complete({'plan_approved':True})
    t.set_execution_plan(PLAN,{'input_hash':t.context()['input_reference']['assembled_hash']})
   for n in range(3):
    other=Journal(root)
    try:
     with other.turn(tid,f'thread-{n}') as t:
      self.assertEqual(t.context()['current_block'],n);t.complete({'verified':True})
    finally:other.close()
   self.assertEqual(j.get(tid)['status'],'DONE')

class PauseAndRaceTests(unittest.TestCase):
 def test_real_pause_over_ten_seconds_no_early_task(self):
  import time
  with tempfile.TemporaryDirectory() as tmp:
   j=Journal(Path(tmp)/'private');self.addCleanup(j.close);c=Collector(j)
   a=c.receive(SCOPE,'1',1,'TASK 1/3\nALPHA')
   time.sleep(10.1)  # Acceptance fixture wait, not an execution-timeout workaround.
   self.assertEqual(j.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0],0)
   c.receive(SCOPE,'2',2,'TASK 2/3\nBRAVO')
   self.assertEqual(j.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0],0)
   c.receive(SCOPE,'3',3,'TASK 3/3 END\nCHARLIE');c.assemble(a['multipart_task_id'])
   self.assertEqual(j.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0],1)
 def test_concurrent_recovery_creates_one_task(self):
  import subprocess,sys
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)/'private';j=Journal(root);self.addCleanup(j.close);c=Collector(j)
   c.receive(SCOPE,'1',1,'TASK 1/1 END\nALPHA')
   code=f"from apps.operator_layer.tasks import Journal\nfrom apps.operator_layer.multipart import Collector\nj=Journal({str(root)!r});c=Collector(j);c.recover();j.close()"
   workers=[subprocess.Popen([sys.executable,'-c',code]) for _ in range(3)]
   self.assertEqual([p.wait() for p in workers],[0,0,0])
   self.assertEqual(j.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0],1)
