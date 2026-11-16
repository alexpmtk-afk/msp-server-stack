import json
import tempfile
import unittest
from pathlib import Path
from apps.operator_layer.tasks import Journal
from apps.operator_layer.worker_service import migrate

PLAN=[dict(goal='Synthetic review',acceptance=['verified'],allowed_mutations=[],expected_output='Fixture evidence',dependencies=[],readback='Fixture readback',rollback='No mutation')]

class AdmissionTests(unittest.TestCase):
 def test_stale_journal_save_cannot_recreate_tombstoned_task(self):
  with tempfile.TemporaryDirectory() as tmp:
   j=Journal(Path(tmp)/'journal');migrate(j)
   tid=j.create('telegram:fixture','Synthetic task',PLAN);stale=j.get(tid)
   with j.db:
    j.db.execute('INSERT INTO recovery_tombstones VALUES(?,?,?,?,?,0,?)',(tid,'ARCHIVED','Fixture','fixture','owner-retirement','ARCHIVED_NO_RETRY'))
    j.db.execute('DELETE FROM tasks WHERE id=?',(tid,))
   with self.assertRaisesRegex(ValueError,'task_retired'):
    j.save(stale,'recovery')
   self.assertIsNone(j.db.execute('SELECT id FROM tasks WHERE id=?',(tid,)).fetchone())
   j.close()

class ArchiveTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name)/'journal';self.j=Journal(self.root);self.addCleanup(self.j.close);migrate(self.j)
  (self.root/'worker-service.lock').touch(mode=0o600)
  self.ids=[self.j.create('telegram:fixture','Synthetic blocked task',PLAN) for _ in range(2)]
  for tid in self.ids:
   body=self.j.get(tid);body['status']='BLOCKED';self.j.save(body,'dependency_blocked')
  self.done=self.j.create('telegram:fixture','Synthetic completed task',PLAN)
  with self.j.turn(self.done,'fixture') as turn:turn.complete({'verified':True})
  self.archive=Path(self.tmp.name)/'archive'
 def run_archive(self,apply=False):
  from apps.operator_layer.task_retirement import retire
  return retire(self.root,self.ids,self.archive,apply=apply)
 def test_read_only_preflight_then_archive_preserves_done_delivery_and_history(self):
  before=self.j.db.execute('SELECT * FROM outbox').fetchall()
  history=self.j.db.execute('SELECT * FROM events').fetchall()
  self.assertEqual(self.run_archive()['status'],'PREFLIGHT_PASS')
  self.assertFalse(self.archive.exists())
  result=self.run_archive(True);self.assertEqual(result['status'],'ARCHIVED')
  self.assertEqual(self.j.db.execute('SELECT * FROM outbox').fetchall(),before)
  self.assertEqual(self.j.get(self.done)['status'],'DONE')
  for tid in self.ids:
   self.assertEqual(self.j.get(tid)['status'],'ARCHIVED')
   with self.assertRaisesRegex(ValueError,'task_retired'):
    with self.j.turn(tid,'retry'):pass
  self.assertEqual(self.j.unfinished(),[])
  self.assertEqual(self.j.db.execute('SELECT * FROM events ORDER BY seq').fetchall()[:len(history)],history)
  self.assertEqual(self.j.db.execute('PRAGMA integrity_check').fetchone(),('ok',))
  self.assertEqual(self.run_archive(True)['status'],'ALREADY_ARCHIVED')
 def test_missing_id_aborts_entire_batch(self):
  self.ids.append('00000000-0000-4000-8000-000000000000')
  with self.assertRaisesRegex(ValueError,'unknown_task'):self.run_archive(True)
  self.assertTrue(all(self.j.get(t)['status']=='BLOCKED' for t in self.ids[:2]))
  self.assertFalse(self.archive.exists())
 def test_active_worker_refused(self):
  import fcntl
  with (self.root/'worker-service.lock').open('r+') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
   with self.assertRaisesRegex(ValueError,'worker_active'):self.run_archive(True)
 def test_archive_destination_failure_preserves_tasks(self):
  self.archive.write_text('occupied')
  with self.assertRaises(FileExistsError):self.run_archive(True)
  self.assertTrue(all(self.j.get(t)['status']=='BLOCKED' for t in self.ids))
 def test_existing_execution_refused(self):
  with self.j.db:self.j.db.execute('INSERT INTO task_executions(request,task,block,state,context,started) VALUES(?,?,0,?, ?,0)',('fixture-request',self.ids[0],'UNKNOWN','{}'))
  with self.assertRaisesRegex(ValueError,'execution_present'):self.run_archive(True)
 def test_dependent_task_refused(self):
  tid=self.j.create('telegram:fixture','Synthetic reference '+self.ids[0],PLAN)
  with self.assertRaisesRegex(ValueError,'dependent_task'):self.run_archive(True)
 def test_queued_and_journal_only_tasks_retire_without_other_queue_changes(self):
  from apps.operator_layer.queue import TaskQueue
  q=TaskQueue(self.j,allowed_scope=('fixture','fixture','telegram:fixture','fixture'))
  with self.j.db:
   self.j.db.execute("INSERT INTO task_queue(task,request,scope,state,updated) VALUES(?,?,?,'BLOCKED',0)",(self.ids[0],'fixture-queued',q._scope_json()))
  self.run_archive(True)
  self.assertEqual(self.j.db.execute('SELECT count(*) FROM task_queue').fetchone()[0],0)
  spec=dict(task_id=self.ids[0],request_id='fixture-retry',profile='fixture',owner='fixture',origin_chat='telegram:fixture',session_key='fixture',origin_platform='telegram')
  with self.assertRaisesRegex(ValueError,'probe_retry_forbidden'):q.submit(spec)
  with q.claim('fixture-worker',self.ids[0],recovery=True) as claim:self.assertIsNone(claim)
  with self.assertRaisesRegex(ValueError,'task_retired'):q._transition(self.ids[0],'QUEUED')
 def test_sqlite_failure_rolls_back_entire_batch_and_preserves_backup(self):
  import sqlite3
  with self.j.db:
   self.j.db.execute("CREATE TRIGGER reject_retirement BEFORE INSERT ON recovery_tombstones WHEN NEW.task_id='"+self.ids[1]+"' BEGIN SELECT RAISE(ABORT,'fixture_abort'); END")
  with self.assertRaisesRegex(sqlite3.IntegrityError,'fixture_abort'):self.run_archive(True)
  self.assertTrue(all(self.j.get(t)['status']=='BLOCKED' for t in self.ids))
  self.assertEqual(self.j.db.execute("SELECT count(*) FROM recovery_tombstones WHERE probe_marker='owner-retirement'").fetchone()[0],0)
  self.assertTrue((self.archive/'journal-before.sqlite').is_file())
 def test_archive_write_error_does_not_modify_database(self):
  from unittest.mock import patch
  with patch('apps.operator_layer.task_retirement._write_private',side_effect=OSError('fixture_disk_full')):
   with self.assertRaisesRegex(OSError,'fixture_disk_full'):self.run_archive(True)
  self.assertTrue(all(self.j.get(t)['status']=='BLOCKED' for t in self.ids))
 def test_live_task_lock_refused(self):
  import fcntl
  with (self.root/(self.ids[0]+'.lock')).open('w') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
   with self.assertRaisesRegex(ValueError,'task_active'):self.run_archive(True)
 def test_done_task_refused(self):
  self.ids=[self.done]
  with self.assertRaisesRegex(ValueError,'task_not_idle_blocked'):self.run_archive(True)
 def test_symlink_database_refused(self):
  db=self.root/'journal.sqlite';db.rename(self.root/'original.sqlite');db.symlink_to(self.root/'original.sqlite')
  with self.assertRaisesRegex(ValueError,'unsafe_file'):self.run_archive(True)
 def test_subprocess_crash_after_partial_insert_rolls_back_and_retry_is_safe(self):
  import subprocess,sys,sqlite3
  with self.j.db:
   self.j.db.execute("CREATE TRIGGER crash_retirement BEFORE INSERT ON recovery_tombstones WHEN NEW.task_id='"+self.ids[1]+"' BEGIN SELECT fixture_crash(); END")
  checkout=Path(__file__).resolve().parents[2]
  code="""import sys,sqlite3,os,json
sys.path.insert(0,sys.argv[1])
original=sqlite3.connect
def connect(*args,**kwargs):
 db=original(*args,**kwargs);db.create_function('fixture_crash',0,lambda:os._exit(77));return db
sqlite3.connect=connect
from apps.operator_layer.task_retirement import retire
retire(sys.argv[2],json.loads(sys.argv[3]),sys.argv[4],apply=True)
"""
  p=subprocess.run([sys.executable,'-I','-B','-c',code,str(checkout),str(self.root),json.dumps(self.ids),str(self.archive)])
  self.assertEqual(p.returncode,77)
  self.assertTrue(all(self.j.get(t)['status']=='BLOCKED' for t in self.ids))
  self.assertEqual(self.j.db.execute('PRAGMA integrity_check').fetchone(),('ok',))
  self.assertTrue((self.archive/'journal-before.sqlite').exists())
  with self.j.db:self.j.db.execute('DROP TRIGGER crash_retirement')
  self.archive=Path(self.tmp.name)/'retry-archive'
  self.assertEqual(self.run_archive(True)['status'],'ARCHIVED')
 def test_legacy_removed_task_remains_fenced_for_direct_journal_and_queue(self):
  import sqlite3
  from apps.operator_layer.queue import TaskQueue,Worker
  from apps.operator_layer.tasks import Turn,Budget
  stale=self.j.get(self.ids[0]);self.run_archive(True)
  with self.j.db:self.j.db.execute('DELETE FROM tasks WHERE id=?',(self.ids[0],))
  with self.assertRaisesRegex(ValueError,'task_retired'):self.j.save(stale,'recovery')
  with self.assertRaisesRegex(ValueError,'task_retired'):
   with self.j.turn(self.ids[0],'fixture'):pass
  with self.assertRaisesRegex(ValueError,'task_retired'):Turn(self.j,stale,'fixture',Budget())
  q=TaskQueue(self.j,allowed_scope=('fixture','fixture','telegram:fixture','fixture'))
  class NeverExecute:
   def execute(self,*args):raise AssertionError('model_called')
  self.assertFalse(Worker(q,NeverExecute(),lambda *_:True,worker_id='fixture').reconcile(self.ids[0]))
 def test_operations_and_outbox_are_never_retired(self):
  with self.j.db:self.j.db.execute('INSERT INTO operations VALUES(?,?,0,?,?,NULL)',('fixture-op',self.ids[0],'fixture','APPLIED'))
  with self.assertRaisesRegex(ValueError,'operation_present'):self.run_archive(True)
  with self.j.db:
   self.j.db.execute('DELETE FROM operations WHERE id=?',('fixture-op',))
   self.j.db.execute('INSERT INTO outbox(task,origin,body) VALUES(?,?,?)',(self.ids[0],'telegram:fixture','{}'))
  with self.assertRaisesRegex(ValueError,'outbox_present'):self.run_archive(True)
 def test_multipart_link_is_not_orphaned(self):
  with self.j.db:
   self.j.db.execute('CREATE TABLE multipart(id TEXT PRIMARY KEY,body TEXT)')
   self.j.db.execute('INSERT INTO multipart VALUES(?,?)',('fixture-collection',json.dumps({'durable_task_id':self.ids[0]})))
  with self.assertRaisesRegex(ValueError,'multipart_link_present'):self.run_archive(True)
 def test_invalid_allowlist_refused(self):
  self.ids=self.ids*2
  with self.assertRaisesRegex(ValueError,'invalid_task_ids'):self.run_archive(True)
 def test_private_permissions_and_verified_backup_hashes(self):
  import hashlib,sqlite3
  self.run_archive(True)
  self.assertEqual(self.archive.stat().st_mode&0o777,0o700)
  manifest=json.loads((self.archive/'manifest.json').read_text())
  for name,digest in manifest['files'].items():
   path=self.archive/name
   self.assertEqual(path.stat().st_mode&0o777,0o600)
   self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),digest)
  backup=sqlite3.connect((self.archive/'journal-before.sqlite').as_uri()+'?mode=ro',uri=True)
  try:
   backup.execute('PRAGMA query_only=ON')
   self.assertTrue(all(json.loads(backup.execute('SELECT body FROM tasks WHERE id=?',(tid,)).fetchone()[0])['status']=='BLOCKED' for tid in self.ids))
  finally:backup.close()
 def test_archived_sandbox_context_cannot_create_or_modify_target(self):
  from apps.operator_layer.sandbox import SandboxAction
  stale=self.j.get(self.ids[0]);self.run_archive(True)
  context={'task_id':self.ids[0],'current_block':0,'block':dict(stale['plan'][0],allowed_mutations=['sandbox_marker']),'budget':{'soft_deadline':9999999999}}
  with self.assertRaisesRegex(ValueError,'task_retired'):SandboxAction(self.root,context)
  self.assertFalse((self.root/'sandbox.sqlite').exists())
