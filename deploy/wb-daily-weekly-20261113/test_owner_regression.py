import json,sys,unittest
from pathlib import Path
P=Path(__file__).parent/'payload';sys.path.insert(0,str(P))
import start_root as install
class OwnerRegression(unittest.TestCase):
 def test_real_existing_hermes_owned_canonical_files_are_supported(self):
  baseline=json.loads((P/'baseline.json').read_bytes())
  try:install.legacy_files(baseline)
  except ValueError as exc:self.fail('Installer rejects verified canonical sources owned by hermes: '+str(exc))
if __name__=='__main__':unittest.main()
