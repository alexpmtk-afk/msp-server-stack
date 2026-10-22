"""Test source-aware formulas; no fabricated marketplace economics."""
import unittest
from apps.msp_self_analytics.decision_indicators import (
    organic_sales_per_available_day, verified_peer_price_index,
    variable_unit_contribution, estimated_incremental_contribution,
    VARIABLE_COSTS,
)


def fact(value, source, **kwargs):
    return {"value": value, "source_kind": source, "status": "FACT",
            "source_ref": "controlled-evidence-001", **kwargs}


def finance():
    out = {"seller_price": fact("1000", "VERIFIED_FINANCE")}
    for k in VARIABLE_COSTS:
        out[k] = fact("10", "VERIFIED_FINANCE")
    return out


class DecisionIndicatorTests(unittest.TestCase):
    def test_organic_sales_rate_with_equal_window(self):
        interval = {"d1": "2026-09-01", "d2": "2026-09-30"}
        x = organic_sales_per_available_day(
            fact(18, "SELLER_ORGANIC_SALES", interval=interval),
            fact(12, "SELLER_AVAILABILITY", interval=interval))
        self.assertEqual(x["value"], "1.5")
        self.assertFalse(x["estimated_marketplace_sales_used"])

    def test_external_estimate_is_not_own_organic_sales(self):
        interval = {"d1": "2026-09-01", "d2": "2026-09-30"}
        x = organic_sales_per_available_day(
            fact(18, "MPSTATS_ESTIMATED_SALES", interval=interval),
            fact(12, "SELLER_AVAILABILITY", interval=interval))
        self.assertEqual(x["status"], "UNKNOWN")

    def test_zero_available_days_not_zero_sales_speed(self):
        interval = {"d1": "2026-09-01", "d2": "2026-09-30"}
        x = organic_sales_per_available_day(
            fact(0, "SELLER_ORGANIC_SALES", interval=interval),
            fact(0, "SELLER_AVAILABILITY", interval=interval))
        self.assertEqual(x["status"], "UNKNOWN")

    def test_different_periods_are_not_compared(self):
        x = organic_sales_per_available_day(
            fact(10, "SELLER_ORGANIC_SALES",
                 interval={"d1": "2026-09-01", "d2": "2026-09-30"}),
            fact(10, "SELLER_AVAILABILITY",
                 interval={"d1": "2026-08-01", "d2": "2026-08-31"}))
        self.assertEqual(x["reason"], "OBSERVATION_INTERVAL_NOT_ALIGNED")

    def test_price_index_requires_verified_comparators(self):
        own = fact(900, "VERIFIED_OWN_PRICE")
        potential = [{"comparability": "POTENTIAL_MARKET_PEER",
                      "price": fact(1000, "VERIFIED_COMPETITOR_PRICE")}]
        self.assertEqual(verified_peer_price_index(own, potential)["status"], "UNKNOWN")
        verified = [
            {"comparability": "VERIFIED_COMPARABLE", "approval_ref": "human-check-1",
             "price": fact(800, "VERIFIED_COMPETITOR_PRICE")},
            {"comparability": "VERIFIED_COMPARABLE", "approval_ref": "human-check-2",
             "price": fact(1000, "VERIFIED_COMPETITOR_PRICE")},
        ]
        r = verified_peer_price_index(own, verified)
        self.assertEqual(r["value"], "1")
        self.assertEqual(r["peer_count"], 2)

    def test_incomplete_finance_is_unknown_not_zero(self):
        costs = finance()
        costs.pop("taxes")
        x = variable_unit_contribution(costs)
        self.assertEqual(x["status"], "UNKNOWN")
        self.assertIn("taxes", x["missing_inputs"])

    def test_unit_margin_is_derived_arithmetic_not_static(self):
        x = variable_unit_contribution(finance())
        self.assertEqual(x["value"], "910")
        self.assertFalse(x["not_a_net_company_profit"] is False)

    def test_model_scenario_not_a_verified_effect(self):
        scenario = {"value": "3", "status": "MODEL_ESTIMATE",
                    "method_ref": "historical-model-dated-20261022"}
        x = estimated_incremental_contribution(
            finance(), scenario, fact(120, "VERIFIED_FINANCE"))
        self.assertEqual(x["status"], "MODEL_ESTIMATE")
        self.assertEqual(x["value"], "2610")
        self.assertFalse(x["causal_effect_proved"])
        self.assertFalse(x["approval_to_execute"])

    def test_missing_scenario_or_cost_is_unknown(self):
        s = {"value": 3, "status": "MODEL_ESTIMATE"}
        x = estimated_incremental_contribution(finance(), s,
            fact(100, "VERIFIED_FINANCE"))
        self.assertEqual(x["status"], "UNKNOWN")
        scenario = {"value": 3, "status": "MODEL_ESTIMATE", "method_ref": "sim-A"}
        x2 = estimated_incremental_contribution(finance(), scenario,
            fact(100, "MPSTATS_ESTIMATE"))
        self.assertEqual(x2["reason"], "ACTION_COST_UNKNOWN")


if __name__ == "__main__":
    unittest.main()
