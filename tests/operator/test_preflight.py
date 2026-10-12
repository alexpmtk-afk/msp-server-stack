import unittest
from datetime import datetime, timezone
from apps.operator_layer.preflight import result, evaluate, load_registry

class PreflightTests(unittest.TestCase):
    def test_visible_is_not_pass(self):
        r=result('github.write',{'provider':'github','target':'repo','ttl':60}, {'tool_visible':True,'authenticated':False,'authorized':False,'acceptance_verified':False},'missing_credentials','rev')
        self.assertEqual(r['state'],'FAIL');self.assertIn('CAPABILITY GAP',r['gap']);self.assertEqual(r['policy_revision'],'rev')
        self.assertGreater(datetime.fromisoformat(r['expires_at']),datetime.fromisoformat(r['checked_at']))
    def test_disabled_has_no_gap(self):
        r=result('google.write',{'provider':'google','target':'sheet','ttl':60,'enabled':False},{},'disabled_by_policy','rev')
        self.assertEqual(r['state'],'DISABLED');self.assertIsNone(r['gap'])
    def test_unauthenticated_unknown_is_not_pass(self):
        r=result('github.write',{'provider':'github','target':'repo','ttl':60},{'tool_visible':None},'unreachable','rev')
        self.assertEqual(r['state'],'UNKNOWN')
    def test_registry_contains_all_required_capabilities(self):
        r=load_registry();self.assertEqual(len(r['capabilities']),17);self.assertIn('hermes.durable_tasks',r['capabilities']);self.assertIn('hermes.multipart_collection',r['capabilities'])
        self.assertFalse(r['capabilities']['google.write']['enabled'])
    def test_missing_broker_is_explicit_gap(self):
        r=evaluate(['github.write'])['results'][0]
        self.assertEqual(r['state'],'FAIL');self.assertEqual(r['reason_code'],'broker_not_installed')
    def test_unknown_required_capability_rejected(self):
        with self.assertRaises(ValueError): evaluate(['sudo.all'], live=False)
if __name__=='__main__':unittest.main()
