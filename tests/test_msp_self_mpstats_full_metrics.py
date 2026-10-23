"""Unit coverage of actual MPSTATS WB full period_stats field semantics."""
import unittest
from apps.msp_self_analytics.mpstats_full_metrics import (
    extract_full_period_metrics, pair_period_metrics)
from apps.msp_self_analytics.checkpoint_workflow import (
    plan_checkpoint_reads, assemble_checkpoint_analysis)
from apps.msp_self_analytics.checkpoint_report_ru import format_checkpoint_history_ru


def events():
    return [
        dict(marketplace="wb",store="laser",marketplace_sku="123456789",
             source_row=i,purchase_date=p,review_date=r,quantity=5)
        for i,(p,r) in enumerate([
            ("2026-07-24","2026-08-05"),
            ("2026-07-30","2026-08-07"),
            ("2026-08-07","2026-08-18")], 1)
    ]


class MpstatsExpandedFieldsTests(unittest.TestCase):
    def test_field_names_not_hallucinated_and_zero_not_missing(self):
        src = {
          "sales":0, "revenue":0, "days_in_stock":0,
          "purchase":74, "purchase_after_return":68,
          "sales_estimated":10, "revenue_estimated":10000,
          "id":123456789, "rating":4.8,
        }
        x=extract_full_period_metrics(src)
        self.assertEqual(x["metrics"]["sales"],0.0)
        self.assertEqual(x["metrics"]["purchase"],74.0)
        self.assertIsNone(x["metrics"]["lost_profit"])
        self.assertNotIn("id",x["metrics"])
        self.assertFalse(x["provider_purchase_fields_unit_verified"])
        self.assertFalse(x["actual_seller_paid_orders_verified"])
        self.assertTrue(x["provider_estimate_includes_self_purchases"])

    def test_non_numeric_nan_negative_booleans_not_fact(self):
        x=extract_full_period_metrics({
            "purchase":True,"purchase_after_return":float("nan"),
            "sales":"3","revenue":-100
        })
        self.assertTrue({"purchase","purchase_after_return","sales","revenue"}.issubset(
            set(x["fields_non_numeric"])))
        self.assertIsNone(x["metrics"]["sales"])

    def test_units_not_interchanged_or_returns_fabricated(self):
        a=extract_full_period_metrics({
            "sales":3,"revenue":300,"purchase":64,"purchase_after_return":59})
        b=extract_full_period_metrics({
            "sales":5,"revenue":520,"purchase":68,"purchase_after_return":61})
        comparison=pair_period_metrics(a,b)
        self.assertEqual(comparison["fields"]["sales"]["absolute_change"],2)
        self.assertEqual(comparison["fields"]["revenue"]["absolute_change"],220)
        self.assertEqual(comparison["fields"]["purchase"]["absolute_change"],4)
        self.assertEqual(comparison["return_count"],"UNKNOWN")
        self.assertFalse(comparison["money_is_verified_payment"])
        self.assertFalse(comparison["causal_inference"])

    def test_exact_source_window_required_before_extras_render(self):
        plan=plan_checkpoint_reads(events(),as_of="2026-10-23")
        observations={}
        for task in plan["requests"]:
            observations[task["key"]]={
                "request_status":"PASS_STRUCTURED",
                "d1":task["d1"],"d2":task["d2"],
                "sales":1, "revenue":1500, "days_in_stock":1,
                "purchase":70,"purchase_after_return":67,
                "sales_estimated":2,"revenue_estimated":1800,
            }
        report=assemble_checkpoint_analysis(events(),observations,as_of="2026-10-23")
        cp=report["checkpoints"][-1]
        m=cp["additional_mpstats_metrics"]["fields"]
        self.assertEqual(m["revenue"]["before"],1500)
        self.assertEqual(m["sales_estimated"]["after"],2)
        rendered=format_checkpoint_history_ru(report)
        self.assertIn("Сумма оценочных заказов",rendered)
        self.assertIn("revenue_estimated",rendered)
        self.assertIn("purchase_after_return",rendered)
        self.assertIn("единицы",rendered)

    def test_broken_source_window_not_passed_as_valid_extra_metrics(self):
        plan=plan_checkpoint_reads(events(),as_of="2026-10-23")
        obs={}
        for task in plan["requests"]:
            obs[task["key"]]={
                "request_status":"PASS_STRUCTURED",
                "d1":task["d1"],"d2":task["d2"],"sales":1,
                "revenue":1500,"days_in_stock":1,"purchase":70,
            }
        key=plan["checkpoint_to_requests"][3]["after"]
        obs[key]["d2"]="2026-01-01"
        report=assemble_checkpoint_analysis(events(),obs,as_of="2026-10-23")
        cp=report["checkpoints"][-1]
        self.assertEqual(cp["status"],"MPSTATS_WINDOWS_INCOMPLETE")
        self.assertNotIn("additional_mpstats_metrics",cp)
        self.assertIn("нет двух проверенных ответов",format_checkpoint_history_ru(report))

    def test_absent_amount_is_unknown_not_zero(self):
        pair=pair_period_metrics(
            extract_full_period_metrics({"sales":2}),
            extract_full_period_metrics({"sales":3,"revenue":90}))
        self.assertEqual(pair["fields"]["revenue"]["state"],"UNKNOWN")
        self.assertIsNone(pair["fields"]["revenue"]["absolute_change"])


if __name__=="__main__":
    unittest.main()
