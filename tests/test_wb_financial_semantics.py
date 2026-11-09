import importlib.util,json,unittest
from pathlib import Path
from decimal import Decimal
P=Path(__file__).resolve().parents[1]/'docs/data-sources/wb-financial-reports/guide.py'
s=importlib.util.spec_from_file_location('wb_semantics',P);g=importlib.util.module_from_spec(s);s.loader.exec_module(g)
class Semantics(unittest.TestCase):
 def setUp(self):self.k=g.load()
 def test_dictionary_links_and_unique_identities(self):self.assertEqual(g.validate(self.k)['status'],'PASS')
 def test_payout_does_not_turn_into_profit(self):
  out=g.route(self.k,'какая чистая прибыль по WB')
  self.assertEqual([x['id'] for x in out['intents']],['profit']);self.assertFalse(out['intents'][0]['formulas'])
 def test_storage_expense_not_lost_when_sku_is_absent(self):
  out=g.route(self.k,'сколько списали за хранение');self.assertIn('storage_fee',[f for i in out['intents'] for f in i['fields']]);self.assertEqual(g.field(self.k,'Хранение')[0]['id'],'storage_fee')
 def test_old_payment_label_routes_to_same_money_not_percentage(self):
  self.assertEqual(g.field(self.k,'Эквайринг/комиссии за организацию платежей')[0]['id'],'payment_fee')
 def test_unsigned_returns_are_subtracted_once(self):
  r=g.calculate(self.k,'net_goods_payout',{'sales':'1000','returns':'100'},'RUB');self.assertEqual(r['value'],'900')
  with self.assertRaises(ValueError):g.calculate(self.k,'net_goods_payout',{'sales':'1000','returns':'-100'},'RUB')
 def test_negative_deduction_is_payment_not_second_expense(self):
  v={'goods_net':'900','delivery':'100','storage':'20','processing':'10','penalties':'5','loyalty_fee_net':'4','loyalty_points_net':'6','deductions_signed':'-7','loyalty_compensation':'8'}
  self.assertEqual(g.calculate(self.k,'settlement_core',v,'RUB')['value'],'770')
 def test_decimal_precision(self):self.assertEqual(g.calculate(self.k,'net_sales',{'sales':'0.1','returns':'0.03'},'RUB')['value'],'0.07')
 def test_missing_unknown_or_nonfinite_components_never_become_zero(self):
  for v in [{'sales':'1'}, {'sales':'1','returns':'0','unknown':'3'}, {'sales':'NaN','returns':'0'}, {'sales':True,'returns':'0'}, {'sales':1.1,'returns':'0'}]:
   with self.subTest(v=v),self.assertRaises(ValueError):g.calculate(self.k,'net_sales',v,'RUB')
 def test_duplicate_json_inputs_are_not_silently_overwritten(self):
  with self.assertRaises(ValueError):json.loads('{"sales":1,"sales":2}',object_pairs_hook=g.strict_pairs)
 def test_unverified_api_bindings_never_invent_key_names(self):
  for f in self.k['fields']:
   if f['api_binding']=='NOT_VERIFIED':self.assertEqual(f['api_keys'],[])
 def test_daily_is_not_falsely_declared_installed(self):self.assertIsNone(self.k['datasets']['daily']['name'])
 def test_unknown_query_does_not_manufacture_financial_answers(self):self.assertFalse(g.route(self.k,'температура воздуха')['matched'])
