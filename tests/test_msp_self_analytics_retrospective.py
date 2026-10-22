"""Deterministic, synthetic tests for historical source-aware analysis."""
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("retrospective",ROOT/"apps/msp_self_analytics/retrospective.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def sample(d1,d2,sales,days,*,rating=None,status="PASS_STRUCTURED"):
    return {"d1":d1,"d2":d2,"request_status":status,"sales":sales,
            "revenue":None if sales is None else sales*100,
            "days_in_stock":days,"period_rating":rating}

def pair(b=2,a=1,bd=14,ad=10):
    return (sample("2026-09-22","2026-10-05",b,bd,rating=0),
            sample("2026-10-07","2026-10-20",a,ad,rating=5))

class TestHistoricalAnalysis(unittest.TestCase):
    def test_exact_windows_exclude_event(self):
        w=m.windows("2026-10-06")
        self.assertEqual(w["before"],{"d1":"2026-09-22","d2":"2026-10-05"})
        self.assertEqual(w["after"],{"d1":"2026-10-07","d2":"2026-10-20"})

    def test_sales_stock_day_normalization_reduces_raw_percent_difference(self):
        r=m.analyze("2026-10-06",*pair())
        self.assertEqual(r["report_status"],"DESCRIPTIVE_ONLY")
        self.assertEqual(r["provider_sales_change"]["percent"],-50.0)
        self.assertAlmostEqual(r["before"]["sales_per_provider_stock_day"],2/14)
        self.assertAlmostEqual(r["after"]["sales_per_provider_stock_day"],1/10)
        self.assertAlmostEqual(r["provider_stock_day_sales_change"]["percent"],-30.0)
        self.assertIn("STOCK_DAYS_DIFFERENT",r["confounders"])
        self.assertFalse(r["causal_effect_proven"])
        self.assertFalse(r["recommendation_automation_allowed"])
        self.assertEqual(r["rating_status"],"PERIOD_FIELD_OBSERVED_ASOF_SEMANTICS_NOT_VERIFIED")

    def test_zero_base_never_returns_infinite_percent(self):
        before,after=pair(0,3)
        r=m.analyze("2026-10-06",before,after)
        self.assertIsNone(r["provider_sales_change"]["percent"])
        self.assertEqual(r["provider_sales_change"]["status"],"PERCENT_UNDEFINED_ZERO_BASE")
        self.assertIn("ZERO_ESTIMATED_SALES_IN_A_WINDOW",r["confounders"])

    def test_missing_stock_days_are_unknown_not_zero(self):
        r=m.analyze("2026-10-06",*pair(2,3,None,None))
        self.assertIsNone(r["provider_stock_day_sales_change"]["absolute"])
        self.assertIn("STOCK_DAYS_UNAVAILABLE",r["confounders"])

    def test_rounded_ratings_are_not_accepted_as_historical(self):
        before,after=pair()
        r=m.analyze("2026-10-06",before,after)
        self.assertFalse(r["before"]["historical_rating_asof_confirmed"])
        self.assertFalse(r["after"]["historical_rating_asof_confirmed"])

    def test_wrong_date_rejected_without_using_number(self):
        before,after=pair()
        before["d1"]="2026-09-20"
        r=m.analyze("2026-10-06",before,after)
        self.assertEqual(r["report_status"],"INCOMPLETE")
        self.assertEqual(r["provider_sales_change"]["status"],"UNAVAILABLE")

    def test_only_verified_comparable_peer_contributes(self):
        before,after=pair(2,4,14,14)
        ok={"same_product_category":True,"same_intended_use":True,"attributes_checked":True,
            "before":sample("2026-09-22","2026-10-05",8,14),
            "after":sample("2026-10-07","2026-10-20",10,14)}
        not_checked=dict(ok,attributes_checked=False)
        r=m.analyze("2026-10-06",before,after,competitors=[ok,not_checked])
        self.assertEqual(r["competitors"]["accepted"],1)
        self.assertEqual(r["competitors"]["rejected"],1)
        self.assertAlmostEqual(r["competitors"]["own_minus_peer_daily_change"],0)
        self.assertEqual(r["competitors"]["interpretation"],"DESCRIPTIVE_DIFFERENCE_NOT_CAUSAL_IMPACT")

    def test_provider_similar_results_without_product_checks_are_not_controls(self):
        before,after=pair()
        r=m.analyze("2026-10-06",before,after,competitors=[{
            "same_product_category":True,"before":before,"after":after}])
        self.assertEqual(r["competitors"]["status"],"NO_VERIFIED_COMPARATORS")

    def test_bad_stock_day_range_fails_closed(self):
        with self.assertRaisesRegex(m.InvalidObservation,"INVALID_DAYS_IN_STOCK"):
            m.analyze("2026-10-06",*pair(2,1,17,10))

    def test_negative_and_malformed_sales_fail_or_remain_unknown(self):
        with self.assertRaisesRegex(m.InvalidObservation,"NEGATIVE_SALES"):
            m.analyze("2026-10-06",*pair(-1,1))
        before,after=pair()
        before["sales"]="bad"
        r=m.analyze("2026-10-06",before,after)
        self.assertEqual(r["report_status"],"INCOMPLETE")

if __name__=="__main__":
    unittest.main()
