import os,copy,csv,importlib.util,io,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent))
sys.path.insert(0,os.environ.get('IMPORT_TEST_PAYLOAD',str(Path(__file__).parent)))
import publish as p,import_root as root
def rows():
 return [dict(reportId=int(p.RID),reportType=1,rrdId=i+1,dateFrom=p.DAY,dateTo=p.DAY,currency='RUB',sellerOperName='Продажа',docTypeName='Продажа',quantity=1,retailPriceWithDisc=1,retailAmount=1,forPay=1,orderId=str(i),customExtra={'nested':True}) for i in range(92)]
def catalog():
 path=Path(json.loads((Path(__file__).parent/'baseline.json').read_text())['release'])/'catalog.py'
 spec=importlib.util.spec_from_file_location('fixture_catalog',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
class ImportTests(unittest.TestCase):
 def test_root_boundary_before_reads(self):
  with self.assertRaises(PermissionError):root.main()
 def test_exact_document_selection(self):
  r=rows();self.assertEqual(p.select(dict(status=200,request_cursor=0,rows=r)),r)
 def test_duplicate_preserves_failure(self):
  r=rows();r[-1]=r[0]
  with self.assertRaises(ValueError):p.select(dict(status=200,request_cursor=0,rows=r))
 def test_foreign_date_refused(self):
  r=rows();r[0]['dateFrom']='2026-11-10'
  with self.assertRaises(ValueError):p.select(dict(status=200,request_cursor=0,rows=r))
 def test_partial_capture_refused(self):
  with self.assertRaises(ValueError):p.select(dict(status=200,request_cursor=0,rows=rows()[:-1]))
 def test_csv_preserves_every_original_field(self):
  raw=p.csv_bytes(rows());out=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig')),delimiter=';'));self.assertEqual(len(out),92)
  self.assertEqual([json.loads(r['_raw_json']) for r in out],rows());self.assertIn('customExtra',out[0])
 def setup_archive(self,t):
  a=catalog();archive=Path(t);base=a.root(p.CAB,archive);(base/'generations').mkdir(parents=True);(base/'documents').mkdir();a.store_index(dict(schema=1,cabinet=p.CAB,baseline_seeded=True,reports={}),archive);a.publish(a.load_index(p.CAB,archive),archive)
  return a,archive
 def test_real_publish_repeat_keeps_one_document_and_generation(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
   a,archive=self.setup_archive(t);first=p.publish(rows(),a,archive,'f'*64);second=p.publish(rows(),a,archive,'f'*64)
   self.assertEqual(first,second);idx=a.load_index(p.CAB,archive);self.assertEqual(len(idx['reports']),1);self.assertEqual(len(list(a.iter_view(a.snapshot(p.CAB,1,None,archive)))),92)
 def test_conflicting_source_not_overwritten(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
   a,archive=self.setup_archive(t);p.publish(rows(),a,archive,'f'*64);r=rows();r[0]['retailAmount']=99
   with self.assertRaises(ValueError):p.publish(r,a,archive,'f'*64)
   self.assertEqual(len(list(a.iter_view(a.snapshot(p.CAB,1,None,archive)))),92)
 def test_index_write_crash_can_resume_without_new_source(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
   a,archive=self.setup_archive(t)
   with patch.object(a,'store_index',side_effect=RuntimeError('fixture crash')),self.assertRaises(RuntimeError):p.publish(rows(),a,archive,'f'*64)
   result=p.publish(rows(),a,archive,'f'*64);self.assertEqual(result['rows'],92);self.assertEqual(len(a.load_index(p.CAB,archive)['reports']),1)
 def test_weekly_same_type_replaces_import_without_deleting_source(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
   a,archive=self.setup_archive(t);p.publish(rows(),a,archive,'f'*64);idx=a.load_index(p.CAB,archive);src=copy.deepcopy(idx['reports'][p.KEY]);src.update(period='weekly',report_id='999');idx['reports']['weekly|1|999']=src
   active,old=a.active_reports(idx);self.assertEqual(len(active),1);self.assertEqual(len(old),1);self.assertTrue(Path(old[0]['csv']).exists())
if __name__=='__main__':unittest.main()
