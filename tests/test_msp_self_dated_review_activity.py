"""Synthetic daily MPSTATS review activity: averages are not star histograms."""
import unittest

from apps.msp_self_analytics.dated_review_activity import (
    analyze_daily_review_activity, format_daily_review_activity_ru,
)

ARGS={"event_date":"2026-09-21","after_start":"2026-09-22",
      "after_end":"2026-09-24"}


def source(rows):
    return {"status":"VERIFIED_DATED_SOURCE",
        "source_kind":"MPSTATS_VERIFIED_DAILY_REVIEW_ACTIVITY",
        "source_ref":"verified-provider-read",
        "series_kind":"DAILY_NEW_REVIEW_COUNTS",
        "date_granularity":"DAY","rating_scale":"FIVE_STAR",
        "rows":rows}


def row(day,n,avg):
    return {"date":day,"new_reviews":n,"average_rating":avg}


class DatedReviewActivityTests(unittest.TestCase):
    def test_daily_count_and_weighted_mean_never_guess_positive(self):
        data=source([row("2026-09-22",2,5),
                     row("2026-09-23",0,None),
                     row("2026-09-24",1,3)])
        a=analyze_daily_review_activity(data,**ARGS)
        self.assertEqual(a["status"],"DAILY_REVIEW_ACTIVITY_OBSERVED")
        self.assertEqual(a["total_new_reviews"],3)
        self.assertEqual(a["weighted_average_rating"],"4.33")
        self.assertIsNone(a["positive_4_5_reviews"])
        self.assertFalse(a["causal_effect_proven"])
        msg=format_daily_review_activity_ru(a)
        self.assertIn("Новые отзывы",msg)
        self.assertIn("положительных отзывов",msg)
        self.assertIn("неизвестно",msg)

    def test_complete_zero_is_observed_zero_not_unknown(self):
        data=source([row("2026-09-22",0,None),
                     row("2026-09-23",0,0),
                     row("2026-09-24",0,None)])
        a=analyze_daily_review_activity(data,**ARGS)
        self.assertEqual(a["total_new_reviews"],0)
        self.assertIsNone(a["weighted_average_rating"])
        self.assertIsNone(a["positive_4_5_reviews"])

    def test_missing_day_unknown(self):
        data=source([row("2026-09-22",2,5),row("2026-09-24",1,5)])
        a=analyze_daily_review_activity(data,**ARGS)
        self.assertEqual(a["status"],"UNKNOWN")
        self.assertEqual(a["reason"],"MISSING_CALENDAR_DATE")
        self.assertIsNone(a["total_new_reviews"])

    def test_duplicate_day_unknown(self):
        data=source([row("2026-09-22",2,5)]*2)
        a=analyze_daily_review_activity(data,**ARGS)
        self.assertEqual(a["reason"],"DUPLICATE_DATE")

    def test_unverified_source_unknown(self):
        data=source([row("2026-09-22",2,5)])
        data["status"]="UNVERIFIED"
        self.assertEqual(analyze_daily_review_activity(data,**ARGS)["status"],"UNKNOWN")

    def test_bad_rating_and_counter_unknown(self):
        self.assertEqual(analyze_daily_review_activity(
            source([row("2026-09-22",-1,5)]),**ARGS)["reason"],
            "INVALID_NEW_REVIEWS_COUNTER")
        self.assertEqual(analyze_daily_review_activity(
            source([row("2026-09-22",2,6)]),**ARGS)["reason"],
            "AVERAGE_RATING_OUT_OF_SCALE")
        self.assertEqual(analyze_daily_review_activity(
            source([row("2026-09-22",0,5)]),**ARGS)["reason"],
            "AVERAGE_WITHOUT_REVIEWS")

    def test_do_not_include_review_event_day(self):
        with self.assertRaisesRegex(ValueError,"AFTER_WINDOW_INVALID"):
            analyze_daily_review_activity(
                source([]),event_date="2026-09-21",
                after_start="2026-09-21",after_end="2026-09-22")

if __name__=="__main__":
    unittest.main()
