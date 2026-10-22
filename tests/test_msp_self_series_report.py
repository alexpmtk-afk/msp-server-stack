"""Pre-first and post-latest recorded review MPSTATS observations."""
from pathlib import Path
import sys,unittest
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
from apps.msp_self_analytics.series_report import build_series_report

def urn():
 return [
 {"marketplace":"wb","store":"laser","marketplace_sku":"336659148",
  "purchase_date":"2026-07-24","review_date":"2026-08-05","quantity":5},
 {"marketplace":"wb","store":"laser","marketplace_sku":"336659148",
  "purchase_date":"2026-07-30","review_date":"2026-08-07","quantity":5},
 {"marketplace":"wb","store":"laser","marketplace_sku":"336659148",
  "purchase_date":"2026-08-07","review_date":"2026-08-18","quantity":5}]

def values(d1,d2,sales,stock=30):
 return {"d1":d1,"d2":d2,"request_status":"PASS_STRUCTURED",
         "sales":sales,"revenue":100*sales,"days_in_stock":stock}

class TestFullSeriesReport(unittest.TestCase):
 def test_correct_urn_plan_and_windows_with_sales(self):
  before=values("2026-07-06","2026-08-04",4)
  after=values("2026-08-19","2026-09-17",7)
  r=build_series_report(urn(),before,after,as_of="2026-10-22")
  self.assertEqual(r["status"],"INTERMEDIATE_FULL_WINDOW")
  self.assertEqual(r["series"]["recorded_completed_purchase_rows"],3)
  self.assertEqual(r["series"]["planned_total_per_card"],5)
  self.assertEqual(r["provider_observations"]["estimated_sales_change"]["absolute"],3)
  self.assertFalse(r["causal_conclusion"])
  self.assertFalse(r["historical_rating_verified"])

 def test_provider_mismatched_time_is_not_accepted(self):
  before=values("2026-07-06","2026-08-04",4)
  after=values("2026-08-19","2026-09-16",7)
  r=build_series_report(urn(),before,after,as_of="2026-10-22")
  self.assertEqual(r["status"],"MPSTATS_WINDOWS_INCOMPLETE")
  self.assertIsNone(r["provider_observations"].get("estimated_sales_change"))

 def test_equal_short_windows_must_be_reported_as_short(self):
  before=values("2026-07-28","2026-08-04",1,8)
  after=values("2026-08-19","2026-08-26",2,8)
  r=build_series_report(urn(),before,after,as_of="2026-08-27")
  self.assertEqual(r["status"],"INTERMEDIATE_SHORT_EQUAL_WINDOW")
  self.assertEqual(r["series"]["windows"]["effective_days_each"],8)

 def test_zero_sales_not_a_missing_value(self):
  before=values("2026-07-06","2026-08-04",0)
  after=values("2026-08-19","2026-09-17",2)
  r=build_series_report(urn(),before,after,as_of="2026-10-22")
  self.assertIsNone(r["provider_observations"]["estimated_sales_change"]["percent"])
  self.assertEqual(r["provider_observations"]["estimated_sales_change"]["absolute"],2)

if __name__=="__main__":unittest.main()
