import importlib.util,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('control',ROOT/'scripts/finance_control/control.py');c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
class Control(unittest.TestCase):
 def test_two_sequential_jobs_single_administrative_wake(self):
  events=[];plans=iter([{'id':1},{'id':2}]);req={'nonce':'a'*32,'cabinet':'wb_laser_master','max_jobs':2}
  result=c.process(req,lambda cab:next(plans),lambda n,p:{'status':'PASS','id':p['id']},lambda *x:events.append(x))
  self.assertEqual(len(result),2);self.assertEqual([e[0] for e in events],['BEFORE_JOB','AFTER_JOB']*2)
 def test_failure_does_not_start_second_portion(self):
  calls=[];req={'nonce':'b'*32,'cabinet':'wb_laser_master','max_jobs':2}
  out=c.process(req,lambda cab:{'report_id':1},lambda i,p:(calls.append(i) or {'status':'PARTIAL'}),lambda *a:None)
  self.assertEqual(calls,[0]);self.assertEqual(len(out),1)
 def test_request_cannot_expand_scope_or_execute(self):
  req={'nonce':'a'*32,'cabinet':'wb_laser_master','max_jobs':1}
  for patch in [{'command':'id'},{'max_jobs':True},{'max_jobs':3},{'cabinet':'ozon_laser_master'},{'nonce':'../escape'},{'reset_budget':True}]:
   with self.assertRaises(ValueError):c.request({**req,**patch})
 def test_real_overlay_loader_two_portions_no_reset_and_crash(self):
  with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR',str(ROOT))) as d:
   p=subprocess.run([sys.executable,'-I','-B',str(ROOT/'scripts/finance_control/test_overlay.py'),str(ROOT/'docs/marketplace-reports/autonomous-control-20261105/install.py'),str(ROOT),d],capture_output=True,timeout=45)
   self.assertEqual(p.returncode,0,p.stderr.decode());proof=json.loads(p.stdout);self.assertEqual(proof['entries'],[3,6]);self.assertEqual(proof['rows'],5);self.assertTrue(proof['completed_replay_no_dispatch'])
 def test_unit_and_policy_allow_only_fixed_start_and_no_daily_timer(self):
  folder=ROOT/'docs/marketplace-reports/autonomous-control-20261105'
  rule=(folder/'49-msp-finance-control.rules').read_text();self.assertIn('action.lookup("verb") === "start"',rule);self.assertIn('subject.user === "hermes"',rule)
  unit=(folder/'msp-finance-control.service').read_text();self.assertIn('ExecStopPost=',unit);self.assertIn('TimeoutStartSec=1000',unit);self.assertNotIn('OnCalendar',unit)
  recover=(folder/'msp-finance-recover.service').read_text();self.assertIn('--recover',recover);self.assertIn('PrivateNetwork=yes',recover)
