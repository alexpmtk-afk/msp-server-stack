import unittest
from unittest.mock import patch
from apps.msp_self_analytics.wb_public_review_source import normalize_public_feedbacks, collect_public_wb


class PublicWbTests(unittest.TestCase):
    def test_family_totals_not_borrowed_for_sku_and_pii_not_returned(self):
        row = {'id': 'x', 'nmId': 123, 'createdDate': '2026-10-01T23:00:00Z',
               'productValuation': 5, 'text': '', 'pros': 'fixture', 'wbUserId': 'private',
               'excludedFromRating': {'isExcluded': True}}
        result = normalize_public_feedbacks({'feedbacks': [row, {**row, 'id': 'y', 'nmId': 456}],
            'feedbackCount': 900, 'feedbackCountWithText': 300,
            'nmValuationDistribution': [{'nm': 123, 'valuationDistribution': {'5': 20}}]},
            sku='123', imt_id=111, observed_at_utc='2026-10-28T00:00:00Z')
        self.assertEqual(result['received_sku_records'], 1)
        self.assertEqual(result['sku_star_distribution_now'], {'5': 20})
        self.assertTrue(result['records'][0]['has_text'])
        self.assertTrue(result['records'][0]['excluded_from_rating_now'])
        self.assertNotIn('wbUserId', result['records'][0])
        self.assertNotIn('text', result['records'][0])
        self.assertFalse(result['complete_publication_history'])

    def test_card_identity_and_resolver_host_validation(self):
        url = 'https://basket-01.wbbasket.ru/vol0/part0/123/info/ru/card.json'
        with patch('apps.msp_self_analytics.wb_public_review_source._get_json', return_value={'nm_id': 456, 'imt_id': 1}):
            with self.assertRaisesRegex(ValueError, 'IDENTITY_MISMATCH'):
                collect_public_wb(sku='123', card_url=url)
        with patch('apps.msp_self_analytics.wb_public_review_source._get_json', side_effect=[{'nm_id': 123, 'imt_id': 1}, ['https://evil.example']]):
            with self.assertRaisesRegex(ValueError, 'UNVERIFIED_WB_FEEDBACK_HOST'):
                collect_public_wb(sku='123', card_url=url)

    def test_conflicting_ids_excluded_from_sample(self):
        row = {'id': 'x', 'nmId': 123, 'createdDate': '2026-10-01T00:00:00Z', 'productValuation': 1}
        result = normalize_public_feedbacks({'feedbacks': [row, {**row, 'productValuation': 5}]},
            sku='123', imt_id=1, observed_at_utc='2026-10-28T00:00:00Z')
        self.assertEqual(result['conflicting_ids_count'], 1)
        self.assertEqual(result['records'], [])
