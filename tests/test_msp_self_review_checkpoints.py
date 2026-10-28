"""Successive dated-review checkpoints: symmetric observed windows, no bleed."""
import unittest

from apps.msp_self_analytics.series_analysis import analyze_series
from apps.msp_self_analytics.series_report import build_series_checkpoint_reports


def entry(purchase, review, row, target=5):
    return {"marketplace": "wb", "store": "laser",
            "marketplace_sku": "336659148", "quantity": target,
            "source_row": row, "purchase_date": purchase, "review_date": review}


def original():
    return [
        entry("2026-07-24", "2026-08-05", 22),
        entry("2026-07-30", "2026-08-07", 28),
        entry("2026-08-07", "2026-08-18", 34),
    ]


def metrics(w, sales, stock=None):
    days = stock or 1
    return {"request_status": "PASS_STRUCTURED",
            "d1": w["d1"], "d2": w["d2"],
            "sales": sales, "days_in_stock": days,
            "revenue": sales * 100}


class ReviewDateCheckpointTests(unittest.TestCase):
    def test_three_reviews_produce_three_separate_snapshots(self):
        s = analyze_series(original(), as_of="2026-10-22",requested_days=30)
        c = s["checkpoints"]
        self.assertEqual(len(c), 3)
        self.assertEqual([x["cumulative_recorded_review_rows"] for x in c],
                         [1, 2, 3])
        self.assertEqual([x["effective_days_each"] for x in c], [1, 10, 30])
        self.assertEqual([x["windows"]["before"]["d2"] for x in c],
                         ["2026-08-04"] * 3)
        self.assertEqual(c[0]["windows"]["after"],
                         {"d1": "2026-08-06", "d2": "2026-08-06"})
        self.assertEqual(c[1]["windows"]["after"],
                         {"d1": "2026-08-08", "d2": "2026-08-17"})
        self.assertEqual(c[2]["windows"]["after"],
                         {"d1": "2026-08-19", "d2": "2026-09-17"})
        self.assertTrue(c[0]["censored_by_next_review"])
        self.assertTrue(c[1]["censored_by_next_review"])
        self.assertFalse(c[2]["censored_by_next_review"])
        self.assertFalse(c[2]["causal_effect_proven"])
        self.assertEqual(s["planned_total_per_card"], 5)
        self.assertEqual(s["recorded_completed_purchase_rows"], 3)
        # Legacy summary remains backwards compatible for old callers.
        self.assertEqual(s["windows"]["after"], c[-1]["windows"]["after"])

    def test_latest_event_has_shorter_equal_period(self):
        s = analyze_series(original(), as_of="2026-08-27")
        c = s["checkpoints"]
        self.assertEqual([x["effective_days_each"] for x in c], [1, 10, 8])
        self.assertEqual(c[-1]["windows"]["before"],
                         {"d1": "2026-07-28", "d2": "2026-08-04"})
        self.assertEqual(c[-1]["windows"]["after"],
                         {"d1": "2026-08-19", "d2": "2026-08-26"})
        self.assertEqual(c[-1]["status"], "SHORTER_EQUAL_WINDOW_PRELIMINARY")

    def test_no_completed_day_after_recent_review_is_pending(self):
        s = analyze_series(original(), as_of="2026-08-19")
        self.assertEqual(s["checkpoints"][-1]["status"], "POST_WINDOW_PENDING")
        self.assertIsNone(s["checkpoints"][-1]["windows"])

    def test_back_to_back_review_dates_do_not_fabricate_event_effect(self):
        rows = [entry("2026-07-01", "2026-07-04", 1),
                entry("2026-07-02", "2026-07-05", 2)]
        c = analyze_series(rows, as_of="2026-08-20",requested_days=30)["checkpoints"]
        self.assertEqual(c[0]["status"], "POST_WINDOW_PENDING")
        self.assertIsNone(c[0]["windows"])
        self.assertEqual(c[1]["effective_days_each"], 30)

    def test_same_day_multiple_reviews_grouped_in_one_checkpoint(self):
        rows = [entry("2026-07-01", "2026-07-04", 1),
                entry("2026-07-02", "2026-07-04", 2),
                entry("2026-07-05", "2026-07-08", 3)]
        c = analyze_series(rows, as_of="2026-08-20",requested_days=30)["checkpoints"]
        self.assertEqual(len(c), 2)
        self.assertEqual(c[0]["recorded_review_rows_on_date"], 2)
        self.assertEqual(c[0]["cumulative_recorded_review_rows"], 2)
        self.assertTrue(c[0]["same_day_events_not_individually_separable"])

    def test_missing_review_not_mistaken_for_new_checkpoint(self):
        rows = original()+[entry("2026-08-30", None, 38)]
        s = analyze_series(rows, as_of="2026-10-22",requested_days=30)
        self.assertEqual(len(s["checkpoints"]), 3)
        self.assertEqual(s["recorded_completed_purchase_rows"], 4)
        self.assertEqual(s["recorded_review_date_rows"], 3)

    def test_provider_data_must_be_exact_per_checkpoint(self):
        s = analyze_series(original(), as_of="2026-08-27")
        observations = {}
        for cp in s["checkpoints"]:
            w = cp["windows"]
            observations[cp["checkpoint_number"]] = {
                "before": metrics(w["before"], 0),
                "after": metrics(w["after"], cp["checkpoint_number"]),
            }
        report = build_series_checkpoint_reports(
            original(), observations, as_of="2026-08-27")
        self.assertEqual(len(report["checkpoints"]), 3)
        self.assertEqual([r["provider_observations"]["estimated_sales_change"]["absolute"]
                          for r in report["checkpoints"]], [1, 2, 3])
        self.assertFalse(report["causal_conclusion"])
        observations[1]["after"]["d2"] = "2026-08-17"
        bad = build_series_checkpoint_reports(
            original(), observations, as_of="2026-08-27")
        self.assertEqual(bad["checkpoints"][0]["status"], "MPSTATS_WINDOWS_INCOMPLETE")
        self.assertEqual(bad["checkpoints"][1]["status"], "SHORTER_EQUAL_WINDOW_PRELIMINARY")

    def test_series_target_conflict_stays_visible(self):
        rows = original()
        rows[-1]["quantity"] = 4
        a = analyze_series(rows, as_of="2026-10-22",requested_days=30)
        self.assertIsNone(a["planned_total_per_card"])
        self.assertEqual(a["series_phase"], "TARGET_CONFLICT")
        self.assertEqual(len(a["checkpoints"]), 3)


if __name__ == "__main__":
    unittest.main()
