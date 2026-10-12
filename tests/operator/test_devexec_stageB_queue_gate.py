import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from apps.operator_layer.tasks import Journal
from apps.operator_layer.queue import TaskQueue,Worker
from apps.operator_layer.hermes_executor import HermesExecutor

SCOPE=('default','owner','telegram:fixture','fixture-session')
MUTATION_PLAN=[dict(goal='owner approved isolated file',acceptance=['verified'],allowed_mutations=['dev.write_file'],expected_output='file',dependencies=[],rollback='none',readback='independent backend receipt')]

class FakeExecutor:
 def __init__(self,authorized=False):
  self.sandbox_enabled=False;self.devexec_write_enabled=True;self.authorized=authorized;self.calls=0
 def approval_for(self,ctx):return self.authorized
 def execute(self,ctx,source,rid,budget):
  self.calls+=1;return {'kind':'complete','evidence':{'verified':True}}
 def interrupt(self):pass

class IntegrationGateTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.j=Journal(Path(self.tmp.name)/'private');self.addCleanup(self.j.close)
  self.q=TaskQueue(self.j,allowed_scope=SCOPE)
  tid=self.j.create(SCOPE[2],'fixture',MUTATION_PLAN)
  self.q.submit({'task_id':tid,'request_id':'fixture:'+tid,'profile':SCOPE[0], 'owner':SCOPE[1], 'origin_chat':SCOPE[2], 'session_key':SCOPE[3], 'origin_platform':'telegram'})
  self.tid=tid
 def test_no_owner_grant_stays_blocked_without_model_call(self):
  ex=FakeExecutor(authorized=False)
  self.assertFalse(Worker(self.q,ex,lambda c,o:True,worker_id='fixture').run_once())
  self.assertEqual(ex.calls,0)
  self.assertEqual(self.q.status(self.tid)['state'],'BLOCKED')
 def test_executor_without_security_attributes_is_also_blocked(self):
  class Unrestricted:
   def __init__(self):self.calls=0
   def execute(self,*args):self.calls+=1;return {'kind':'complete','evidence':{'verified':True}}
  ex=Unrestricted()
  self.assertFalse(Worker(self.q,ex,lambda c,o:True,worker_id='fixture').run_once())
  self.assertEqual(ex.calls,0)
  self.assertEqual(self.q.status(self.tid)['state'],'BLOCKED')
 def test_approved_precreated_plan_passes_queue_gate(self):
  ex=FakeExecutor(authorized=True)
  self.assertTrue(Worker(self.q,ex,lambda c,o:True,worker_id='fixture').run_once())
  self.assertEqual(ex.calls,1)
  self.assertEqual(self.q.status(self.tid)['state'],'DONE')
 def test_default_executor_stays_unapproved(self):
  ex=HermesExecutor(self.j.root,profile='default')
  ctx={'task_id':self.tid,'current_block':0,'block':MUTATION_PLAN[0]}
  self.assertFalse(ex.approval_for(ctx))
  self.assertFalse(ex.verify(ctx,{'kind':'complete','evidence':{'verified':True}}))
 def test_automatic_mutation_plan_rejected_even_with_write_flag(self):
  ex=HermesExecutor(self.j.root,profile='default',devexec_write_enabled=True)
  ctx={'requires_decomposition':True,'input_reference':{'assembled_hash':'example'}}
  outcome={'kind':'plan','plan':MUTATION_PLAN}
  self.assertFalse(ex.verify(ctx,outcome))

if __name__=='__main__':unittest.main()
