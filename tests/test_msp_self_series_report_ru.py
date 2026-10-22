"""Russian summary labels are factual and non-causal."""
from pathlib import Path
import sys, unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from apps.msp_self_analytics.series_report import build_series_report
from apps.msp_self_analytics.series_report_ru import format_series_report_ru

def event(review,purchase):
 return {"marketplace":"wb","store":"laser","marketplace_sku":"336659148",
         "quantity":5,"purchase_date":purchase,"review_date":review}

def metrics(d1,d2,sales,stock):
 return {"request_status":"PASS_STRUCTURED","d1":d1,"d2":d2,
         "sales":sales,"days_in_stock":stock,"revenue":sales*1000}
ROWS=[event("2026-08-05","2026-07-24"),event("2026-08-07","2026-07-30"),
      event("2026-08-18","2026-08-07")]

class TestRussianSeriesReport(unittest.TestCase):
 def test_urn_three_of_five_and_zero_baseline(self):
  r=build_series_report(ROWS,metrics("2026-07-06","2026-08-04",0,26),
      metrics("2026-08-19","2026-09-17",3,30),as_of="2026-10-22")
  t=format_series_report_ru(r,label="Урна 400×300×800")
  self.assertIn("План 5; записано выкупов 3; дат отзывов 3",t)
  self.assertIn("06.07.2026",t)
  self.assertIn("17.09.2026",t)
  self.assertIn("0 до и 3 после",t)
  self.assertIn("нулевой исходной базы",t)
  self.assertIn("не доказано",t)
  self.assertNotIn("15 выкупов",t)
 def test_missing_provider_values_do_not_create_sales(self):
  b=metrics("2026-07-06","2026-08-04",0,26)
  a=metrics("2026-08-19","2026-09-17",3,30)
  a["request_status"]="TOOL_ERROR"
  r=build_series_report(ROWS,b,a,as_of="2026-10-22")
  self.assertIn("недостаточно сопоставимых данных",format_series_report_ru(r))
 def test_zero_days_still_descriptive(self):
  r=build_series_report(ROWS,metrics("2026-07-06","2026-08-04",0,0),
      metrics("2026-08-19","2026-09-17",3,30),as_of="2026-10-22")
  self.assertIn("0 до и 3 после",format_series_report_ru(r))
 def test_requires_real_report_structure(self):
  with self.assertRaises(ValueError):
   format_series_report_ru({"status":"PASS"})
if __name__=="__main__":
 unittest.main()
