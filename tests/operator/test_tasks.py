import tempfile,unittest
from pathlib import Path
from apps.operator_layer.tasks import Journal,Budget

PLAN=[dict(goal=f'block {i}',acceptance=['verified'],allowed_mutations=['fixture'],expected_output='evidence',dependencies=list(range(i)),readback='fixture state',rollback='remove fixture') for i in range(3)]
class TasksTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.path=Path(self.tmp.name)/'tasks';self.j=Journal(self.path)
  self.id=self.j.create('telegram:fixture','three blocks',PLAN)
 def test_three_distinct_turns_compact_resume_done(self):
  for i in range(3):
   with Journal(self.path).turn(self.id,f'turn-{i}') as t:
    self.assertEqual(t.context()['current_block'],i)
    t.checkpoint('tests',{'tests_status':'PASS'})
    t.complete({'verified':True})
    with self.assertRaises(ValueError):t.begin_operation('another','fixture')
  self.assertEqual(self.j.get(self.id)['status'],'DONE')
  with self.assertRaises(ValueError):
   with self.j.turn(self.id,'repeat'):pass
  self.assertEqual(len(self.j.results()),1)
 def test_unknown_mutation_requires_readback_and_does_not_repeat(self):
  with self.assertRaises(RuntimeError):
   with self.j.turn(self.id,'old-thread') as t:
    self.req=t.begin_operation('commit','fixture')['request_id'];raise RuntimeError('transport')
  self.assertEqual(self.j.get(self.id)['status'],'INTERRUPTED')
  with self.j.turn(self.id,'new-thread') as t:
   with self.assertRaises(ValueError):t.begin_operation('commit','fixture')
   t.reconcile(self.req,{'verified':True,'commit':'abc'},applied=True)
   self.assertEqual(t.begin_operation('commit','fixture'),{'request_id':self.req,'execute':False})
   t.checkpoint('commit',{'last_commit':'abc'})
   t.complete({'verified':True})
 def test_second_writer_blocked(self):
  with self.j.turn(self.id,'one'):
   with self.assertRaises(ValueError):
    with Journal(self.path).turn(self.id,'two'):pass
 def test_acceptance_and_budget(self):
  with self.j.turn(self.id,'one') as t:
   with self.assertRaises(ValueError):t.complete({'verified':False})
  b=Budget(started=0,now=lambda:481)
  self.assertFalse(b.can_start(1));self.assertEqual(b.soft_deadline,480)
 def test_secret_fields_and_unsafe_storage(self):
  with self.j.turn(self.id,'one') as t:
   with self.assertRaises(ValueError):t.checkpoint('tests',{'token':'secret'})
  self.assertEqual(self.path.stat().st_mode&0o777,0o700)
  self.assertEqual((self.path/'journal.sqlite').stat().st_mode&0o777,0o600)
if __name__=='__main__':unittest.main()

class ProcessRecoveryTests(unittest.TestCase):
 def test_commit_crash_new_process_three_blocks(self):
  import subprocess,sys,json,os
  with tempfile.TemporaryDirectory() as root:
   root=Path(root);repo=root/'repo';repo.mkdir()
   def git(*args):return subprocess.check_output(['git','-C',str(repo),*args],text=True).strip()
   git('init','-q');git('config','user.email','fixture@example.test');git('config','user.name','Fixture')
   (repo/'data').write_text('base');git('add','data');git('commit','-qm','base')
   j=Journal(root/'journal');tid=j.create('telegram:fixture','three-process fixture',PLAN)
   prefix=f"from apps.operator_layer.tasks import Journal; import os,subprocess; from pathlib import Path\nj=Journal({str(root/'journal')!r});tid={tid!r}\n"
   crash=prefix+f"with j.turn(tid,'thread-old') as t:\n op=t.begin_operation('commit','fixture')\n Path({str(repo/'data')!r}).write_text('changed')\n subprocess.run(['git','-C',{str(repo)!r},'commit','-am','fixture'],check=True,stdout=subprocess.DEVNULL)\n os._exit(99)\n"
   self.assertEqual(subprocess.run([sys.executable,'-c',crash]).returncode,99)
   head=git('rev-parse','HEAD')
   resume=prefix+f"with j.turn(tid,'thread-new') as t:\n c=t.context()\n assert c['recovery_required']\n rid=c['pending_operations'][0][0]\n assert subprocess.check_output(['git','-C',{str(repo)!r},'rev-parse','HEAD'],text=True).strip()=={head!r}\n t.reconcile(rid,{{'verified':True,'commit':{head!r}}},True)\n assert not t.begin_operation('commit','fixture')['execute']\n t.checkpoint('commit',{{'last_commit':{head!r}}})\n t.complete({{'verified':True}})\n"
   subprocess.run([sys.executable,'-c',resume],check=True)
   for i in (1,2):
    subprocess.run([sys.executable,'-c',prefix+f"with j.turn(tid,'thread-{i}') as t:\n assert t.context()['current_block']=={i}\n t.complete({{'verified':True}})\n"],check=True)
   self.assertEqual(git('rev-list','--count','HEAD'),'2')
   self.assertEqual(Journal(root/'journal').unfinished(),[])
   self.assertEqual(len(j.results()),1)
