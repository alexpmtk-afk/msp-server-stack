import unittest
from apps.operator_layer.admin import runner_plan
class RunnerTests(unittest.TestCase):
 def test_isolation_no_hermes_groups_or_root(self):
  p=runner_plan();self.assertEqual(p['user'],'msp-runner');self.assertNotIn('hermes',p['supplementary_groups']);self.assertIn('/home/hermes',p['inaccessible_paths']);self.assertFalse(p['root_access'])
 def test_gateway_not_in_migration_units(self):
  self.assertTrue(all('hermes-gateway' not in u for u in runner_plan()['restart_units']))
if __name__=='__main__':unittest.main()
