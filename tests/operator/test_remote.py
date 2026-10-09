import io,tarfile,tempfile,unittest
from pathlib import Path
from apps.operator_layer.remote import RemoteBroker,extract_release,release_status
class RemoteTests(unittest.TestCase):
    def test_unknown_component_and_argv_denied(self):
        b=RemoteBroker({},None,None)
        for params in [{'component':'hermes-gateway'},{'component':'msp-data-catalog','shell':'id'}]:
            with self.assertRaises(ValueError):b.execute('registered_service_status',params)
    def test_archive_traversal_and_symlinks_denied(self):
        for name,kind in [('root/../outside',tarfile.REGTYPE),('root/apps/msp_data_sync/x',tarfile.SYMTYPE)]:
            buf=io.BytesIO()
            with tarfile.open(fileobj=buf,mode='w:gz') as t:
                i=tarfile.TarInfo(name);i.type=kind;t.addfile(i)
            with tempfile.TemporaryDirectory() as d:
                with self.assertRaises(ValueError):extract_release(buf.getvalue(),Path(d)/'release','a'*40)
    def test_immutable_export_and_sha_metadata(self):
        b=io.BytesIO()
        with tarfile.open(fileobj=b,mode='w:gz') as t:
            for name,data in [('root/apps/msp_data_sync/sync.py',b'x'),('root/apps/msp_data_sync/schema.sql',b'x'),('root/config/msp-data/sync.json',b'{}')]:
                i=tarfile.TarInfo(name);i.size=len(data);t.addfile(i,io.BytesIO(data))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'release';extract_release(b.getvalue(),p,'a'*40)
            self.assertEqual(release_status(p)['sha'],'a'*40)
            self.assertFalse((p/'apps/msp_data_sync/sync.py').stat().st_mode & 0o222)
    def test_no_shell_operation(self):
        with self.assertRaises(ValueError):RemoteBroker({},None,None).execute('shell',{'command':'id'})
if __name__=='__main__':unittest.main()
