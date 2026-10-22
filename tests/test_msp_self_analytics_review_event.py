"""Review-date lifecycle guards with synthetic dates only."""
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("review_event",ROOT/"apps/msp_self_analytics/review_event.py")
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class TestReviewDateEvent(unittest.TestCase):
    def test_completed_purchase_without_review_is_pending_not_analysis(self):
        got=module.classify_review_event("2026-10-06",None)
        self.assertEqual(got["status"],"REVIEW_DATE_NOT_RECORDED")
        self.assertIsNone(got["anchor_date"])
        self.assertFalse(got["analyze_review_outcome"])

    def test_reported_review_later_than_purchase(self):
        got=module.classify_review_event("2026-10-06","2026-10-14",review_url_present=True)
        self.assertEqual(got["anchor_date"],"2026-10-14")
        self.assertEqual(got["days_between_purchase_and_review"],8)
        self.assertEqual(got["status"],"READY_REGISTRY_DATE_WITH_UNCERTAINTY")
        self.assertEqual(got["date_quality"],"REGISTRY_REPORTED_NOT_VERIFIED")
        self.assertTrue(got["analyze_review_outcome"])

    def test_url_alone_does_not_confirm_date(self):
        got=module.classify_review_event("2026-10-06",None,review_url_present=True)
        self.assertIsNone(got["anchor_date"])

    def test_publication_verified_independently(self):
        got=module.classify_review_event("2026-10-06","2026-10-14",
                                          publication_date_verified="2026-10-14")
        self.assertEqual(got["status"],"READY_VERIFIED_PUBLICATION")
        self.assertEqual(got["date_quality"],"PUBLICATION_VERIFIED")

    def test_inconsistent_publication_needs_reconciliation(self):
        got=module.classify_review_event("2026-10-06","2026-10-14",
                                          publication_date_verified="2026-10-15")
        self.assertFalse(got["analyze_review_outcome"])
        self.assertEqual(got["status"],"SOURCE_DATE_MISMATCH")

    def test_review_before_purchase_not_used(self):
        got=module.classify_review_event("2026-10-06","2026-09-30")
        self.assertEqual(got["status"],"INVALID_DATE_ORDER")
        self.assertIsNone(got["anchor_date"])

    def test_draft_or_plan_without_purchase_is_not_completed_case(self):
        got=module.classify_review_event(None,"2026-10-14")
        self.assertEqual(got["status"],"PURCHASE_NOT_CONFIRMED")
        self.assertIsNone(got["anchor_date"])

if __name__=="__main__":
    unittest.main()
