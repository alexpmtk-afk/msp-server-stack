import importlib.util,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
def load():
 spec=importlib.util.spec_from_file_location('observable_driver',ROOT/'scripts/finance_control/history_driver.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
class DriverObservability(unittest.TestCase):
 def test_exact_root_controller_preflight_does_not_start_duplicate_diagnostic(self):
  m=load()
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);m.ROOT_STATE=root/'root';m.STATE=root/'driver';m.STATE.mkdir();(m.ROOT_STATE/'inbox').mkdir(parents=True);(m.ROOT_STATE/'results').mkdir()
   (m.ROOT_STATE/'INSTALL.json').write_text(json.dumps({'release':m.EXPECTED_RELEASE,'schedule_enabled':False}))
   receipt={'request_nonce':'a'*32,'status':'PASS','jobs':[{'status':'PASS'}],'api_enabled_after_run':False,'schedule_enabled':False}
   (m.STATE/'state.json').write_text(json.dumps({'last':receipt}))
   (m.ROOT_STATE/'inbox/request.json').write_text(json.dumps({'nonce':'a'*32,'cabinet':'wb_laser_master','max_jobs':1}))
   (m.ROOT_STATE/'results'/('a'*32+'.json')).write_text(json.dumps(receipt))
   with patch.object(m,'root_json',side_effect=lambda p:json.loads(p.read_text())),patch.object(m,'unit_closed'),patch.object(m,'control_preflight_verified',return_value=True,create=True),patch.object(m.subprocess,'run',side_effect=AssertionError('must not repeat standalone diagnostic')):
    m.ADMISSION_PREFLIGHT=True
    self.assertEqual(m.gate('wb_laser_master'),'READY')

 def test_error_preserves_location_and_phase_without_exception_text(self):
  m=load()
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'state.json';p.write_text(json.dumps({'schema':1,'phase':'READY','wakes':0,'last':None,'cabinet_index':0}))
   def broken():raise ValueError('SECRET_TOKEN_MUST_NOT_LEAK')
   out=m.advance(p,broken,lambda:self.fail('no wake after gate failure'),lambda r:None)
   self.assertEqual(out['failure']['phase'],'preflight');self.assertEqual(out['failure']['error_type'],'ValueError')
   self.assertTrue(out['failure']['frames']);self.assertNotIn('SECRET_TOKEN_MUST_NOT_LEAK',p.read_text())

 def test_unknown_external_dispatch_is_never_automatically_retried(self):
  m=load();m.ADMISSION_PREFLIGHT=True
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);m.ROOT_STATE=root/'root';m.STATE=root/'driver';m.STATE.mkdir();(m.ROOT_STATE/'inbox').mkdir(parents=True)
   (m.STATE/'state.json').write_text(json.dumps({'last':{'request_nonce':'a'*32}}))
   (m.ROOT_STATE/'inbox/request.json').write_text(json.dumps({'nonce':'b'*32,'cabinet':'wb_laser_master'}))
   with patch.object(m,'control_preflight_verified',return_value=True):
    with self.assertRaisesRegex(ValueError,'uncertain'):m.admission_receipt_gate('wb_laser_master')

 def test_zero_job_receipt_is_complete_only_under_reviewed_root_preflight_mode(self):
  m=load();m.ADMISSION_PREFLIGHT=True
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'state.json';p.write_text(json.dumps({'schema':1,'phase':'READY','wakes':3,'last':None,'cabinet_index':0}))
   result={'request_nonce':'a'*32,'status':'PARTIAL','jobs':[],'api_enabled_after_run':False,'schedule_enabled':False}
   out=m.advance(p,lambda:'READY',lambda:result,lambda r:None)
   self.assertEqual(out['phase'],'CABINET_COMPLETE')
