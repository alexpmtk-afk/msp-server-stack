"""Synthetic regression fixtures for read-only MPSTATS keyword/shelf evidence."""
import unittest
from apps.msp_self_analytics.external_visibility_evidence import (
    analyze_keyword_history, compare_shelf_visibility, format_keyword_price_observations_ru,
)


def kws():
    return {"startRow":0,"endRow":2,"total":2,
        "data":{"dates":{
            "2026-09-22":{"client_price":1500,"sales":1},
            "2026-09-23":{"client_price":1500,"sales":0},
            "2026-09-25":{"client_price":1200,"sales":2},
            "2026-09-28":{"client_price":1300,"sales":0}},
            "words":[
                {"query":"private query that must not escape",
                 "dates":{"2026-09-22":{"position":5,"organic_position":2},
                          "2026-09-25":{"position":10}}},
                {"query":"another private query",
                 "dates":{"2026-09-28":{"position":12}}}]}}


class ExternalEvidenceTests(unittest.TestCase):
    def test_nested_words_and_daily_history_without_fabricating_missing_days(self):
        r=analyze_keyword_history(kws(),d1="2026-09-22",d2="2026-09-28")
        self.assertEqual(r["status"],"OBSERVED_SPARSE_PROVIDER_HISTORY")
        self.assertEqual(r["returned_word_rows"],2)
        self.assertEqual(r["word_day_entries"],3)
        self.assertEqual(r["word_distinct_days"],3)
        self.assertEqual(r["daily_observed_days"],4)
        self.assertEqual(r["daily_client_price_positive_days"],4)
        self.assertEqual(r["unobserved_calendar_days"],3)
        self.assertEqual(r["observed_client_price_levels"],3)
        self.assertEqual(len(r["observed_price_transitions"]),2)
        self.assertEqual(r["observed_price_transitions"][0]["observed_price_delta"],-300)
        self.assertEqual(r["observed_price_transitions"][0]["calendar_days_between_observations"],2)
        self.assertFalse(r["seller_price_corrections_inferred"])
        self.assertFalse(r["verified_buyer_paid_price"])
        self.assertNotIn("query",str(r))
        self.assertNotIn("private",str(r))

    def test_unknown_prices_do_not_become_zeros_and_no_transitions(self):
        x=kws()
        x["data"]["dates"]["2026-09-22"]["client_price"]=0
        x["data"]["dates"]["2026-09-25"]["client_price"]=None
        x["data"]["dates"]["2026-09-28"]["client_price"]=float("nan")
        a=analyze_keyword_history(x,d1="2026-09-22",d2="2026-09-28")
        self.assertEqual(a["daily_client_price_positive_days"],1)
        self.assertEqual(a["observed_price_transitions"],[])
        self.assertEqual(a["daily_observed_days"],4)

    def test_partial_query_pagination_never_claims_complete(self):
        x=kws()
        x["total"]=51
        a=analyze_keyword_history(x,d1="2026-09-22",d2="2026-09-28")
        self.assertFalse(a["all_word_rows_received"])
        self.assertEqual(a["provider_reported_total_words"],51)
        self.assertEqual(a["status"],"PARTIAL_KEYWORD_PAGINATION")
        msg=format_keyword_price_observations_ru(a,a)
        self.assertIn("неполная постраничная выдача",msg)
        self.assertNotIn("Переходов между",msg)

    def test_missing_pagination_total_is_not_treated_as_complete(self):
        x=kws()
        x.pop("total")
        a=analyze_keyword_history(x,d1="2026-09-22",d2="2026-09-28")
        self.assertEqual(a["daily_client_price_positive_days"],4)
        self.assertFalse(a["all_word_rows_received"])
        self.assertEqual(a["status"],"PARTIAL_KEYWORD_PAGINATION")
        self.assertIn("неполная постраничная выдача",
            format_keyword_price_observations_ru(a,a))

    def test_outside_date_is_not_included(self):
        x=kws()
        x["data"]["dates"]["2026-08-01"]={"client_price":500}
        x["data"]["words"][0]["dates"]["2026-08-01"]={"position":1}
        a=analyze_keyword_history(x,d1="2026-09-22",d2="2026-09-28")
        self.assertEqual(a["daily_observed_days"],4)
        self.assertEqual(a["word_day_entries"],3)

    def test_invalid_observations_and_bad_window(self):
        self.assertEqual(analyze_keyword_history({"data":[]},
            d1="2026-09-22",d2="2026-09-28")["status"],
            "UNVERIFIED_KEYWORD_RESPONSE")
        with self.assertRaises(ValueError):
            analyze_keyword_history(kws(),d1="2026-09-29",d2="2026-09-22")

    def test_shelf_aggregate_179_is_not_detailed_177_or_impressions(self):
        rows=[{"positions":{"2026-09-22":{"ads":0}}},
              {"positions":{"2026-09-23":{"ads":1},
                            "2026-09-25":{"ads":0}}}]
        a=compare_shelf_visibility({"visibility_count":5,"items":2},
            {"total":2,"data":rows},
            d1="2026-09-22",d2="2026-09-28")
        self.assertEqual(a["status"],"OBSERVED_AGGREGATE_DETAIL_MISMATCH")
        self.assertEqual(a["aggregate_detail_discrepancy"],2)
        self.assertEqual(a["detail_host_date_entries"],3)
        self.assertEqual(a["detail_observed_days"],3)
        self.assertEqual(a["detail_paid_position_entries"],1)
        self.assertFalse(a["aggregate_count_equals_human_impressions"])
        self.assertFalse(a["paid_marker_equals_seller_ad_spend"])

    def test_russian_numeric_provider_price_changes_are_not_seller_edit_claims(self):
        original=kws()
        after=analyze_keyword_history(original,d1="2026-09-22",d2="2026-09-28")
        before=analyze_keyword_history(original,d1="2026-09-22",d2="2026-09-28")
        text=format_keyword_price_observations_ru(before,after,max_changes=1)
        self.assertIn("client_price ПОСЛЕ: 2026-09-23 (1500) → 2026-09-25 (1200)",text)
        self.assertIn("точный вид цены и единицы ещё не подтверждены",text)
        self.assertIn("Дополнительно 1 переходов",text)
        self.assertNotIn("private query",text)
        self.assertNotIn("изменения цены продавца из журнала МСП доказаны",text)

    def test_incomplete_shelves_pagination_refuses_numeric_comparison(self):
        x=compare_shelf_visibility({"visibility_count":100},
            {"total":100,"data":[{"positions":{}}]},
            d1="2026-09-22",d2="2026-09-28")
        self.assertEqual(x["status"],"DETAIL_PAGINATION_INCOMPLETE")
        self.assertIsNone(x["aggregate_detail_discrepancy"])

if __name__=="__main__": unittest.main()
