import importlib.util,json,os,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from apps.msp_marketplace_reports import archive,generation_store as g
ROOT=Path(__file__).resolve().parents[1];p=ROOT/'docs/data-sources/wb-financial-reports/export_local_schema.py';s=importlib.util.spec_from_file_location('schema_audit',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class SchemaAudit(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch');self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name);self.args=(self.root,'wb_weekly_finance_main','wb_laser_master','2026')
  self.row={'reportId':123,'reportType':1,'rrdId':8,'docTypeName':'Продажа','supplierOperName':'Продажа','retailPriceWithDisc':100,'commissionPercent':20,'acquiringFee':2,'ppvzForPay':78,'private_marker':'DO_NOT_EXPORT'}
  cells={k:archive_value(v) for k,v in self.row.items()};cells['_raw_json']=json.dumps(self.row,ensure_ascii=False,sort_keys=True,separators=(',',':'));self.raw=archive._encode(list(cells),{('123','8'):cells})
  meta=json.dumps(archive._metadata(self.raw,1,*self.args[1:])).encode();self.commit=g.publish_batch(*self.args,{'data.csv':self.raw,'data.csv.meta.json':meta});self.scope=g._scope(*self.args);self.csv=self.scope/'generations'/self.commit['generation']/'data.csv'
  original=m.plain;self.guard=patch.object(m,'plain',side_effect=lambda p,**kw:original(p,owners=(0,995,os.geteuid()),directory=kw.get('directory',False)));self.guard.start();self.addCleanup(self.guard.stop)
 def test_verified_scope_is_bound_to_current_bytes(self):
  out=m.audit_scope(self.root,*self.args[1:]);self.assertEqual(out['csv_sha256'],archive._sha(self.raw));self.assertEqual(out['rows'],1);self.assertTrue(out['raw_json_matches_csv'])
 def test_actual_names_types_and_formula_are_exported_not_values(self):
  out=m.profile_csv(self.csv,expected_rows=1);self.assertIn('ppvzForPay',out['headers']);self.assertEqual(out['raw_types']['ppvzForPay'],{'int':1});self.assertEqual(out['formula_diagnostics']['item_payout']['nonzero_tested'],1);self.assertEqual(out['formula_diagnostics']['item_payout']['matches_within_0_02'],1);self.assertNotIn('DO_NOT_EXPORT',json.dumps(out))
 def test_csv_raw_json_disagreement_is_not_blessed(self):
  self.csv.write_bytes(self.raw.replace(b';78;',b';79;'))
  with self.assertRaises(ValueError):m.profile_csv(self.csv,expected_rows=1)
 def test_changed_csv_hash_rejected(self):
  self.csv.write_bytes(self.raw+b'X')
  with self.assertRaises(ValueError):m.audit_scope(self.root,*self.args[1:])
 def test_descriptor_repack_without_current_change_rejected(self):
  p=self.csv.parent/'generation.json';p.write_bytes(p.read_bytes()+b' ')
  with self.assertRaises(ValueError):m.audit_scope(self.root,*self.args[1:])
 def test_wrong_report_type_is_rejected(self):
  with self.assertRaises(ValueError):m.profile_csv(self.csv,expected_rows=1,report_type=2)
 def test_duplicate_business_rows_rejected(self):
  parts=self.raw.splitlines(keepends=True);self.csv.write_bytes(self.raw+parts[-1])
  with self.assertRaises(ValueError):m.profile_csv(self.csv,expected_rows=2)
 def test_symlink_data_is_not_read(self):
  copy=self.root/'copy.csv';self.csv.rename(copy);self.csv.symlink_to(copy)
  with self.assertRaises(ValueError):m.audit_scope(self.root,*self.args[1:])
 def test_root_boundary_rejects_before_any_read_or_write(self):
  r=subprocess.run(['/usr/bin/python3','-I','-B',str(p)],capture_output=True,text=True);self.assertNotEqual(r.returncode,0);self.assertEqual(json.loads(r.stdout)['status'],'HOLD')
def archive_value(v):return '' if v is None else str(v)
