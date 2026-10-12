import tempfile,unittest
from pathlib import Path
from apps.operator_layer.tasks import Journal,Budget
from apps.operator_layer.hermes_executor import HermesExecutor,parse_outcome
class ExecutorTests(unittest.TestCase):
 def test_response_parser_cannot_set_runtime_or_scope(self):
  with self.assertRaises(ValueError):parse_outcome('{"kind":"complete","evidence":{},"root_command":"id"}')
  self.assertEqual(parse_outcome('{"kind":"checkpoint","updates":{"tests_status":"PASS"}}')['kind'],'checkpoint')
 def test_parser_and_receipt_normalizer_agree_on_top_level_verified(self):
  from apps.operator_layer.receipt_schema import normalize_receipt
  raw=parse_outcome('{"schema_version":1,"kind":"complete","verified":true,"evidence":{"answer":"Result"}}')
  canonical=normalize_receipt(raw)
  self.assertEqual(canonical['evidence'],{'verified':True,'answer':'Result'})
  self.assertNotIn('verified',canonical)
  with self.assertRaisesRegex(ValueError,'invalid_verifier_field'):
   normalize_receipt(parse_outcome('{"schema_version":1,"kind":"complete","verified":"true","evidence":{}}'))
 def test_readonly_completion_requires_nonempty_answer(self):
  ctx={'block':{'allowed_mutations':[],'acceptance':['verified']}}
  for ev in ({'verified':True},{'verified':True,'answer':''},{'verified':True,'answer':'   '},{'verified':True,'answer':None},{'verified':False,'answer':'Result'}):
   with self.subTest(evidence=ev):
    self.assertFalse(HermesExecutor.verify(None,ctx,{'kind':'complete','evidence':ev}))
  self.assertTrue(HermesExecutor.verify(None,ctx,{'kind':'complete','evidence':{'verified':True,'answer':'Result'}}))
 def test_readback_is_durable_across_new_executor(self):
  with tempfile.TemporaryDirectory() as tmp:
   j=Journal(Path(tmp)/'private');self.addCleanup(j.close)
   a=HermesExecutor(j.root,profile='default');a.record('request',{'kind':'complete','evidence':{'verified':True}})
   b=HermesExecutor(j.root,profile='default')
   self.assertEqual(b.readback('request',{})['evidence'],{'verified':True})
 def test_runtime_budget_and_untrusted_profile(self):
  with tempfile.TemporaryDirectory() as tmp:
   j=Journal(Path(tmp)/'private');self.addCleanup(j.close)
   with self.assertRaises(ValueError):HermesExecutor(j.root,profile='other')
   a=HermesExecutor(j.root,profile='default')
   with self.assertRaises(TimeoutError):a.execute({'task_id':'fixture'},None,'req',Budget(started=0))
