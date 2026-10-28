"""Synthetic source contracts: platform schemas never borrowed across marketplaces."""
import unittest
from apps.msp_self_analytics import wb_rating_source, ozon_rating_source

class AdapterTests(unittest.TestCase):
 def test_platform_specific_comments_and_ozon_placeholders(self):
  wb=wb_rating_source.normalize({'comments':[{'date':'2026-09-28','valuation':5,'text':'fixture'}],'last_request':1},[{'data':'2026-09-28','rating':5,'comments':1}])
  oz=ozon_rating_source.normalize([{'date':'2026-09-28','valuation':4,'text':'fixture'}],[{'data':'2026-09-28','rating':4.2,'comments':3,'no_data':1}])
  self.assertEqual(wb['tool'],'wb_sku');self.assertEqual(oz['tool'],'ozon_sku')
  self.assertEqual(oz['period'][0]['daynum'],0)
  self.assertNotIn('last_request',oz['comments'])
  self.assertIsNone(ozon_rating_source.normalize({'comments':[]},[])['comments'])
  self.assertIsNone(wb_rating_source.normalize([],[])['comments'])

class CollectionTests(unittest.TestCase):
 def test_ozon_uses_only_ozon_tool_and_common_engine(self):
  from apps.msp_self_analytics.marketplace_rating_sources import collect_rating_evidence
  class Reader:
   def __init__(self):self.calls=1;self.tools=[]
   def call(self,name,args):
    self.calls+=1;self.tools.append(name)
    if args['report']=='comments':return [{'date':'2026-09-26','valuation':5,'text':'fixture'}],'PASS_JSON'
    return [{'data':d,'no_data':0,'rating':v,'comments':1} for d,v in [('2026-09-22',4),('2026-09-23',4),('2026-09-24',4),('2026-09-25',4),('2026-09-26',5),('2026-09-27',5)]],'PASS_JSON'
  reader=Reader();cp={'checkpoint_number':1,'review_date':'2026-09-25','windows':{'before':{'d1':'2026-09-23','d2':'2026-09-24'},'after':{'d1':'2026-09-26','d2':'2026-09-27'}}}
  r=collect_rating_evidence(reader,marketplace='oz',sku='123',checkpoints=[cp])
  self.assertEqual(set(reader.tools),{'ozon_sku'})
  e=r['evidence'][1];self.assertEqual(e['rating_change'],1)
  self.assertEqual(e['strict_rating_comparison']['status'],'PARTIAL_OR_UNKNOWN')
  self.assertEqual(e['after']['positive_text_record_count'],1)
 def test_no_budget_no_network_and_unknown_not_zero(self):
  from apps.msp_self_analytics.marketplace_rating_sources import collect_rating_evidence
  class Reader:
   calls=24
   def call(self,*a):raise AssertionError('budget exceeded')
  cp={'checkpoint_number':1,'review_date':'2026-09-25','windows':{'before':{'d1':'2026-09-23','d2':'2026-09-24'},'after':{'d1':'2026-09-26','d2':'2026-09-27'}}}
  e=collect_rating_evidence(Reader(),marketplace='oz',sku='123',checkpoints=[cp])['evidence'][1]
  self.assertIsNone(e['after']['positive_text_record_count'])
  self.assertIsNone(e['rating_change'])
 def test_unknown_marketplace_never_falls_back_to_wb(self):
  from apps.msp_self_analytics.marketplace_rating_sources import source_adapter
  with self.assertRaisesRegex(ValueError,'UNSUPPORTED_RATING_MARKETPLACE'):source_adapter('other')

class CliTests(unittest.TestCase):
 def test_ozon_missing_review_date_never_substitutes_purchase(self):
  from scripts.remote import msp_self_sku_report_cli as cli
  from unittest.mock import patch
  rows=[{'marketplace':'oz','store':'fixture','marketplace_sku':'123','quantity':2,'purchase_date':'2026-09-20','review_date':None}]
  with patch('apps.msp_self_analytics.sku_request.load_existing_series',return_value=rows):
   r=cli._report_ozon_ratings('fixture','123','2026-09-28',lambda: self.fail('No event: no provider calls'))
  self.assertEqual(r['status'],'NO_REGISTERED_REVIEW_DATES')
  self.assertEqual(r['mpstats_calls'],0)
 def test_ozon_cli_uses_common_windows_without_wb_calls(self):
  from scripts.remote import msp_self_sku_report_cli as cli
  from unittest.mock import patch
  rows=[{'marketplace':'oz','store':'fixture','marketplace_sku':'123','quantity':2,'purchase_date':'2026-09-20','review_date':'2026-09-25'}]
  class Reader:
   def __init__(self):self.calls=1
   def call(self,name,args):
    assert name=='ozon_sku';self.calls+=1
    if args['report']=='comments':return [{'date':'2026-09-26','valuation':5,'text':'fixture'}],'PASS_JSON'
    return [{'data':d,'no_data':0,'rating':v,'comments':1} for d,v in [('2026-09-22',4),('2026-09-23',4),('2026-09-24',4),('2026-09-25',4),('2026-09-26',5),('2026-09-27',5)]],'PASS_JSON'
  with patch('apps.msp_self_analytics.sku_request.load_existing_series',return_value=rows):r=cli._report_ozon_ratings('fixture','123','2026-09-28',Reader)
  self.assertEqual(r['review_source_evidence'][1]['rating_change'],1)
  self.assertIn('ozon_sku',r['text']);self.assertNotIn('wb_sku',r['text'])
  self.assertFalse(r['causal_effect_proven'])

class HistoryTests(unittest.TestCase):
 def test_no_data_rating_zero_and_absent_cache_are_not_facts(self):
  from apps.msp_self_analytics.marketplace_rating_sources import inspect_marketplace_history
  r=inspect_marketplace_history(marketplace='oz',sku='123',d1='2026-09-23',d2='2026-09-24',comments=[],period=[{'data':'2026-09-23','rating':5,'comments':9,'no_data':1},{'data':'2026-09-24','rating':0,'comments':0,'no_data':0}])
  self.assertIsNone(r['window']['rating_end'])
  self.assertEqual(r['window']['observed_days'],1)
  self.assertFalse(r['window']['complete_publication_history'])
  self.assertEqual(r['mode'],'SOURCE_HISTORY_INSPECTION_NOT_REGISTERED_EVENT')
 def test_ozon_duplicate_ids_do_not_become_independent_reviews(self):
  from apps.msp_self_analytics.marketplace_rating_sources import inspect_marketplace_history
  record={'id':'same','date':'2026-09-23','valuation':5,'text':'fixture'}
  r=inspect_marketplace_history(marketplace='oz',sku='123',d1='2026-09-23',d2='2026-09-24',comments=[record,record],period=[])
  self.assertEqual(r['window']['positive_text_record_count'],1)
  self.assertFalse(r['independent_buyers_verified'])
 def test_ozon_format_names_ozon_not_wb(self):
  from apps.msp_self_analytics.review_source_adapter import review_source_evidence,format_review_source_evidence_ru
  e=review_source_evidence(marketplace='oz',sku='123',event_date='2026-09-25',before_start='2026-09-23',before_end='2026-09-24',after_start='2026-09-26',after_end='2026-09-27')
  text=format_review_source_evidence_ru(e)
  self.assertIn('ozon_sku',text);self.assertNotIn('wb_sku',text)
