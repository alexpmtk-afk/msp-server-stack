import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from apps.msp_marketplace_reports import generation_store as g
from apps.msp_marketplace_reports.archive import _encode,_metadata

class LineageStreaming(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.args=(Path(self.temp.name),'wb_weekly_finance_main','wb_laser_master','2026')
  self.files=[];self.commits=[]
  for n in range(3):
   row={'reportId':'1','rrdId':'1','reportType':'1','amount':str(n)}
   raw=_encode(list(row),{('1','1'):row});files={'data.csv':raw,'data.csv.meta.json':json.dumps(_metadata(raw,1,*self.args[1:])).encode()}
   self.files.append(files);self.commits.append(g.publish_batch(*self.args,files,expected_generation=self.commits[-1]['generation'] if self.commits else None))
  self.scope=g._scope(*self.args)
 def test_active_semantics_once_but_all_ancestor_files_rehashed(self):
  with patch.object(g,'_validate_payload_pairs',wraps=g._validate_payload_pairs) as validate:
   self.assertEqual(g.read_active(*self.args)['files'],self.files[-1])
   self.assertEqual(validate.call_count,1)
  ancestor=self.scope/'generations'/self.commits[0]['generation']/'data.csv'
  ancestor.write_bytes(ancestor.read_bytes().replace(b'0',b'9'))
  with self.assertRaises(g.GenerationError):g.read_active(*self.args)
 def test_missing_ancestor_payload_is_not_skipped(self):
  (self.scope/'generations'/self.commits[0]['generation']/'data.csv.meta.json').unlink()
  with self.assertRaises((g.GenerationError,OSError)):g.read_active(*self.args)
 def test_selected_historical_generation_still_gets_semantic_validation(self):
  with patch.object(g,'_validate_payload_pairs',wraps=g._validate_payload_pairs) as validate:
   old=g.read_generation(*self.args,self.commits[0]['generation'],expected_digest=self.commits[0]['manifest_sha256'])
   self.assertEqual(old['files'],self.files[0]);self.assertEqual(validate.call_count,2)
 def test_corrupt_ancestor_descriptor_is_still_rejected(self):
  p=self.scope/'generations'/self.commits[0]['generation']/'generation.json';p.write_bytes(p.read_bytes()+b' ')
  with self.assertRaises(g.GenerationError):g.read_active(*self.args)
