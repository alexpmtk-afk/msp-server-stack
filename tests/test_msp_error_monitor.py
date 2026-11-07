import importlib.util,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def load():
 spec=importlib.util.spec_from_file_location('error_monitor',ROOT/'scripts/operations/error_monitor.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
class MonitorTests(unittest.TestCase):
 def test_persistent_failure_does_not_wake_agent_every_poll(self):
  m=load();state={'incidents':{}}
  failure={'source':'user:down.service','code':'SERVICE_FAILED','details':{'unit':'down.service'}}
  a=m.reconcile(state,[failure],1000);b=m.reconcile(state,[failure],1030)
  self.assertEqual(a,b);self.assertEqual(len(a['actionable']),1)
  later=m.reconcile(state,[failure],1601);self.assertNotEqual(a,later)
 def test_blocked_external_does_not_disappear_or_trigger_endless_repairs(self):
  m=load();state={'incidents':{}};f={'source':'system:root.service','code':'SERVICE_FAILED','details':{}}
  m.reconcile(state,[f],1);incident=next(iter(state['incidents'].values()));incident['remediation']='blocked_external'
  out=m.reconcile(state,[f],5000);self.assertEqual(out['actionable'],[]);self.assertEqual(out['blocked'],[incident['id']])
  out=m.reconcile(state,[],5001);self.assertEqual(out['open'],[]);self.assertEqual(incident['status'],'resolved')
 def test_exception_content_is_never_exported_from_error_log(self):
  m=load();events=m.classify_log('Traceback: ValueError: token=SUPER_SECRET customer amount=123456 HTTP 503')
  self.assertNotIn('SUPER_SECRET',str(events));self.assertNotIn('123456',str(events));self.assertTrue(events)
 def test_active_service_failure_cannot_be_hidden_by_false_resolution(self):
  m=load();state={'incidents':{}};f={'source':'user:failed.service','code':'SERVICE_FAILED','details':{}}
  m.reconcile(state,[f],1);next(iter(state['incidents'].values()))['remediation']='resolved'
  out=m.reconcile(state,[f],2);self.assertEqual(len(out['actionable']),1)
