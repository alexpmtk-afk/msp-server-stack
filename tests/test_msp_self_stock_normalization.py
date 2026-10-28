"""Source-gated descriptive inventory exposure normalization; synthetic fixtures."""
import unittest

from apps.msp_self_analytics.stock_normalization import normalize_stock_exposure
from apps.msp_self_analytics.checkpoint_workflow import (
    plan_checkpoint_reads, assemble_checkpoint_analysis,
)
from apps.msp_self_analytics.checkpoint_report_ru import format_checkpoint_history_ru


def event():
    return [{"marketplace":"wb","store":"novok","marketplace_sku":"123456789",
             "source_row":1,"purchase_date":"2026-09-10",
             "review_date":"2026-09-21","quantity":2}]


def report(before,after,sb,sa):
    rows=event()
    p=plan_checkpoint_reads(rows,as_of="2026-10-23")
    d={}
    for req in p["requests"]:
        is_before=req["d2"]<"2026-09-21"
        n=before if is_before else after
        stock=sb if is_before else sa
        d[req["key"]]={"request_status":"PASS_STRUCTURED",
                       "d1":req["d1"],"d2":req["d2"],
                       "sales":n,"revenue":n*100 if n is not None else None,
                       "days_in_stock":stock}
    return assemble_checkpoint_analysis(rows,d,as_of="2026-10-23")


class NormalizedStockExposureTests(unittest.TestCase):
    def test_31_day_sku_estimates_and_denominators(self):
        out=normalize_stock_exposure(2,7,25,27,window_days=31)
        self.assertEqual(out["status"],"READY_LOW_SAMPLE")
        self.assertAlmostEqual(out["orders_per_in_stock_day_before"],0.08)
        self.assertAlmostEqual(out["orders_per_in_stock_day_after"],7/27)
        self.assertAlmostEqual(out["rate_percent_change"],(7/27/0.08-1)*100)
        self.assertAlmostEqual(out["in_stock_coverage_percent_after"],27/31*100)
        self.assertFalse(out["causal_inference_allowed"])
        self.assertFalse(out["missing_day_extrapolation_allowed"])

    def test_90_day_case_reverses_total_orders_story(self):
        out=normalize_stock_exposure(3,14,13,81,window_days=90)
        self.assertLess(out["orders_per_in_stock_day_after"],
                        out["orders_per_in_stock_day_before"])
        self.assertLess(out["rate_percent_change"],0)

    def test_completed_zero_orders_positive_stock_valid_but_percent_unknown(self):
        out=normalize_stock_exposure(0,7,10,12,window_days=30)
        self.assertEqual(out["status"],"READY_LOW_SAMPLE")
        self.assertEqual(out["orders_per_in_stock_day_before"],0)
        self.assertIsNone(out["rate_percent_change"])

    def test_zero_stock_exposure_refuses_rate_even_zero_orders(self):
        out=normalize_stock_exposure(0,4,0,12,window_days=30)
        self.assertEqual(out["status"],"ZERO_STOCK_EXPOSURE")
        self.assertIsNone(out["orders_per_in_stock_day_after"])
        self.assertIsNone(out["rate_percent_change"])

    def test_missing_and_invalid_stock_not_zero(self):
        for value in (None,-1,100,2.5,True,float("nan"),float("inf")):
            out=normalize_stock_exposure(2,7,value,27,window_days=31)
            self.assertEqual(out["status"],"STOCK_DAYS_MISSING_OR_INVALID")
            self.assertIsNone(out["in_stock_days_before"])
        self.assertEqual(normalize_stock_exposure(None,7,25,27,window_days=31)
                         ["status"],"ESTIMATED_ORDERS_MISSING")

    def test_window_strict_cap(self):
        for n in (0,91,True,2.5):
            with self.assertRaises(ValueError):
                normalize_stock_exposure(2,7,25,27,window_days=n)

    def test_live_report_interface_has_rates_and_low_sample_warning(self):
        r=report(2,7,25,27)
        self.assertEqual(r["status"],"COMPLETE_DESCRIPTIVE")
        cp=r["checkpoints"][0]
        self.assertIn("LOW_ESTIMATED_ORDER_SAMPLE",cp["source_quality_flags"])
        self.assertEqual(cp["stock_normalized_orders"]["status"],"READY_LOW_SAMPLE")
        text=format_checkpoint_history_ru(r)
        self.assertIn("0,08 ДО",text)
        self.assertIn("Изменение интенсивности",text)
        self.assertIn("Малая выборка",text)
        self.assertIn("НЕ доказательство эффекта отзыва",text)
        self.assertEqual(cp["advertising_evidence_status"],"UNVERIFIED_FOR_SKU_AND_WINDOW")
        self.assertEqual(cp["verified_comparator_status"],"NO_VERIFIED_COMPARATORS")
        self.assertIn("не означает отсутствие рекламы или 0 ₽",text)
        self.assertIn("подтверждённых сопоставимых товаров нет",text)


    def test_zero_stock_report_flags_no_rate(self):
        r=report(0,7,0,27)
        text=format_checkpoint_history_ru(r)
        self.assertIn("0 подтверждённых дней наличия",text)
        self.assertNotIn("Изменение интенсивности: ",text)


if __name__=="__main__":
    unittest.main()
