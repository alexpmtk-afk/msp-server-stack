"""Source-aligned sequential observational analytics; all fixtures synthetic."""
import unittest

from apps.msp_self_analytics.checkpoint_workflow import (
    CheckpointPlanningError, plan_checkpoint_reads, assemble_checkpoint_analysis,
)
from apps.msp_self_analytics.checkpoint_report_ru import format_checkpoint_history_ru


def event(p, r, i, target=5):
    return {"marketplace": "wb", "store": "laser",
            "marketplace_sku": "123456789", "source_row": i, "quantity": target,
            "purchase_date": p, "review_date": r}


def series():
    return [event("2026-07-24", "2026-08-05", 1),
            event("2026-07-30", "2026-08-07", 2),
            event("2026-08-07", "2026-08-18", 3)]


def provider(r, sales=1, stock=1):
    return {"d1": r["d1"], "d2": r["d2"],
            "request_status": "PASS_STRUCTURED", "sales": sales,
            "days_in_stock": stock, "revenue": sales * 100}


def observations(plan):
    return {r["key"]: provider(r) for r in plan["requests"]}


class CheckpointWorkflowTests(unittest.TestCase):
    def test_three_events_produce_six_distinct_exact_requests(self):
        p = plan_checkpoint_reads(series(), as_of="2026-10-22",requested_days=30)
        self.assertEqual(p["checkpoint_count"], 3)
        self.assertEqual(p["provider_read_count"], 6)
        self.assertEqual([x["effective_days_each"]
                          for x in p["series"]["checkpoints"]], [1, 10, 30])
        self.assertEqual(len({x["key"] for x in p["requests"]}), 6)
        self.assertTrue(p["excluded_event_days"])
        self.assertTrue(p["future_review_censors_earlier_post_window"])

    def test_duplicate_exact_windows_are_requested_once(self):
        rows = [event("2026-07-01", "2026-07-04", 1),
                event("2026-07-05", "2026-07-08", 2),
                event("2026-07-06", "2026-07-08", 3)]
        p = plan_checkpoint_reads(rows, as_of="2026-08-20",requested_days=30)
        self.assertEqual(p["checkpoint_count"], 2)
        self.assertEqual(p["provider_read_count"], 4)

    def test_short_equal_window_at_as_of(self):
        p = plan_checkpoint_reads(series(), as_of="2026-08-27")
        self.assertEqual([x["effective_days_each"]
                          for x in p["series"]["checkpoints"]], [1, 10, 8])
        self.assertEqual(p["series"]["checkpoints"][-1]["windows"]["after"],
                         {"d1": "2026-08-19", "d2": "2026-08-26",})
        self.assertEqual(p["provider_read_count"], 6)

    def test_result_with_all_expected_readbacks(self):
        p = plan_checkpoint_reads(series(), as_of="2026-10-22",requested_days=30)
        d = observations(p)
        r = assemble_checkpoint_analysis(series(), d, as_of="2026-10-22",requested_days=30)
        self.assertEqual(r["status"], "COMPLETE_DESCRIPTIVE")
        self.assertEqual(r["summary"]["with_estimated_sales"], 3)
        self.assertEqual(r["summary"]["incomplete_source"], 0)
        self.assertEqual(r["provider_windows_planned"], 6)
        self.assertFalse(r["causal_conclusion"])
        self.assertEqual(r["checkpoints"][0]["status"], "SHORTER_EQUAL_WINDOW_PRELIMINARY")
        self.assertEqual(r["checkpoints"][-1]["status"], "FULL_EQUAL_WINDOW")

    def test_missing_provider_observation_is_not_zero(self):
        p = plan_checkpoint_reads(series(), as_of="2026-10-22",requested_days=30)
        d = observations(p)
        del d[p["checkpoint_to_requests"][2]["after"]]
        r = assemble_checkpoint_analysis(series(), d, as_of="2026-10-22",requested_days=30)
        self.assertEqual(r["summary"]["incomplete_source"], 1)
        self.assertEqual(r["checkpoints"][1]["status"], "MPSTATS_WINDOWS_INCOMPLETE")
        self.assertEqual(r["status"], "PARTIAL_DESCRIPTIVE")

    def test_wrong_response_date_is_rejected(self):
        p = plan_checkpoint_reads(series(), as_of="2026-10-22",requested_days=30)
        d = observations(p)
        d[p["checkpoint_to_requests"][3]["before"]]["d2"] = "2026-08-03"
        r = assemble_checkpoint_analysis(series(), d, as_of="2026-10-22",requested_days=30)
        self.assertEqual(r["checkpoints"][2]["status"], "MPSTATS_WINDOWS_INCOMPLETE")

    def test_stock_inequality_and_zero_baseline_are_flagged(self):
        p = plan_checkpoint_reads(series(), as_of="2026-10-22",requested_days=30)
        d = observations(p)
        first = p["checkpoint_to_requests"][1]
        d[first["before"]]["sales"] = 0
        d[first["before"]]["days_in_stock"] = 0
        r = assemble_checkpoint_analysis(series(), d, as_of="2026-10-22",requested_days=30)
        flags = r["checkpoints"][0]["source_quality_flags"]
        self.assertIn("STOCK_AVAILABILITY_DIFFERS", flags)
        self.assertIn("STOCK_NORMALIZED_RATE_UNAVAILABLE", flags)
        self.assertIn("PERCENT_CHANGE_FROM_ZERO_UNDEFINED", flags)
        self.assertIsNone(r["checkpoints"][0]["provider_observations"]
                          ["estimated_sales_change"]["percent"])

    def test_zero_day_as_of_is_pending_and_no_queries(self):
        rows = [event("2026-08-06", "2026-08-08", 1)]
        p = plan_checkpoint_reads(rows, as_of="2026-08-09")
        self.assertEqual(p["provider_read_count"], 0)
        r = assemble_checkpoint_analysis(rows, {}, as_of="2026-08-09")
        self.assertEqual(r["summary"]["post_window_pending"], 1)
        self.assertEqual(r["status"], "PARTIAL_DESCRIPTIVE")

    def test_invalid_series_count_not_truncated_silently(self):
        rows = [event("2026-01-01", f"2026-02-{i:02d}", i, target=13)
                for i in range(1, 14)]
        with self.assertRaisesRegex(CheckpointPlanningError,
                                    "CHECKPOINT_LIMIT_EXCEEDED"):
            plan_checkpoint_reads(rows, as_of="2026-05-01")

    def test_call_cap_requires_explicit_escalation(self):
        with self.assertRaisesRegex(CheckpointPlanningError,
                                    "PROVIDER_READ_LIMIT_EXCEEDED"):
            plan_checkpoint_reads(series(), as_of="2026-10-22",requested_days=30,
                                  max_provider_reads=5)

    def test_russian_report_no_causal_claim(self):
        p = plan_checkpoint_reads(series(), as_of="2026-10-22",requested_days=30)
        r = assemble_checkpoint_analysis(
            series(), observations(p), as_of="2026-10-22",requested_days=30)
        text = format_checkpoint_history_ru(r, label="Контрольный товар")
        self.assertEqual(text.count("Контроль "), 3)
        self.assertIn("Контроль 1", text)
        self.assertIn("30-дневный итог", text)
        self.assertIn("не доказывает", text)
        self.assertNotIn("эффективность подтверждена", text)

    def test_missing_report_structure_rejected(self):
        with self.assertRaisesRegex(ValueError, "CHECKPOINT_HISTORY_REQUIRED"):
            format_checkpoint_history_ru({})


if __name__ == "__main__":
    unittest.main()
