"""Pure, synthetic regression tests: peer data never establish causal controls."""
import unittest
from apps.msp_self_analytics.peer_history_context import (
    summarize_peer_history, format_peer_history_ru,
)


def observation(orders, stock, quality="OBSERVATIONAL_MPSTATS"):
    return {"state":"PASS_STRUCTURED","quality":quality,
            "estimated_orders":orders,"days_in_stock":stock}


def fixture():
    return {"status":"PASS_CANDIDATE_CONTEXT_ONLY","verified_comparators":0,
        "eligible_causal_controls":0,"review_day_excluded":True,
        "window_days":7,
        "date_windows":{"before":{"d1":"2026-09-01","d2":"2026-09-07"},
                        "after":{"d1":"2026-09-09","d2":"2026-09-15"}},
        "own":{"before":observation(4,5),"after":observation(8,6)},
        "candidates":[{"verified_comparator":False,"used_as_causal_control":False,
            "source_relation":"MPSTATS_SIMILAR_CANDIDATE_NOT_VERIFIED",
            "before":observation(50,7),"after":observation(21,7)}]}


class PeerContextTest(unittest.TestCase):
    def test_complete_descriptive_observations_and_ru_warnings(self):
        a=summarize_peer_history(fixture())
        self.assertEqual(a["status"],"EXPLORATORY_CANDIDATE_CONTEXT_ONLY")
        self.assertFalse(a["qualified_control_group"])
        self.assertEqual(a["verified_comparators"],0)
        self.assertAlmostEqual(a["own"]["rate_change_percent"],66.66666666666666)
        self.assertEqual(a["candidate_histories_with_data"],1)
        self.assertTrue(a["own"]["small_sample"])
        self.assertFalse(a["economics_from_peer_change_allowed"])
        rendered=format_peer_history_ru(a)
        self.assertIn("ПРЕДВАРИТЕЛЬНЫЙ",rendered)
        self.assertIn("Малая выборка",rendered)
        self.assertIn("Сопоставимость товаров не подтверждена",rendered)
        self.assertNotIn("SKU",rendered)

    def test_wrong_window_and_review_day_included_blocked(self):
        x=fixture()
        x["date_windows"]["after"]["d1"]="2026-09-08"
        with self.assertRaisesRegex(ValueError,"WINDOWS_NOT_EQUAL"):
            summarize_peer_history(x)
        x=fixture()
        x["window_days"]=90
        with self.assertRaisesRegex(ValueError,"WINDOW_INTEGRITY"):
            summarize_peer_history(x)

    def test_unavailable_or_zero_stock_is_unknown_not_zero(self):
        x=fixture()
        x["candidates"][0]["after"]["days_in_stock"]=0
        r=summarize_peer_history(x)
        self.assertEqual(r["status"],"PARTIAL_CONTEXT_UNKNOWN")
        self.assertEqual(r["candidate_histories_with_data"],0)
        self.assertEqual(r["candidates"][0]["metrics"]["status"],"UNKNOWN_WINDOW_DATA")

    def test_no_percent_change_when_own_base_zero(self):
        x=fixture()
        x["own"]["before"]["estimated_orders"]=0
        a=summarize_peer_history(x)
        self.assertIsNone(a["own"]["rate_change_percent"])
        self.assertIn("процент не рассчитывается от нуля",format_peer_history_ru(a))

    def test_no_verified_comparators_can_be_inferred(self):
        x=fixture()
        x["verified_comparators"]=1
        with self.assertRaisesRegex(ValueError,"VERIFIED_CONTROL"):
            summarize_peer_history(x)
        x=fixture()
        x["candidates"][0]["verified_comparator"]=True
        with self.assertRaisesRegex(ValueError,"CANDIDATE_VERIFICATION"):
            summarize_peer_history(x)

    def test_missing_provider_dates_fail_closed(self):
        x=fixture()
        x["own"]["before"]["quality"]="UNVERIFIED"
        a=summarize_peer_history(x)
        self.assertEqual(a["own"]["status"],"UNKNOWN_WINDOW_DATA")
        self.assertEqual(a["status"],"PARTIAL_CONTEXT_UNKNOWN")

if __name__=="__main__":
    unittest.main()
