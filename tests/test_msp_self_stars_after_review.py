"""Owner contract: dates and stars, not review text or purchase_date."""
import unittest
from apps.msp_self_analytics.rating_history_query import summarize_history, review_date_summary


class StarsAfterReviewTests(unittest.TestCase):
    def history(self, rows):
        return summarize_history(marketplace='oz', sku='123', d1='2026-10-20', d2='2026-10-27',
            comments=rows, period=[{'data': '2026-10-22', 'rating': 4.1, 'comments': 12, 'no_data': 0},
                                  {'data': '2026-10-27', 'rating': 4.3, 'comments': 16, 'no_data': 0}])

    def test_scores_without_text_count_and_own_day_is_separate(self):
        rows = [{'date': d, 'valuation': s} for d, s in [
            ('2026-10-21', 5), ('2026-10-22', 1), ('2026-10-23', 5),
            ('2026-10-24', 5), ('2026-10-25', 4), ('2026-10-27', 2)]]
        result = review_date_summary(self.history(rows), review_date='2026-10-23')
        self.assertEqual(result['before_received_ratings']['mean_received_rating'], 3)
        after = result['after_received_ratings']
        self.assertEqual(after['stars'], {'1': 0, '2': 1, '3': 0, '4': 1, '5': 1})
        self.assertAlmostEqual(after['mean_received_rating'], 11/3)
        self.assertEqual(result['own_date_records_not_attributed']['received_count'], 1)
        self.assertEqual(result['before_card_snapshot']['rating'], 4.1)
        self.assertEqual(result['latest_available_card_snapshot']['rating'], 4.3)
        self.assertFalse(result['card_rating_excludes_own_review'])

    def test_multiple_same_day_reviews_are_not_guessed_as_own(self):
        rows = [{'id': str(s), 'date': '2026-10-23', 'valuation': s} for s in (4, 5)]
        result = review_date_summary(self.history(rows), review_date='2026-10-23', own_review_ids=['5'])
        self.assertEqual(result['identified_own_reviews_excluded']['received_count'], 1)
        self.assertEqual(result['own_date_records_not_attributed']['received_count'], 1)
        self.assertEqual(result['after_received_ratings']['received_count'], 0)

    def test_later_own_review_date_is_not_counted_as_other_buyers(self):
        result = review_date_summary(self.history([{'date': '2026-10-25', 'valuation': 5}]),
            review_date='2026-10-23', own_review_dates=['2026-10-25'])
        self.assertEqual(result['after_received_ratings']['received_count'], 0)
        self.assertEqual(result['own_date_records_not_attributed']['received_count'], 1)

    def test_verified_own_id_excluded_even_when_source_date_differs(self):
        result = review_date_summary(self.history([{'id': 'own', 'date': '2026-10-24', 'valuation': 5}]),
            review_date='2026-10-23', own_review_ids=['own'])
        self.assertEqual(result['after_received_ratings']['received_count'], 0)
        self.assertEqual(result['identified_own_reviews_excluded']['received_count'], 1)

    def test_missing_source_not_reported_as_zero(self):
        result = review_date_summary(self.history(None), review_date='2026-10-23')
        self.assertIsNone(result['after_received_ratings'])

    def test_event_outside_window_rejected(self):
        with self.assertRaises(ValueError):
            review_date_summary(self.history([]), review_date='2026-10-19')
