"""Batch self-purchase reports: independent cards, strict dates and no writes."""
import unittest

from apps.msp_self_analytics.batch_report import (
    PortfolioDataError, card_key, plan_portfolio, build_portfolio_report,
)


def row(sku, purchase, review, *, target=5, status="completed", source_row=None, store="laser"):
    item = {"marketplace": "wb", "store": store, "marketplace_sku": sku,
            "purchase_date": purchase, "review_date": review,
            "purchase_status": status, "quantity": target}
    if source_row is not None:
        item["source_row"] = source_row
    return item


URN = [
    row("urn", "2026-07-24", "2026-08-05", source_row=22),
    row("urn", "2026-07-30", "2026-08-07", source_row=28),
    row("urn", "2026-08-07", "2026-08-18", source_row=34),
]


def provider(d1, d2, sales, days):
    return {"request_status": "PASS_STRUCTURED", "d1": d1, "d2": d2,
            "sales": sales, "days_in_stock": days, "revenue": sales * 1000}


class PortfolioTest(unittest.TestCase):
    def test_batch_keeps_cards_isolated_and_sorts_deterministically(self):
        rows = URN + [row("other", "2026-08-01", "2026-08-08", target=1),
                      row("ignored", "2026-07-01", None, status="planned")]
        p = plan_portfolio(rows, as_of="2026-10-22",requested_days=30)
        self.assertEqual(p["card_count"], 2)
        self.assertEqual(p["noncompleted_rows_excluded"], 1)
        self.assertEqual(p["provider_request_count"], 4)
        urn = next(c for c in p["cards"] if c["card_key"] == card_key(("wb", "laser", "urn")))
        self.assertEqual(urn["series"]["recorded_completed_purchase_rows"], 3)
        self.assertEqual(urn["series"]["planned_total_per_card"], 5)
        self.assertEqual(urn["requests"][0], {
            "side": "before", "d1": "2026-07-06", "d2": "2026-08-04"})
        self.assertEqual(urn["requests"][1], {
            "side": "after", "d1": "2026-08-19", "d2": "2026-09-17"})
        self.assertFalse(p["marketplace_actions_allowed"])

    def test_provider_readback_and_russian_output(self):
        key = card_key(("wb", "laser", "urn"))
        observations = {key: {
            "before": provider("2026-07-06", "2026-08-04", 0, 26),
            "after": provider("2026-08-19", "2026-09-17", 3, 30),
        }}
        result = build_portfolio_report(URN, observations, as_of="2026-10-22",requested_days=30)
        self.assertEqual(result["summary"]["ready_with_both_sources"], 1)
        report = result["cards"][0]
        self.assertEqual(report["status"], "INTERMEDIATE_FULL_WINDOW")
        self.assertIn("План 5; записано выкупов 3", report["text_ru"])
        self.assertIn("0 до и 3 после", report["text_ru"])
        self.assertIn("не доказано", report["text_ru"])
        self.assertFalse(result["causal_effect_estimated"])

    def test_missing_provider_data_is_unknown_not_zero(self):
        result = build_portfolio_report(URN, {}, as_of="2026-10-22",requested_days=30)
        self.assertEqual(result["summary"]["provider_data_incomplete"], 1)
        self.assertEqual(result["cards"][0]["status"], "MPSTATS_WINDOWS_INCOMPLETE")
        self.assertIn("недостаточно сопоставимых данных", result["cards"][0]["text_ru"])

    def test_wrong_provider_window_must_fail(self):
        key = card_key(("wb", "laser", "urn"))
        value = {key: {
            "before": provider("2026-07-07", "2026-08-04", 10, 26),
            "after": provider("2026-08-19", "2026-09-17", 20, 30)}}
        outcome = build_portfolio_report(URN, value, as_of="2026-10-22",requested_days=30)
        self.assertEqual(outcome["summary"]["provider_data_incomplete"], 1)

    def test_repeated_plan_conflict_blocks_provider_requests(self):
        rows = URN[:2] + [row("urn", "2026-08-07", "2026-08-18", target=7)]
        plan = plan_portfolio(rows, as_of="2026-10-22",requested_days=30)
        self.assertEqual(plan["cards"][0]["status"], "RECONCILIATION_REQUIRED")
        self.assertEqual(plan["provider_request_count"], 0)
        result = build_portfolio_report(rows, {}, as_of="2026-10-22",requested_days=30)
        self.assertEqual(result["summary"]["reconciliation_required"], 1)
        self.assertIsNone(result["cards"][0]["report"])

    def test_no_review_or_no_post_days_does_not_consume_provider(self):
        rows = [row("a", "2026-10-20", None, target=1),
                row("b", "2026-10-20", "2026-10-21", target=1)]
        result = plan_portfolio(rows, as_of="2026-10-22",requested_days=30)
        self.assertEqual(result["provider_request_count"], 0)
        self.assertEqual({c["status"] for c in result["cards"]},
                         {"NO_RECORDED_REVIEW_DATE", "POST_WINDOW_PENDING"})

    def test_recent_review_uses_short_equal_windows(self):
        rows = [row("fresh", "2026-10-10", "2026-10-19", target=1)]
        plan = plan_portfolio(rows, as_of="2026-10-22",requested_days=30)
        self.assertEqual(plan["provider_request_count"], 2)
        self.assertEqual(plan["cards"][0]["requests"],
                         [{"side": "before", "d1": "2026-10-17", "d2": "2026-10-18"},
                          {"side": "after", "d1": "2026-10-20", "d2": "2026-10-21"}])

    def test_broken_card_does_not_stop_other_cards(self):
        rows = URN + [row("bad", "2026-09-01", "2026-08-01", target=1)]
        p = plan_portfolio(rows, as_of="2026-10-22",requested_days=30)
        self.assertEqual(p["provider_request_count"], 2)
        self.assertEqual(len([c for c in p["cards"] if c["status"] == "INVALID_SERIES"]), 1)

    def test_card_limit_and_invalid_rows(self):
        rows = [row(str(i), "2026-01-01", "2026-01-05") for i in range(3)]
        with self.assertRaisesRegex(PortfolioDataError, "CARD_LIMIT_EXCEEDED"):
            plan_portfolio(rows, as_of="2026-10-22", requested_days=30, max_cards=2)
        with self.assertRaisesRegex(PortfolioDataError, "INVALID_SOURCE_ROW"):
            plan_portfolio([None], as_of="2026-10-22",requested_days=30)
        with self.assertRaisesRegex(PortfolioDataError, "IDENTITY_REQUIRED"):
            plan_portfolio([{"purchase_status": "completed"}], as_of="2026-10-22",requested_days=30)

    def test_keys_cannot_collide_on_embedded_delimiters(self):
        self.assertNotEqual(card_key(("w|b", "la", "ser|1")),
                            card_key(("w", "b|la", "ser|1")))


if __name__ == "__main__":
    unittest.main()
