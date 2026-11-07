import importlib.util,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from apps.msp_marketplace_reports.wb_worker_adapter import run_one_step
ROOT=Path(__file__).resolve().parents[1]
class Snapshot(unittest.TestCase):
 def test_generation_is_read_once_per_dataset_during_one_serialized_selection(self):
  spec=importlib.util.spec_from_file_location('apps.msp_marketplace_reports.snapshot_receipts',ROOT/'scripts/finance_control/overlays/finance_receipts.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   for rid in (9,10):
    row={'reportId':rid,'reportType':1,'rrdId':rid,'amount':'SYNTHETIC'}
    run_one_step(root,'wb_laser_master',2026,rid,1,lambda req:(200,[row]));run_one_step(root,'wb_laser_master',2026,rid,1,lambda req:(204,None))
   cache={}
   with patch.object(m,'read_active',wraps=m.read_active) as reader:
    for rid in (9,10):self.assertTrue(m.report_receipt(root,'wb_laser_master',2026,rid,1,snapshot=cache)['verified'])
    self.assertEqual(reader.call_count,1)
   # A NEW selection must revalidate the then-current generation, never use a global cache.
   with patch.object(m,'read_active',wraps=m.read_active) as reader:
    m.report_receipt(root,'wb_laser_master',2026,9,1,snapshot={});self.assertEqual(reader.call_count,1)
