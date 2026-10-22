"""Verify that purchase quantity is kept separate from dated review evidence."""
import importlib.util
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("review_quantity",ROOT/"apps/msp_self_analytics/review_quantity.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class TestQuantityAudit(unittest.TestCase):
    def test_multiple_units_without_independent_evidence(self):
        r=mod.quantity_audit(3)
        self.assertEqual(r["purchase_units"],3)
        self.assertIsNone(r["verified_distinct_review_count"])
        self.assertTrue(r["multiple_units_require_individual_review_dates"])

    def test_one_verified_record_is_not_three_records(self):
        r=mod.quantity_audit(3,["sample-record-1"])
        self.assertEqual(r["verified_distinct_review_count"],1)
        self.assertEqual(r["unverified_potential_review_count"],2)

    def test_duplicate_reference_is_not_double_counted(self):
        r=mod.quantity_audit(2,["reference-a","reference-a"])
        self.assertEqual(r["verified_distinct_review_count"],1)

    def test_missing_or_invalid_unit_count_rejected(self):
        for value in (0,-1,None,True,1.5):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    mod.quantity_audit(value)

if __name__=="__main__":
    unittest.main()
