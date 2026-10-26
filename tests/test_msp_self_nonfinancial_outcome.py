"""Nonfinancial result is observational only; no invented public reviews."""
import unittest

from apps.msp_self_analytics.nonfinancial_outcome import (
    summarize_nonfinancial_outcome, format_nonfinancial_outcome_ru,
)
from apps.msp_self_analytics.self_purchase_analysis import build_observational_case
from apps.msp_self_analytics.checkpoint_workflow import plan_checkpoint_reads


def cp(n, before, after, status="READY_LOW_SAMPLE", pct=None, small=True):
    return {"checkpoint_number":n, "review_date":"2026-09-21",
        "stock_normalized_orders":{
            "status":status,
            "orders_per_in_stock_day_before":before,
            "orders_per_in_stock_day_after":after,
            "rate_percent_change":pct,
            "small_observed_sample":small,
        }}


def prices(*entries):
    return {"status":"VERIFIED_READONLY_VIEW","checkpoints":list(entries)}


class NonfinancialOutcomeTests(unittest.TestCase):
    def test_up_without_claiming_causes_or_followup_reviews(self):
        hist={"checkpoints":[cp(1,0.08,5/30,pct=108.333,small=True)]}
        p=prices({"checkpoint_number":1,"after_window_price_events":[]})
        result=summarize_nonfinancial_outcome(hist,p)
        observed=result["checkpoints"][0]
        self.assertEqual(observed["order_signal"],"OBSERVED_RATE_UP")
        self.assertEqual(observed["new_positive_public_reviews_status"],
                         "UNKNOWN_NO_VERIFIED_DATED_SOURCE")
        self.assertFalse(result["confirmed_historical_positive_review_count_is_zero"])
        self.assertFalse(result["any_causal_success_proven"])
        text=format_nonfinancial_outcome_ru(result)
        self.assertIn("рост оценочных заказов",text)
        self.assertIn("Малая выборка",text)
        self.assertIn("неизвестно",text)
        self.assertNotIn("подтверждённая эффективность",text)

    def test_decrease_flat_and_unknown_stay_distinct(self):
        hist={"checkpoints":[cp(1,1,0.5,pct=-50,small=False),
                             cp(2,0.2,0.2,pct=0,small=False),
                             cp(3,None,None,status="ZERO_STOCK_EXPOSURE")]}
        p=prices()
        x=summarize_nonfinancial_outcome(hist,p)
        self.assertEqual([a["order_signal"] for a in x["checkpoints"]],
            ["OBSERVED_RATE_DOWN","OBSERVED_RATE_UNCHANGED","UNKNOWN_SOURCE_OR_WINDOW"])
        self.assertEqual(x["checkpoints"][2]["normalized_rate_change_percent"],None)

    def test_zero_before_does_not_produce_fake_percentage(self):
        x=summarize_nonfinancial_outcome({"checkpoints":[cp(1,0,1,pct=None)]},prices())
        self.assertEqual(x["checkpoints"][0]["order_signal"],"OBSERVED_RATE_UP")
        self.assertIsNone(x["checkpoints"][0]["normalized_rate_change_percent"])
        self.assertIn("процентное изменение не установлено",
                      format_nonfinancial_outcome_ru(x))

    def test_price_change_warning_is_not_attributed_to_review(self):
        x=summarize_nonfinancial_outcome({"checkpoints":[cp(1,0.2,0.3)]},
             prices({"checkpoint_number":1,"after_window_price_events":[{"event_date":"2026-10-01"}]}))
        self.assertEqual(x["checkpoints"][0]["seller_price_context"],
                         "SELLER_PRICE_EDITS_IN_AFTER_WINDOW")
        self.assertIn("корректировка цены продавца",format_nonfinancial_outcome_ru(x))

    def test_missing_comparable_provider_data_is_not_success(self):
        x=summarize_nonfinancial_outcome({"checkpoints":[
            {"checkpoint_number":1,"review_date":"2026-09-21"}]},
            {"status":"UNKNOWN_PRICE_HISTORY"})
        self.assertEqual(x["checkpoints"][0]["order_signal"],"UNKNOWN_SOURCE_OR_WINDOW")
        self.assertEqual(x["checkpoints"][0]["seller_price_context"],"PRICE_HISTORY_UNKNOWN")

    def test_integration_uses_real_checkpoint_model_but_synthetic_data(self):
        rows=[{"marketplace":"wb","store":"laser","marketplace_sku":"123456789",
               "quantity":3,"source_row":1,"purchase_date":"2026-09-01",
               "review_date":"2026-09-21"}]
        req=plan_checkpoint_reads(rows,as_of="2026-10-26")["requests"]
        observations={}
        for r in req:
            is_before=r["d2"]<"2026-09-21"
            observations[r["key"]]={
                "request_status":"PASS_STRUCTURED","d1":r["d1"],"d2":r["d2"],
                "sales":2 if is_before else 5,
                "days_in_stock":25 if is_before else 30,
                "revenue":100 if is_before else 250}
        result=build_observational_case(rows,observations,as_of="2026-10-26")
        self.assertEqual(result["status"],"OBSERVATIONAL_REPORT_READY")
        self.assertIn("nonfinancial_outcome",result)
        self.assertEqual(result["nonfinancial_outcome"]["checkpoint_count"],1)
        self.assertEqual(result["nonfinancial_outcome"]["checkpoints"][0]["order_signal"],
                         "OBSERVED_RATE_UP")
        self.assertIn("НЕСТОИМОСТНАЯ ОЦЕНКА",result["human_readable_ru"])
        self.assertIn("Новые положительные оценки/отзывы",result["human_readable_ru"])
        self.assertFalse(result["business_effect_proven"])


if __name__=="__main__":
    unittest.main()
