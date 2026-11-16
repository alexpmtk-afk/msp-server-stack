import importlib.util,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
B=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('finish',B/'finish_verified.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
class FinishTests(unittest.TestCase):
 def test_nonroot_refuses_before_target_reads(self):
  with patch.object(f,'verify',side_effect=AssertionError('NO READ')),self.assertRaises(PermissionError):f.main()
 def test_actual_read_only_verification_does_not_write(self):
  before=Path('/var/lib/msp-wb-daily-weekly/installation.json').read_bytes()
  with patch.object(f,'atomic',side_effect=AssertionError('NO WRITE')):self.assertEqual(f.main(check=True)['status'],'READY_TO_FINALIZE')
  self.assertEqual(Path('/var/lib/msp-wb-daily-weekly/installation.json').read_bytes(),before)
 def test_actual_manifest_drift_is_rejected(self):
  with patch.dict(f.EXPECTED,manifest_sha256='0'*64),self.assertRaises(ValueError):f.main(check=True)
 def test_metadata_only_transaction_and_idempotence(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
   root=Path(t);(root/'backups').mkdir();old=json.dumps(dict(status='INSTALLING',root_release=f.EXPECTED['release'])).encode();(root/'installation.json').write_bytes(old);(root/'schedule.json').write_text('{"not_before_epoch":1794635100}')
   realpath=Path
   def mapped(value):
    path=realpath(value)
    if str(path).startswith('/var/lib/msp-wb-daily-weekly/'):return root/path.name
    return path
   state=dict(ActiveState='active',UnitFileState='enabled')
   with patch.object(f,'Path',side_effect=mapped),patch.object(f.os,'geteuid',return_value=0),patch.object(f,'trust'),patch.object(f,'verify',return_value=(state,state,state)),patch.dict(f.EXPECTED,installation_sha256=f.sha(old)):
    result=f.main();self.assertEqual(result['status'],'INSTALLED');self.assertFalse(result['service_restarted']);self.assertEqual((root/'backups/installation-before-finalize.json').read_bytes(),old)
    with patch.object(f,'atomic',side_effect=AssertionError('NO SECOND WRITE')):self.assertEqual(f.main()['status'],'ALREADY_FINALIZED')
 def test_sender_lifecycle_commands_absent(self):
  import ast
  tree=ast.parse((B/'finish_verified.py').read_text())
  for node in ast.walk(tree):
   if isinstance(node,ast.Constant) and isinstance(node.value,str):self.assertNotIn(node.value,('start','stop','restart','enable','daemon-reload','sendMessage'))
if __name__=='__main__':unittest.main()
