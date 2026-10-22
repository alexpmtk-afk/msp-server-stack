"""Series correction: one source row = one purchase, repeated quantity is target."""
import importlib.util
from pathlib import Path
import unittest
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("self_series",root/"apps/msp_self_analytics/series_analysis.py")
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def urn_rows(plan=5):
    return [
       {"source_row":22,"marketplace":"wb","store":"laser","marketplace_sku":"336659148",
        "quantity":plan,"purchase_date":"2026-07-24","review_date":"2026-08-05"},
       {"source_row":28,"marketplace":"wb","store":"laser","marketplace_sku":"336659148",
        "quantity":plan,"purchase_date":"2026-07-30","review_date":"2026-08-07"},
       {"source_row":34,"marketplace":"wb","store":"laser","marketplace_sku":"336659148",
        "quantity":plan,"purchase_date":"2026-08-07","review_date":"2026-08-18"},
    ]

class TestSeries(unittest.TestCase):
    def test_urn_three_of_five_not_fifteen(self):
        a=m.analyze_series(urn_rows(),as_of="2026-10-22")
        self.assertEqual(a["planned_total_per_card"],5)
        self.assertEqual(a["recorded_completed_purchase_rows"],3)
        self.assertEqual(a["recorded_purchase_occurrences"],3)
        self.assertEqual(a["recorded_review_date_rows"],3)
        self.assertEqual(a["remaining_against_plan"],2)
        self.assertEqual(a["series_phase"],"INTERMEDIATE_SERIES")
        self.assertFalse(a["five_star_public_rating_confirmed_from_registry"])
        self.assertEqual(a["first_review_date"],"2026-08-05")
        self.assertEqual(a["latest_review_date"],"2026-08-18")
        self.assertEqual(a["windows"]["before"],{"d1":"2026-07-06","d2":"2026-08-04"})
        self.assertEqual(a["windows"]["after"],{"d1":"2026-08-19","d2":"2026-09-17"})
        self.assertTrue(a["windows"]["full_requested_window"])
        self.assertTrue(a["windows"]["intermediate_observation"])

    def test_can_compare_after_third_without_fifth(self):
        a=m.analyze_series(urn_rows(),as_of="2026-08-27")
        self.assertEqual(a["status"],"SHORTER_EQUAL_WINDOW_PRELIMINARY")
        self.assertEqual(a["windows"]["effective_days_each"],8)
        self.assertEqual(a["windows"]["before"]["d2"],"2026-08-04")
        self.assertEqual(a["windows"]["after"]["d1"],"2026-08-19")
        self.assertEqual(a["windows"]["after"]["d2"],"2026-08-26")

    def test_no_finished_post_day_is_pending(self):
        a=m.analyze_series(urn_rows(),as_of="2026-08-19")
        self.assertEqual(a["status"],"POST_WINDOW_PENDING")
        self.assertIsNone(a["windows"])

    def test_not_yet_reviewed_row_is_not_published_feedback(self):
        r=urn_rows()
        r.append({**r[-1],"source_row":40,"purchase_date":"2026-08-23","review_date":None})
        a=m.analyze_series(r,as_of="2026-10-22")
        self.assertEqual(a["recorded_completed_purchase_rows"],4)
        self.assertEqual(a["recorded_review_date_rows"],3)
        self.assertEqual(a["rows_without_review_date"],1)
        self.assertEqual(a["remaining_against_plan"],1)

    def test_full_series_five_rows_uses_final_review(self):
        r=urn_rows()
        for i,date in enumerate(("2026-08-24","2026-09-01"),1):
            r.append({**r[-1],"source_row":40+i,
                "purchase_date":date,"review_date":("2026-08-31" if i==1 else "2026-09-08")})
        a=m.analyze_series(r,as_of="2026-10-22")
        self.assertEqual(a["series_phase"],"REPORTED_SERIES_COMPLETE_PUBLICATION_UNVERIFIED")
        self.assertEqual(a["latest_review_date"],"2026-09-08")
        self.assertEqual(a["windows"]["after"]["d1"],"2026-09-09")
        self.assertFalse(a["windows"]["intermediate_observation"])

    def test_conflicting_target_is_explicit_not_summed(self):
        r=urn_rows()
        r[1]["quantity"]=4
        a=m.analyze_series(r,as_of="2026-10-22")
        self.assertEqual(a["series_phase"],"TARGET_CONFLICT")
        self.assertIsNone(a["planned_total_per_card"])
        self.assertEqual(a["planned_total_values_conflict"],[4,5])

    def test_different_marketplace_or_sku_must_never_mix(self):
        r=urn_rows()
        r[2]["marketplace_sku"]="111333555"
        with self.assertRaisesRegex(m.SeriesDataError,"MIXED_CARD_IDENTITIES"):
            m.analyze_series(r,as_of="2026-10-22")

    def test_duplicate_source_row_rejected(self):
        r=urn_rows();r[1]["source_row"]=22
        with self.assertRaisesRegex(m.SeriesDataError,"DUPLICATE_SOURCE_ROW"):
            m.analyze_series(r,as_of="2026-10-22")

    def test_public_reviews_not_automatically_verified(self):
        a=m.analyze_series(urn_rows(),as_of="2026-10-22")
        self.assertIsNone(a["independently_verified_distinct_review_count"])
        self.assertFalse(a["individual_publication_dates_independently_verified"])
        self.assertFalse(a["sale_effect_not_proven"] is False)

    def test_case_without_review_date_is_not_eligible(self):
        r=urn_rows()[:1];r[0]["review_date"]=None
        a=m.analyze_series(r,as_of="2026-10-22")
        self.assertEqual(a["status"],"NO_REVIEW_DATE")
        self.assertIsNone(a["windows"])

if __name__=="__main__":
    unittest.main()
