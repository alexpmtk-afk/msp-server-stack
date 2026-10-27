"""Conclusions must never assert changes absent from individual MPSTATS records."""
import unittest
from scripts.remote.msp_self_sku_report_cli import format_checkpoint_conclusion


class ConclusionTests(unittest.TestCase):
    def test_no_numeric_source_means_unknown_not_small_or_changed(self):
        result=format_checkpoint_conclusion(
            {"checkpoint_number":1,
             "provider_observations":{},
             "stock_normalized_orders":{"status":"UNKNOWN"}},
            {})
        self.assertIn("неизвестна",result)
        self.assertNotIn("выборка оценочных заказов мала",result)
        self.assertNotIn("дни наличия различаются",result)
        self.assertNotIn("цена",result)

    def test_real_low_sample_and_changed_stock_get_warnings(self):
        result=format_checkpoint_conclusion(
            {"checkpoint_number":2,
             "provider_observations":{"before":{"sales":1},"after":{"sales":1}},
             "stock_normalized_orders":{
                 "status":"READY_LOW_SAMPLE",
                 "rate_percent_change":-34.6,
                 "small_observed_sample":True,
                 "stock_coverage_differs":True}},
            {"observed_positive_text_entries":1})
        self.assertIn("не изменились",result)
        self.assertIn("-34,6%",result)
        self.assertIn("выборка оценочных заказов мала",result)
        self.assertIn("дни наличия различаются",result)
        self.assertIn("записей 4–5★ с текстом: 1",result)
        self.assertIn("полнота неизвестна",result)
        self.assertNotIn("цены менялись",result)

    def test_rate_zero_reference_not_calculated(self):
        result=format_checkpoint_conclusion(
            {"checkpoint_number":3,
             "provider_observations":{"before":{"sales":0},"after":{"sales":4}},
             "stock_normalized_orders":{"status":"READY_DESCRIPTIVE",
                                         "rate_percent_change":None,
                                         "small_observed_sample":False,
                                         "stock_coverage_differs":False}},
            {"observed_positive_text_entries":None})
        self.assertIn("выросли",result)
        self.assertIn("процентное изменение",result)
        self.assertNotIn("выборка оценочных заказов мала",result)


if __name__=="__main__":
    unittest.main()
