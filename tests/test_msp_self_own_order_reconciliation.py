import unittest,json,types
from apps.msp_self_analytics.own_order_reconciliation import fetch_own_wb_orders
class Tests(unittest.TestCase):
 def test_own_feed_zero_not_proven_zero_orders(self):
  fake=lambda *a,**k:types.SimpleNamespace(returncode=0,stdout=json.dumps({'success':True,'data':{'count':0,'results':[],'next':None}}))
  v=fetch_own_wb_orders(sku='123',store='novok',d1='2026-09-26',d2='2026-10-25',run=fake)
  self.assertEqual(v['observed_units'],0);self.assertFalse(v['source_load_coverage_verified']);self.assertIsNone(v['independent_external_orders'])
 def test_scope_mismatch(self):
  fake=lambda *a,**k:types.SimpleNamespace(returncode=0,stdout=json.dumps({'success':True,'data':{'count':1,'results':[{'nmId':999,'blockid':3,'orderCreatedAt':'2026-10-01'}],'next':None}}))
  v=fetch_own_wb_orders(sku='123',store='novok',d1='2026-09-26',d2='2026-10-25',run=fake);self.assertEqual(v['status'],'SOURCE_SCOPE_MISMATCH')
 def test_wrong_page_count_not_complete(self):
  fake=lambda *a,**k:types.SimpleNamespace(returncode=0,stdout=json.dumps({'success':True,'data':{'count':1,'results':[],'next':None}}))
  self.assertEqual(fetch_own_wb_orders(sku='123',store='novok',d1='2026-09-26',d2='2026-10-25',run=fake)['status'],'PAGINATION_OR_IDENTITY_NOT_VERIFIED')
