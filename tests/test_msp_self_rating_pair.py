"""Synthetic two-sided rating checks; no causal claims."""
import unittest
from apps.msp_self_analytics.dated_rating_dynamics import compare_dated_rating_periods

def item(day, total, neg, text, neg_text):
    return dict(date=day, ratings_total=total, ratings_negative=neg,
                ratings_with_text=text, ratings_negative_with_text=neg_text)

def source(rows, kind="DAILY_NEW_COUNTS"):
    return dict(status="VERIFIED_DATED_SOURCE",
                source_kind="MPSTATS_VERIFIED_DATED_RATING_AGGREGATES",
                source_ref="synthetic-verified-contract",date_granularity="DAY",
                rating_scale="FIVE_STAR",negative_stars=[1,2,3],
                series_kind=kind,rows=rows)

ARGS=dict(event_date="2026-09-25", before_start="2026-09-23",
          before_end="2026-09-24", after_start="2026-09-26",
          after_end="2026-09-27")

class TwoSidedRatingTests(unittest.TestCase):
    def test_daily_new_positive_counts_both_periods(self):
        rows=[
            item("2026-09-23",3,1,2,1), item("2026-09-24",3,1,2,1),
            item("2026-09-26",5,2,3,1), item("2026-09-27",5,2,3,1)]
        r=compare_dated_rating_periods(source(rows),**ARGS)
        self.assertEqual(r["status"],"COMPARABLE_DAILY_COUNTS")
        self.assertEqual(r["before"]["positive_ratings_4_5"],4)
        self.assertEqual(r["after"]["positive_ratings_4_5"],6)
        self.assertEqual(r["change"]["positive_ratings_4_5"],2)
        self.assertEqual(r["change"]["positive_reviews_with_text_4_5"],2)
        self.assertEqual(r["change"]["positive_ratings_without_text_4_5"],0)
        self.assertFalse(r["causal_effect_proven"])
    def test_cumulative_deletion_is_net_not_new_posts(self):
        rows=[
            item("2026-09-22",10,4,6,2),item("2026-09-24",9,4,5,2),
            item("2026-09-25",9,4,5,2),item("2026-09-27",10,4,6,2)]
        r=compare_dated_rating_periods(source(rows,"CUMULATIVE_SNAPSHOTS"),**ARGS)
        self.assertEqual(r["status"],"COMPARABLE_NET_CHANGES")
        self.assertEqual(r["before"]["positive_ratings_4_5"],-1)
        self.assertEqual(r["after"]["positive_ratings_4_5"],1)
        self.assertEqual(r["change"]["positive_ratings_4_5"],2)
        self.assertTrue(r["before"]["net_change_only"])
    def test_unverified_series_is_unknown(self):
        r=compare_dated_rating_periods(None,**ARGS)
        self.assertEqual(r["status"],"PARTIAL_OR_UNKNOWN")
        self.assertIsNone(r["change"]["positive_ratings_4_5"])
    def test_non_equal_windows_refused(self):
        with self.assertRaisesRegex(ValueError,"EQUAL_COMPLETED_WINDOWS_REQUIRED"):
            compare_dated_rating_periods(None,**{**ARGS,"before_start":"2026-09-22"})

if __name__=="__main__":
    unittest.main()
