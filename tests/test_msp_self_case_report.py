"""Synthetic acceptance tests: descriptive observations with no invented reviews."""
from pathlib import Path
import importlib.util
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from apps.msp_self_analytics.case_report import build_case_report

def period(d1,d2,qty,stock):
    return {"request_status":"PASS_STRUCTURED","d1":d1,"d2":d2,
            "sales":qty,"revenue":qty*500,"days_in_stock":stock,
            "period_rating":None}

def case(qty=3,review="2026-09-30"):
    return {"purchase_status":"completed","purchase_date":"2026-09-06",
            "review_date":review,"quantity":qty,
            "review_url_present":True,"business_goal":"unknown"}

def inputs():
    pre=period("2026-09-16","2026-09-29",5,12)
    post=period("2026-10-01","2026-10-14",6,14)
    return pre,post

class TestCaseReport(unittest.TestCase):
    def test_multiple_purchased_units_are_not_confirmed_reviews(self):
        r=build_case_report(case(),*inputs(),as_of="2026-10-22")
        self.assertEqual(r["status"],"DESCRIPTIVE_ONLY")
        q=r["purchase_quantity_evidence"]
        self.assertEqual(q["purchase_units"],3)
        self.assertIsNone(q["individually_verified_review_count"])
        self.assertTrue(q["multiple_units_single_date_ambiguous"])
        self.assertIsNone(r["observed_metrics"]["verified_historical_rating"])
        self.assertIsNone(r["observed_metrics"]["historical_review_count"])
        self.assertFalse(r["causal_effect_proven"])
        self.assertFalse(r["automated_marketplace_action"])

    def test_only_individually_verified_review_ids_count(self):
        r=build_case_report(case(),*inputs(),as_of="2026-10-22",
                            verified_review_ids=["r1","r1"])
        self.assertEqual(r["purchase_quantity_evidence"]["individually_verified_review_count"],1)
        self.assertEqual(r["purchase_quantity_evidence"]["unmatched_units"],2)

    def test_missing_review_date_never_falls_back_to_purchase(self):
        r=build_case_report(case(review=None),*inputs(),as_of="2026-10-22")
        self.assertEqual(r["status"],"REVIEW_ANALYSIS_NOT_ELIGIBLE")
        self.assertIsNone(r["historical_outcomes"])
        self.assertTrue(r["no_purchase_date_fallback"])

    def test_incomplete_post_window_never_reports_change(self):
        r=build_case_report(case(),*inputs(),as_of="2026-10-14")
        self.assertEqual(r["status"],"POST_WINDOW_INCOMPLETE")
        self.assertIsNone(r["historical_outcomes"])

    def test_plan_cannot_enter_completed_case_analysis(self):
        e=case()
        e["purchase_status"]="planned"
        with self.assertRaisesRegex(ValueError,"PURCHASE_NOT_COMPLETED"):
            build_case_report(e,*inputs(),as_of="2026-10-22")

    def test_bad_provider_dates_mark_incomplete(self):
        pre,post=inputs()
        post["d2"]="2026-10-13"
        r=build_case_report(case(),pre,post,as_of="2026-10-22")
        self.assertEqual(r["status"],"INCOMPLETE")
        self.assertIsNone(r["observed_metrics"]["provider_estimated_sales"]["after"])

    def test_actual_publication_date_disagreement_blocks(self):
        r=build_case_report(case(),*inputs(),as_of="2026-10-22",
                            verified_publication_date="2026-10-01")
        self.assertEqual(r["status"],"REVIEW_ANALYSIS_NOT_ELIGIBLE")
        self.assertEqual(r["event_state"],"SOURCE_DATE_MISMATCH")

    def test_no_peer_claim_without_evidence(self):
        r=build_case_report(case(),*inputs(),as_of="2026-10-22",
            checked_competitors=[{"same_product_category":True}])
        self.assertEqual(r["comparable_products"]["accepted"],0)
        self.assertIn("CONTROL_GROUP_NOT_VALIDATED",r["confidence_limitations"])

if __name__=="__main__":
    unittest.main()
