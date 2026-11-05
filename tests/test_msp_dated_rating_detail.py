import unittest
from unittest.mock import patch

from apps.msp_self_analytics.rating_history_query import summarize_history, format_history_ru, review_date_summary, format_review_date_summary_ru
from apps.msp_self_analytics.dated_rating_detail import enrich_public_fallback


class DatedDetailTests(unittest.TestCase):
    def history(self, records):
        return summarize_history(marketplace='wb', sku='123', d1='2026-10-01',
            d2='2026-10-31', comments={'comments': records}, period=[])

    def test_empty_text_still_prints_exact_date_and_stars(self):
        h=self.history([{'date':'2026-10-04','valuation':2,'text':''}])
        self.assertIn('2026-10-04 | 2★', format_history_ru(h))

    def test_stale_records_report_real_latest_date_not_cache_date(self):
        h=self.history([{'date':'2026-06-10','valuation':4,'text':''}])
        self.assertEqual(h['review_feed_diagnostics']['latest_record_date'],'2026-06-10')
        self.assertIn('2026-06-10',format_history_ru(h))

    def test_registered_event_report_also_prints_dated_stars(self):
        h=self.history([{'date':'2026-10-04','valuation':2,'text':''},
                        {'date':'2026-10-05','valuation':5,'text':''}])
        summary=review_date_summary(h,review_date='2026-10-05')
        text=format_review_date_summary_ru(summary)
        self.assertIn('2026-10-04 | 2★',text)
        self.assertNotIn('2026-10-05 | 5★',text)

    def test_fallback_preserves_separate_source_and_filters_exact_sku(self):
        class Reader:
            calls=3
            def call(self, name, args):
                self.calls+=1
                return {'id':123,'photo':{'list':[{'f':'https://basket-01.wbbasket.ru/vol0/part0/123/images/big/1.webp'}]}},'PASS_JSON'
        h=self.history([])
        payload={'records':[{'id':'x','sku':'123','published_at_utc':'2026-10-04T12:00:00+00:00','valuation':5},
                            {'id':'other','sku':'999','published_at_utc':'2026-10-04T12:00:00+00:00','valuation':1}],
                 'received_sku_records':2,'complete_publication_history':False}
        with patch('apps.msp_self_analytics.dated_rating_detail.collect_public_wb',return_value=payload):
            enrich_public_fallback(h,Reader())
        self.assertEqual([r['id'] for r in h['public_wb_detail']['period_records']],['x'])
        self.assertEqual(h['received_review_sample']['records_received_in_period'],0)
        self.assertIn('2026-10-04 | 5★',format_history_ru(h))
        self.assertFalse(h['complete_publication_history'])

    def test_budget_exhausted_does_not_request_full_or_network(self):
        class Reader:
            calls=24
            def call(self,*args):raise AssertionError('unexpected call')
        h=self.history([])
        with patch('apps.msp_self_analytics.dated_rating_detail.collect_public_wb') as public:
            enrich_public_fallback(h,Reader())
        public.assert_not_called()
        self.assertEqual(h['public_wb_detail']['status'],'CALL_BUDGET')

    def test_error_is_not_empty_success_or_secret_disclosure(self):
        class Reader:
            calls=3
            def call(self,*args): raise OSError('secret-url')
        h=self.history([]);enrich_public_fallback(h,Reader())
        self.assertEqual(h['public_wb_detail']['status'],'SOURCE_UNAVAILABLE')
        self.assertNotIn('secret-url',str(h))
