import unittest
from apps.operator_layer.release import version_report
class ReleaseTests(unittest.TestCase):
 def test_missing_install_is_not_workspace(self):
  r=version_report('a'*40,'b'*40,None,None)
  self.assertIsNone(r['installed_release_sha']);self.assertIsNone(r['running_release_sha']);self.assertNotEqual(r['workspace_sha'],r['canonical_github_sha'])
 def test_running_without_installed_rejected(self):
  with self.assertRaises(ValueError):version_report('a'*40,'a'*40,None,'a'*40)
if __name__=='__main__':unittest.main()
