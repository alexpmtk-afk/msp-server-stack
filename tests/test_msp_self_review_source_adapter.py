import unittest
from apps.msp_self_analytics.review_source_adapter import review_source_evidence,format_review_source_evidence_ru
ARGS=dict(sku='123',event_date='2026-09-25',after_start='2026-09-26',after_end='2026-10-25')
class Tests(unittest.TestCase):
 def test_one_observed_text_does_not_mean_complete_positive_history(self):
  v=review_source_evidence(**ARGS,comments={'comments':[{'date':'2026-09-28','valuation':5,'text':'sample'}]})
  self.assertEqual(v['observed_positive_text_entries'],1);self.assertIsNone(v['new_positive_text_reviews']);self.assertIsNone(v['new_positive_ratings']);self.assertFalse(v['independent_reviewers_verified'])
 def test_unknown_not_zero(self):
  v=review_source_evidence(**ARGS);self.assertIsNone(v['observed_positive_text_entries']);self.assertIn('UNKNOWN',format_review_source_evidence_ru(v))
 def test_zero_rating_not_a_five_point_gain(self):
  v=review_source_evidence(**ARGS,period=[{'data':'2026-09-25','comments':0,'rating':0},{'data':'2026-10-25','comments':1,'rating':5}])
  self.assertIsNone(v['rating_change']);self.assertEqual(v['provider_comments_counter']['observed_difference'],1);self.assertIsNone(v['new_positive_text_reviews'])
 def test_duplicate_dates_invalidate_counter_difference(self):
  p=[{'data':'2026-09-25','comments':0,'rating':0},{'data':'2026-10-25','comments':1,'rating':5},{'data':'2026-10-25','comments':2,'rating':5}]
  v=review_source_evidence(**ARGS,period=p);self.assertNotIn('provider_comments_counter',v)
 def test_event_day_excluded(self):
  v=review_source_evidence(**ARGS,comments={'comments':[{'date':'2026-09-25','valuation':5,'text':'sample'}]});self.assertEqual(v['observed_positive_text_entries'],0);self.assertIsNone(v['new_positive_text_reviews'])
 def test_placeholders_are_not_observations(self):
  v=review_source_evidence(**ARGS,period=[{'data':'2026-09-25','daynum':0,'comments':0,'rating':0},{'data':'2026-10-25','comments':1,'rating':5}]);self.assertNotIn('provider_comments_counter',v)
