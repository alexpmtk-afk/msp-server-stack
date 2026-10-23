"""Price change journal as a noncausal explanatory context for review stages."""
import unittest
from apps.msp_self_analytics.checkpoint_workflow import (
    plan_checkpoint_reads, assemble_checkpoint_analysis)
from apps.msp_self_analytics.price_event_context import price_event_context


def row(p,r,i):
    return dict(marketplace="wb",store="laser",marketplace_sku="123456789",
                quantity=5,purchase_date=p,review_date=r,source_row=i)

ROWS=[row("2026-07-24","2026-08-05",1),
      row("2026-07-30","2026-08-07",2),
      row("2026-08-07","2026-08-18",3)]


def base():
    plan=plan_checkpoint_reads(ROWS,as_of="2026-10-23")
    payload={spec["key"]:{
        "request_status":"PASS_STRUCTURED","d1":spec["d1"],"d2":spec["d2"],
        "sales":0,"days_in_stock":1} for spec in plan["requests"]}
    return assemble_checkpoint_analysis(ROWS,payload,as_of="2026-10-23")


class PriceContextTests(unittest.TestCase):
    def test_price_event_on_second_period_flagged_but_not_causal(self):
        result=price_event_context(base(),
            [{"event_date":"2026-08-06"},{"event_date":"2026-08-08"},
             {"event_date":"2026-09-01"}],source_status="VERIFIED_READONLY_VIEW")
        cp=result["checkpoints"]
        self.assertEqual(cp[0]["recorded_price_changes_after_window"],1)
        self.assertTrue(cp[0]["confounding_price_events"])
        self.assertEqual(cp[1]["recorded_price_changes_after_window"],1)
        self.assertEqual(cp[2]["recorded_price_changes_after_window"],1)
        self.assertFalse(result["historical_price_levels_independently_verified"])

    def test_events_in_gap_are_context_not_current_post(self):
        result=price_event_context(base(),[
            {"event_date":"2026-08-07"}],
            source_status="VERIFIED_READONLY_VIEW")
        self.assertEqual(result["checkpoints"][0]["recorded_price_changes_after_window"],0)
        self.assertEqual(result["checkpoints"][1]["recorded_price_changes_between_windows"],1)
        self.assertEqual(result["checkpoints"][2]["recorded_price_changes_between_windows"],1)

    def test_unavailable_view_never_claims_stable_price(self):
        x=price_event_context(base(),[],source_status="UNAVAILABLE")
        self.assertEqual(x["status"],"UNKNOWN_PRICE_HISTORY")
        self.assertEqual(x["checkpoints"],[])

    def test_no_entries_does_not_prove_flat_marketplace_price(self):
        x=price_event_context(base(),[],source_status="VERIFIED_READONLY_VIEW")
        self.assertEqual(x["checkpoints"][0]["status"],"NO_RECORDED_PRICE_EVENTS_IN_PERIOD")
        self.assertTrue(x["no_events_does_not_prove_no_price_changes"])

    def test_invalid_rows_are_counted_not_coerced(self):
        x=price_event_context(base(),[
            {"event_date":"2026-08-50"}, {"event_date":None}],
            source_status="VERIFIED_READONLY_VIEW")
        self.assertEqual(x["status"],"PARTIAL_INVALID_DATES")
        self.assertEqual(x["invalid_date_rows"],2)


if __name__=="__main__":
    unittest.main()
