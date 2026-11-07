"""Exercise generated operator continuation in an isolated filesystem; no API."""
import ast,hashlib,importlib.util,json,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
class ResumeUpgrade(unittest.TestCase):
 def fixture(self,tmp):
  path=ROOT/'docs/marketplace-reports/autonomous-control-20261105/resume-discovery.py'
  spec=importlib.util.spec_from_file_location('resume_upgrade',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  m.BASE=tmp/'base';m.STATE=tmp/'state';m.ROOT=tmp/'root';m.BASE.mkdir();(m.BASE/'backups').mkdir();m.STATE.mkdir();(m.ROOT/'inbox').mkdir(parents=True);(m.ROOT/'results').mkdir()
  m.RELEASE=str(tmp/'release');Path(m.RELEASE).mkdir();control=Path(m.RELEASE)/'control.py';control.write_text('# isolated fixture');m.CONTROL_SHA=hashlib.sha256(control.read_bytes()).hexdigest()
  (m.BASE/'wb-laser-master-20261106.py').write_text('# old wrapper')
  prior={'request_nonce':m.EXPECTED_NONCE,'jobs':[{'outcome':{'discovery':{'plan_sha256':'7dffbfc66652c48870b23e9a5663183b9b3780909d2dd29ce857332639eb0036'},'http_response_statuses':[200],'http_outcomes_unknown':0}}]}
  (m.STATE/'state.json').write_text(json.dumps({'schema':1,'phase':'HOLD','wakes':6,'cabinet_index':0,'last':prior,'counters':{'old-plan':3}}))
  (m.ROOT/'INSTALL.json').write_text(json.dumps({'release':m.RELEASE}));(m.ROOT/'inbox/request.json').write_text(json.dumps({'nonce':m.EXPECTED_NONCE}));(m.ROOT/'results'/(m.EXPECTED_NONCE+'.json')).write_text(json.dumps(prior))
  calls=[];original=m.importlib.util.spec_from_file_location
  def load(name,source):
   spec=original(name,source);loader=spec.loader;exec_original=loader.exec_module
   def exec_module(driver):
    exec_original(driver);driver.unit_closed=lambda:None;driver.root_json=lambda p:json.loads(p.read_text())
    def wake(cab):
     v=json.loads((m.STATE/'state.json').read_text());self.assertEqual(v['phase'],'DISPATCHING');self.assertEqual(v['wakes'],7);self.assertEqual(v['counters'],{'old-plan':3});calls.append(cab)
     return {'status':'PASS','request_nonce':'b'*32,'jobs':[{'status':'PASS'}]}
    driver.wake=wake
   loader.exec_module=exec_module;return spec
  stat_original=Path.stat
  def stat(p,*args,**kwargs):
   st=stat_original(p,*args,**kwargs)
   return types.SimpleNamespace(st_uid=0,st_mode=st.st_mode) if p==control else st
  def run(args,**kwargs):
   calls.append(args)
   return types.SimpleNamespace(stdout='failed\n',returncode=0)
  return m,calls,load,stat,run
 def test_real_generated_launcher_records_checkpoint_then_resumes_only_scoped_service(self):
  with tempfile.TemporaryDirectory() as tmp:
   m,calls,loader,stat,run=self.fixture(Path(tmp))
   with patch.object(m.os,'geteuid',return_value=1001),patch.object(m.importlib.util,'spec_from_file_location',side_effect=loader),patch.object(Path,'stat',stat),patch.object(m.subprocess,'run',side_effect=run):
    self.assertEqual(m.main(),0)
    self.assertEqual(calls.count('wb_laser_master'),1)
    v=json.loads((m.STATE/'state.json').read_text());self.assertEqual(v['phase'],'COOLDOWN');self.assertEqual(v['wakes'],7)
    with self.assertRaisesRegex(ValueError,'no longer current'):m.main()
    self.assertEqual(calls.count('wb_laser_master'),1)
 def test_root_cannot_run_user_recovery_program(self):
  spec=importlib.util.spec_from_file_location('refuse_root_resume',ROOT/'docs/marketplace-reports/autonomous-control-20261105/resume-discovery.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  with patch.object(m.os,'geteuid',return_value=0):
   with self.assertRaisesRegex(ValueError,'hermes only'):m.main()
