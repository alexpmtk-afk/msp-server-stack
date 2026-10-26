"""Synthetic, verified-date semantics only; never inferred review impact."""
import unittest

from apps.msp_self_analytics.dated_rating_dynamics import (
    analyze_dated_positive_ratings,format_dated_positive_ratings_ru,
)


def item(day,total,negative,text,negative_text):
    return {"date":day,"ratings_total":total,
            "ratings_negative":negative,"ratings_with_text":text,
            "ratings_negative_with_text":negative_text}


def source(rows,kind="DAILY_NEW_COUNTS"):
    return {
        "status":"VERIFIED_DATED_SOURCE",
        "source_kind":"MPSTATS_VERIFIED_DATED_RATING_AGGREGATES",
        "source_ref":"independently-checked-provider-date-shape",
        "date_granularity":"DAY","rating_scale":"FIVE_STAR",
        "negative_stars":[1,2,3],"series_kind":kind,"rows":rows}


ARGS=dict(event_date="2026-09-21",after_start="2026-09-22",
          after_end="2026-09-24")


class RatingHistoryTests(unittest.TestCase):
    def test_exact_daily_positive_total_and_text(self):
        x=source([item("2026-09-22",6,2,3,1),
                  item("2026-09-23",1,0,1,0),
                  item("2026-09-24",2,1,1,1)])
        y=analyze_dated_positive_ratings(x,**ARGS)
        self.assertEqual(y["status"],"DAILY_POSITIVE_COUNTS_OBSERVED")
        self.assertEqual(y["positive_ratings_4_5"],6)
        self.assertEqual(y["positive_reviews_with_text_4_5"],3)
        self.assertFalse(y["net_change_only"])
        self.assertFalse(y["effect_proven"])
        self.assertFalse(y["distinct_other_buyers_verified"])
        self.assertIn("6 положительных",format_dated_positive_ratings_ru(y))

    def test_missing_day_unknown_not_zero(self):
        x=source([item("2026-09-22",0,0,0,0),
                  item("2026-09-24",0,0,0,0)])
        y=analyze_dated_positive_ratings(x,**ARGS)
        self.assertEqual(y["status"],"UNKNOWN")
        self.assertIsNone(y["positive_ratings_4_5"])

    def test_disallow_unverified_current_snapshots(self):
        x=source([item("2026-09-22",1,0,0,0)])
        x["status"]="UNVERIFIED_ASOF_RATING"
        y=analyze_dated_positive_ratings(x,**ARGS)
        self.assertEqual(y["reason"],"SOURCE_CONTRACT_NOT_VERIFIED")

    def test_cumulative_only_net_not_new_events(self):
        x=source([item("2026-09-21",20,3,12,2),
                  item("2026-09-24",27,4,18,3)],
                 kind="CUMULATIVE_SNAPSHOTS")
        y=analyze_dated_positive_ratings(x,**ARGS)
        self.assertEqual(y["status"],"NET_RATING_COUNT_CHANGE_ONLY")
        self.assertEqual(y["positive_ratings_4_5"],6)
        self.assertEqual(y["positive_reviews_with_text_4_5"],5)
        self.assertTrue(y["net_change_only"])
        self.assertIn("не точное число",format_dated_positive_ratings_ru(y))

    def test_cumulative_negative_revision_unknown(self):
        x=source([item("2026-09-21",12,3,8,2),
                  item("2026-09-24",11,3,8,2)],
                 kind="CUMULATIVE_SNAPSHOTS")
        y=analyze_dated_positive_ratings(x,**ARGS)
        self.assertEqual(y["reason"],"CUMULATIVE_COUNTER_DECREASE_OR_MODERATION")

    def test_baseline_absent_does_not_assume_zero(self):
        x=source([item("2026-09-24",7,0,4,0)],
                 kind="CUMULATIVE_SNAPSHOTS")
        y=analyze_dated_positive_ratings(x,**ARGS)
        self.assertEqual(y["reason"],"BASELINE_OR_END_SNAPSHOT_MISSING")

    def test_duplicates_and_inconsistent_subcounts(self):
        a=item("2026-09-22",2,0,1,0)
        y=analyze_dated_positive_ratings(source([a,a]),**ARGS)
        self.assertEqual(y["reason"],"DUPLICATE_DATED_ITEM")
        b=item("2026-09-22",2,1,2,2)
        y=analyze_dated_positive_ratings(source([b]),**ARGS)
        self.assertEqual(y["reason"],"INCONSISTENT_RATING_COUNTS")

    def test_event_day_not_in_after_window(self):
        x=source([item("2026-09-21",1,0,1,0)])
        with self.assertRaisesRegex(ValueError,"AFTER_WINDOW_INVALID"):
            analyze_dated_positive_ratings(
                x,event_date="2026-09-21",
                after_start="2026-09-21",after_end="2026-09-22")

    def test_empty_source_unknown_not_zero(self):
        y=analyze_dated_positive_ratings(None,**ARGS)
        self.assertEqual(y["status"],"UNKNOWN")
        self.assertIsNone(y["positive_reviews_with_text_4_5"])
        self.assertIn("неизвестно",format_dated_positive_ratings_ru(y))

if __name__=="__main__":
    unittest.main()
