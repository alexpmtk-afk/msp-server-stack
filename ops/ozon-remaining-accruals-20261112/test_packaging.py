import unittest,tarfile,tempfile,subprocess,sys,json,hashlib
from pathlib import Path
B=Path(__file__).parent
class PackagingTests(unittest.TestCase):
 def test_deployed_archive_contains_executable_child_manifests(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as tmp:
   root=Path(tmp)
   with tarfile.open(B/'ozon-remaining-accruals.tar.gz') as t:
    for m in t.getmembers():
     self.assertTrue(m.isfile());p=root/m.name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(t.extractfile(m).read())
   for cabinet in ('ozon_novokshenov','ozon_laser_master'):
    d=root/cabinet
    self.assertTrue((d/'MANIFEST.json').is_file(),cabinet+' missing manifest in actual deployment artifact')
    expected=json.loads((d/'MANIFEST.json').read_bytes())
    self.assertTrue(all(hashlib.sha256((d/n).read_bytes()).hexdigest()==h for n,h in expected.items()))
    code='import sys;from unittest.mock import patch;sys.path.insert(0,sys.argv[1]);import root_common as r\nwith patch.object(r,"trust"):r.verify_payload()\n'
    r=subprocess.run([sys.executable,'-I','-c',code,str(d)],capture_output=True,text=True)
    self.assertEqual(r.returncode,0,r.stderr)
 def test_failed_child_has_safe_diagnostic_not_exception_text(self):
  sys.path.insert(0,str(B/'payload'))
  import root_common as r
  with self.assertRaises(RuntimeError) as caught:
   r.run([sys.executable,'-I','-c','raise ValueError("PRIVATE_SENTINEL")'])
  self.assertIn('ValueError',str(caught.exception))
  self.assertNotIn('PRIVATE_SENTINEL',str(caught.exception))
if __name__=='__main__':unittest.main(verbosity=2)
