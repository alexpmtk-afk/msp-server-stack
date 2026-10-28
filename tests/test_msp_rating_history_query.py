"""Synthetic checks for gaps, bounded date queries and non-equivalent metrics."""
import unittest

from apps.msp_self_analytics.rating_history_query import query_history, summarize_history


class HistoryQueryTests(unittest.TestCase):
    def test_missing_endpoint_is_not_nearest_day_and_no_data_is_not_zero(self):
        result = summarize_history(marketplace='oz', sku='123', d1='2026-10-21', d2='2026-10-23',
            comments=[], period=[
                {'data': '2026-10-21', 'rating': 4, 'comments': 7, 'no_data': 0},
                {'data': '2026-10-22', 'rating': 0, 'comments': 0, 'no_data': 1}])
        self.assertIsNone(result['exact_end_snapshot'])
        self.assertIsNone(result['rating_change'])
        self.assertEqual(result['last_available_snapshot']['date'], '2026-10-21')
        self.assertEqual(result['observed_days'], 1)
        self.assertIsNone(result['total_ratings'])

    def test_sample_mean_does_not_replace_card_rating(self):
        result = summarize_history(marketplace='wb', sku='123', d1='2026-10-22', d2='2026-10-22',
            comments={'comments': [
                {'date': '2026-10-22', 'valuation': 5, 'text': 'fixture'},
                {'date': '2026-10-22', 'valuation': 1, 'text': ''}]},
            period=[{'data': '2026-10-22', 'rating': 4.8, 'comments': 100}])
        self.assertEqual(result['received_review_sample']['mean_received_rating'], 3)
        self.assertEqual(result['mean_observed_daily_rating'], 4.8)
        self.assertEqual(result['received_review_sample']['positive_text_records'], 1)
        self.assertFalse(result['received_review_sample']['identities_verified'])
        self.assertIsNone(result['new_positive_ratings'])

    def test_wb_fractional_field_preserved_separately_from_rounded_rating(self):
        result = summarize_history(marketplace='wb', sku='123', d1='2026-10-22', d2='2026-10-22',
            comments={'comments': []},
            period=[{'data': '2026-10-22', 'rating': 5, 'commentsvaluation': 4.9, 'comments': 100}])
        self.assertEqual(result['exact_end_snapshot']['rating'], 5)
        self.assertEqual(result['exact_end_snapshot']['provider_commentsvaluation'], 4.9)
        self.assertIn('MAY_BE_ROUNDED', result['rating_metric'])

    def test_conflicting_review_id_suppresses_sample(self):
        comments = [{'id': 'x', 'date': '2026-10-22', 'valuation': s, 'text': ''} for s in (1, 5)]
        result = summarize_history(marketplace='oz', sku='123', d1='2026-10-22', d2='2026-10-22',
                                   comments=comments, period=[])
        self.assertIsNone(result['received_review_sample'])

    def test_long_window_chunks_reuse_boundary_without_duplicate_days(self):
        class Reader:
            calls = 1
            names = []
            def call(self, name, args):
                self.calls += 1
                self.names.append(name)
                if args['report'] == 'comments':
                    return [], 'PASS_JSON'
                return [{'data': args['d1'], 'no_data': 0, 'rating': 4, 'comments': 1},
                        {'data': args['d2'], 'no_data': 0, 'rating': 4, 'comments': 1}], 'PASS_JSON'
        reader = Reader()
        result = query_history(reader, marketplace='oz', sku='123', d1='2026-01-01',
                               d2='2026-04-10', as_of='2026-10-28')
        self.assertEqual(result['mpstats_calls'], 4)
        self.assertEqual(len(result['windows']), 2)
        self.assertEqual(result['duplicate_dates'], [])
        self.assertEqual(set(reader.names), {'ozon_sku'})

    def test_invalid_or_overbudget_query_does_not_call_provider(self):
        class Reader:
            calls = 24
            def call(self, *args):
                raise AssertionError('unexpected network')
        base = dict(marketplace='wb', sku='123', d1='2026-10-01', d2='2026-10-27', as_of='2026-10-28')
        for changes in ({}, {'d2': '2026-10-28'}, {'sku': ' 123'}, {'marketplace': 'other'}, {'d1': '20261001'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                query_history(Reader(), **{**base, **changes})

    def test_provider_failure_is_unknown_not_zero(self):
        class Reader:
            calls = 1
            def call(self, name, args):
                self.calls += 1
                return None, 'HTTP_ERROR'
        result = query_history(Reader(), marketplace='wb', sku='123', d1='2026-10-01',
                               d2='2026-10-02', as_of='2026-10-28')
        self.assertIsNone(result['received_review_sample'])
        self.assertIsNone(result['exact_end_snapshot'])
        self.assertEqual(result['source_receipts'][0]['state'], 'HTTP_ERROR')


if __name__ == '__main__':
    unittest.main()
