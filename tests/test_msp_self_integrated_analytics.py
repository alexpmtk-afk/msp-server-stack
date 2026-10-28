"""Source-gated observational case, not a tool for fabricating reviews."""
import unittest
from apps.msp_self_analytics.checkpoint_workflow import plan_checkpoint_reads
from apps.msp_self_analytics.self_purchase_analysis import build_observational_case
from apps.msp_self_analytics.decision_indicators import VARIABLE_COSTS


def rows():
    return [dict(marketplace="wb",store="laser",marketplace_sku="123456789",
                 quantity=5,source_row=i,purchase_date=p,review_date=r)
            for i,(p,r) in enumerate([
                ("2026-07-24","2026-08-05"),
                ("2026-07-30","2026-08-07"),
                ("2026-08-07","2026-08-18")],1)]


def data():
    reqs=plan_checkpoint_reads(rows(),as_of="2026-10-23")["requests"]
    return {x["key"]:{"request_status":"PASS_STRUCTURED",
            "d1":x["d1"],"d2":x["d2"],"sales":0,
            "days_in_stock":1,"revenue":0} for x in reqs}


def fact(v):
    return dict(value=v,status="FACT",source_ref="verified-ledger-01",
                source_kind="VERIFIED_FINANCE")


class IntegratedAnalyticsTests(unittest.TestCase):
    def test_three_checkpoints_with_a_price_confounded_last(self):
        result=build_observational_case(rows(),data(),as_of="2026-10-23",
                price_events=[{"event_date":"2026-07-20"}],
                price_source_status="VERIFIED_READONLY_VIEW")
        self.assertEqual(result["status"],"OBSERVATIONAL_REPORT_READY")
        self.assertEqual(len(result["checkpoint_interpretations"]),3)
        self.assertEqual(
            result["checkpoint_interpretations"][-1]["price_impact_uncertainty"],
            "PRICE_CHANGE_CONFOUND_RECORDED")
        self.assertFalse(result["business_effect_proven"])
        self.assertEqual(result["verified_unit_contribution"]["status"],"UNKNOWN")
        self.assertIn("Денежная окупаемость отложена",result["human_readable_ru"])
        self.assertIn("журнал цен МСП — изменений ДО",result["human_readable_ru"])
        self.assertNotIn("В период ПОСЛЕ цена продавца",result["human_readable_ru"])

    def test_post_review_price_change_numeric_evidence_renders(self):
        value=build_observational_case(
            rows(),data(),as_of="2026-10-23",
            price_events=[{"event_date":"2026-09-01",
                           "source_segment":"current","source_ordinal":1,
                           "old_price":"2500","new_price":"2000"}],
            price_source_status="VERIFIED_READONLY_VIEW")
        self.assertIn("Цена ПОСЛЕ отзыва 2026-09-01: 2500 → 2000 ₽",
                      value["human_readable_ru"])
        self.assertEqual(value["price_history"]["checkpoints"][-1]
                         ["after_window_price_events"][0]["change_percent"],
                         "-20.00")
        self.assertIn("изменение -500 ₽ (-20,00%)", value["human_readable_ru"])
        self.assertIn("В период ПОСЛЕ цена продавца корректировалась", value["human_readable_ru"])
        self.assertTrue(value["checkpoint_interpretations"][-1]["price_changed_after_review"])
        self.assertFalse(value["business_effect_proven"])

    def test_missing_numeric_pair_remains_explicitly_unknown(self):
        value=build_observational_case(rows(),data(),as_of="2026-10-23",
            price_events=[{"event_date":"2026-09-01",
                           "old_price":None,"new_price":"1700"}],
            price_source_status="VERIFIED_READONLY_VIEW")
        self.assertIn("было/стало: значение неизвестно",value["human_readable_ru"])
        self.assertNotIn("0 → 1700",value["human_readable_ru"])
        self.assertTrue(value["checkpoint_interpretations"][-1]["price_changed_after_review"])

    def test_price_unavailable_stays_unknown(self):
        result=build_observational_case(rows(),data(),as_of="2026-10-23")
        self.assertEqual(result["price_history"]["status"],"UNKNOWN_PRICE_HISTORY")
        self.assertTrue(all(x["price_impact_uncertainty"]=="PRICE_HISTORY_UNKNOWN"
                            for x in result["checkpoint_interpretations"]))
        self.assertIn("пока недоступно",result["human_readable_ru"])

    def test_verified_finance_is_not_review_effect(self):
        costs={"seller_price":fact(1000)}
        costs.update({k:fact(20) for k in VARIABLE_COSTS})
        result=build_observational_case(
            rows(),data(),as_of="2026-10-23",verified_unit_costs=costs)
        self.assertEqual(result["verified_unit_contribution"]["status"],"FACT_DERIVED")
        self.assertFalse(result["business_effect_proven"])
        self.assertTrue(all(x["financial_return_status"]=="UNKNOWN_CAUSAL_INCREMENT"
                            for x in result["checkpoint_interpretations"]))

    def test_provider_missing_partially_reports_without_zero_substitution(self):
        result=build_observational_case(rows(),{},as_of="2026-10-23")
        self.assertEqual(result["status"],"OBSERVATIONAL_REPORT_PARTIAL")
        self.assertEqual(result["history"]["summary"]["incomplete_source"],3)
        self.assertFalse(result["marketplace_actions_allowed"])


    def test_failed_own_feed_attempt_does_not_claim_reconciliation(self):
        res=build_observational_case(
            rows(),data(),as_of="2026-10-23",
            own_order_sources={
                1:{"before":{"status":"SOURCE_UNAVAILABLE"},
                   "after":{"status":"OBSERVED_OWN_WB_FEED",
                            "pagination_complete":True}}})
        self.assertEqual(res["history"]["order_evidence"]["status"],
                         "OWN_FEED_PARTIAL_OR_UNAVAILABLE")
        self.assertFalse(res["history"]["order_evidence"]["independent_organic_orders_verified"])
        self.assertFalse(res["history"]["order_evidence"]["own_orders_automatically_subtracted"])

    def test_observed_own_feed_still_does_not_prove_coverage(self):
        observation={"status":"OBSERVED_OWN_WB_FEED",
                     "pagination_complete":True,
                     "source_load_coverage_verified":False}
        res=build_observational_case(
            rows(),data(),as_of="2026-10-23",
            own_order_sources={1:{"before":observation,"after":observation}})
        self.assertEqual(res["history"]["order_evidence"]["status"],
                         "OWN_FEED_OBSERVED_COVERAGE_UNVERIFIED")
        self.assertFalse(res["history"]["order_evidence"]["independent_organic_orders_verified"])

if __name__=="__main__":
    unittest.main()
