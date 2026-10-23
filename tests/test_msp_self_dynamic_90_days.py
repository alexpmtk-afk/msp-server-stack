"""Owner correction: elapsed complete post-review days, symmetric <=90 by default."""
import unittest
from apps.msp_self_analytics.series_analysis import analyze_series, SeriesDataError
from apps.msp_self_analytics.checkpoint_workflow import plan_checkpoint_reads, assemble_checkpoint_analysis
from apps.msp_self_analytics.checkpoint_report_ru import format_checkpoint_history_ru
from apps.msp_self_analytics.self_purchase_analysis import build_observational_case


def row(date="2026-06-17", *, id=1, plan=2):
    return dict(marketplace="wb",store="laser",marketplace_sku="987654321",
                source_row=id,purchase_date="2026-06-10",review_date=date,
                quantity=plan,purchase_status="completed")


class DynamicNinetyDayTests(unittest.TestCase):
    def test_default_old_review_uses_full_ninety_days_not_thirty(self):
        series=analyze_series([row()],as_of="2026-10-23")
        cp=series["checkpoints"][0]
        self.assertEqual(cp["effective_days_each"],90)
        self.assertEqual(cp["requested_days_each"],90)
        self.assertEqual(cp["status"],"FULL_EQUAL_WINDOW")
        self.assertEqual(cp["windows"]["before"],{"d1":"2026-03-19","d2":"2026-06-16"})
        self.assertEqual(cp["windows"]["after"],{"d1":"2026-06-18","d2":"2026-09-15"})
        self.assertEqual(series["windows"]["after"],cp["windows"]["after"])
        self.assertTrue(cp["windows"]["full_requested_window"])

    def test_exact_30_elapsed_days_now_intermediate_not_final(self):
        cp=analyze_series([row()],as_of="2026-07-18")["checkpoints"][0]
        self.assertEqual(cp["effective_days_each"],30)
        self.assertEqual(cp["windows"]["before"],{"d1":"2026-05-18","d2":"2026-06-16"})
        self.assertEqual(cp["windows"]["after"],{"d1":"2026-06-18","d2":"2026-07-17"})
        self.assertFalse(cp["windows"]["full_requested_window"])
        self.assertEqual(cp["status"],"SHORTER_EQUAL_WINDOW_PRELIMINARY")

    def test_89_then_90_day_boundary(self):
        cp89=analyze_series([row()],as_of="2026-09-15")["checkpoints"][0]
        self.assertEqual(cp89["effective_days_each"],89)
        self.assertFalse(cp89["windows"]["full_requested_window"])
        cp90=analyze_series([row()],as_of="2026-09-16")["checkpoints"][0]
        self.assertEqual(cp90["effective_days_each"],90)
        self.assertTrue(cp90["windows"]["full_requested_window"])
        self.assertEqual(cp90["windows"]["after"]["d2"],"2026-09-15")

    def test_today_and_review_day_excluded(self):
        fresh=analyze_series([row()],as_of="2026-06-18")["checkpoints"][0]
        self.assertEqual(fresh["effective_days_each"],0)
        self.assertIsNone(fresh["windows"])
        first=analyze_series([row()],as_of="2026-06-19")["checkpoints"][0]
        self.assertEqual(first["effective_days_each"],1)
        self.assertEqual(first["windows"]["after"],{"d1":"2026-06-18","d2":"2026-06-18"})

    def test_second_review_censors_first_and_preserves_baseline(self):
        rows=[row(),row("2026-07-17",id=2)]
        s=analyze_series(rows,as_of="2026-10-23")
        c0,c1=s["checkpoints"]
        self.assertEqual(c0["effective_days_each"],29)
        self.assertEqual(c0["windows"]["after"]["d2"],"2026-07-16")
        self.assertEqual(c1["effective_days_each"],90)
        self.assertEqual(c1["windows"]["before"],{"d1":"2026-03-19","d2":"2026-06-16"})
        self.assertEqual(c1["windows"]["after"],{"d1":"2026-07-18","d2":"2026-10-15"})
        self.assertTrue(c0["censored_by_next_review"])

    def test_90_day_provider_requests_and_russian_report_not_30(self):
        rows=[row()]
        plan=plan_checkpoint_reads(rows,as_of="2026-10-23")
        self.assertEqual(plan["provider_read_count"],2)
        self.assertEqual([(r["d1"],r["d2"]) for r in plan["requests"]],
                         [("2026-03-19","2026-06-16"),
                          ("2026-06-18","2026-09-15")])
        obs={r["key"]:dict(request_status="PASS_STRUCTURED",d1=r["d1"],d2=r["d2"],
                           sales=2,revenue=4000,days_in_stock=25)
             for r in plan["requests"]}
        result=assemble_checkpoint_analysis(rows,obs,as_of="2026-10-23")
        self.assertEqual(result["status"],"COMPLETE_DESCRIPTIVE")
        rendered=format_checkpoint_history_ru(result)
        self.assertIn("90 полных дней",rendered)
        self.assertNotIn("не полный 30-дневный итог",rendered)
        self.assertNotIn("Равные укороченные окна",rendered)
        case=build_observational_case(rows,obs,as_of="2026-10-23")
        self.assertEqual(case["status"],"OBSERVATIONAL_REPORT_READY")
        self.assertFalse(case["business_effect_proven"])

    def test_explicit_30_days_allowed_but_never_default(self):
        cp=analyze_series([row()],as_of="2026-10-23",requested_days=30)["checkpoints"][0]
        self.assertEqual(cp["effective_days_each"],30)
        self.assertEqual(cp["windows"]["before"]["d1"],"2026-05-18")
        with self.assertRaisesRegex(SeriesDataError,"INVALID_WINDOW_DAYS"):
            analyze_series([row()],as_of="2026-10-23",requested_days=91)
        with self.assertRaisesRegex(SeriesDataError,"INVALID_WINDOW_DAYS"):
            analyze_series([row()],as_of="2026-10-23",requested_days=0)


if __name__ == "__main__":
    unittest.main()
