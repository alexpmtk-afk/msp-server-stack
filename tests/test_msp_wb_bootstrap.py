"""Unprivileged offline tests. No root installer, secrets, systemd or Redis run."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[1]
def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts/wb_bootstrap'/f'{name}.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
b=load('package');i=load('install')


def archive(entries):
    out=io.BytesIO()
    with tarfile.open(fileobj=out,mode='w',format=tarfile.USTAR_FORMAT) as t:
        for name,data,typ in entries:
            info=tarfile.TarInfo(name);info.mode=0o644;info.type=typ
            info.size=len(data) if typ==tarfile.REGTYPE else 0
            if typ in (tarfile.SYMTYPE,tarfile.LNKTYPE):info.linkname='/outside'
            t.addfile(info,io.BytesIO(data) if info.isfile() else None)
    return out.getvalue()


class Bootstrap(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)
        self.data=b'synthetic code'
        self.manifest=json.dumps({'files':[{'path':'install.py','sha256':b.sha(self.data)}]}).encode()
        self.mh=b.sha(self.manifest)
    def good(self):
        return [('install.py',self.data,tarfile.REGTYPE),('BUNDLE_MANIFEST.json',self.manifest,tarfile.REGTYPE)]
    def test_archive_readback_exact_bytes(self):
        files,manifest=b.validate(archive(self.good()),self.mh)
        self.assertEqual(files,{'install.py':self.data});self.assertEqual(manifest,self.manifest)
    def test_traversal_absolute_symlink_hardlink_duplicate_refused(self):
        for name,typ in [('../escape',tarfile.REGTYPE),('/absolute',tarfile.REGTYPE),('link',tarfile.SYMTYPE),('hard',tarfile.LNKTYPE),('install.py',tarfile.REGTYPE)]:
            with self.assertRaises(ValueError):b.validate(archive(self.good()+[(name,b'x',typ)]),self.mh)
    def test_wrong_manifest_and_changed_payload_refused(self):
        with self.assertRaises(ValueError):b.validate(archive(self.good()),'0'*64)
        items=self.good();items[0]=('install.py',b'changed',tarfile.REGTYPE)
        with self.assertRaises(ValueError):b.validate(archive(items),self.mh)
    def test_unlisted_payload_refused(self):
        with self.assertRaises(ValueError):b.validate(archive(self.good()+[('extra',b'x',tarfile.REGTYPE)]),self.mh)
    def test_nonroot_refuses_before_payload_secret_or_system_calls(self):
        with patch.object(os,'geteuid',return_value=1001),patch.object(i,'verify_payload',side_effect=AssertionError('not allowed')),patch.object(i,'run',side_effect=AssertionError('not allowed')),patch('builtins.print'):
            self.assertEqual(i.main(),2)
    def test_write_new_no_overwrite(self):
        p=self.path/'new';i.write_new(p,b'original')
        with self.assertRaises(FileExistsError):i.write_new(p,b'replacement')
        self.assertEqual(p.read_bytes(),b'original')
    def test_uncertain_fsync_keeps_evidence(self):
        p=self.path/'new'
        with patch.object(os,'fsync',side_effect=OSError('synthetic')):
            with self.assertRaises(OSError):i.write_new(p,b'evidence')
        self.assertTrue(p.exists())
        with self.assertRaises(FileExistsError):i.write_new(p,b'replacement')
    def test_wheel_paths_and_symlinks_refused(self):
        for name,mode in [('../outside',0),('other/module.py',0),('redis/link',0o120777)]:
            p=self.path/'test.whl'
            with zipfile.ZipFile(p,'w') as z:
                info=zipfile.ZipInfo(name);info.external_attr=mode<<16;z.writestr(info,b'synthetic')
            with self.assertRaises(ValueError):i.wheel_files(p)
    def test_valid_pure_python_wheel_extraction_data(self):
        p=self.path/'good.whl'
        with zipfile.ZipFile(p,'w') as z:z.writestr('redis/__init__.py',b'VERSION=1')
        self.assertEqual(i.wheel_files(p),{'redis/__init__.py':b'VERSION=1'})
    def test_launcher_mismatch_stops_before_any_staging(self):
        p=self.path/'bad.tar';p.write_bytes(b'not a bundle')
        # Pretend root only inside the child; mismatched hash stops before /var writes.
        code='import os;os.geteuid=lambda:0;'+b.LAUNCHER
        result=subprocess.run([sys.executable,'-I','-B','-c',code,str(p),'0'*64,'0'*64],capture_output=True)
        self.assertNotEqual(result.returncode,0);self.assertIn(b'BUNDLE_HASH',result.stderr)
    def test_no_api_activation_in_installer_or_unit(self):
        source=(ROOT/'scripts/wb_bootstrap/install.py').read_text()
        self.assertNotIn("'enable'",source);self.assertNotIn("'restart'",source)
        self.assertNotIn('MSP_REPORTS_SHARED_QUEUE_VERIFIED=YES',source)
        self.assertIn("'--unit=msp-wb-bootstrap-smoke'",source)
    def test_rel_rejects_escaping_and_empty_paths(self):
        for path in ['../x','/x','a//b','a/./b','a\\b','']:
            with self.assertRaises(ValueError):i.rel(path)
    def test_venv_wheel_import_real_unconnected_network_denied(self):
        # Actual isolated runtime; NOT an installation or backend connection.
        import venv
        wheel=Path('/home/hermes/.hermes/cache/scratch/redis-8.1.0-py3-none-any.whl')
        if not wheel.exists():self.skipTest('offline pinned wheel absent in this checkout')
        self.assertEqual(b.sha(wheel.read_bytes()),b.WHEEL_SHA)
        env=self.path/'venv';venv.EnvBuilder(with_pip=False,symlinks=True).create(env)
        site=next((env/'lib').glob('python*/site-packages'))
        for name,data in i.wheel_files(wheel).items():
            p=site/name;p.parent.mkdir(parents=True,exist_ok=True);i.write_new(p,data,0o644)
        code='import sys; sys.addaudithook(lambda event,args: (_ for _ in ()).throw(AssertionError("NETWORK_DENIED")) if event in ("socket.connect","socket.bind","socket.getaddrinfo") else None); import redis; assert redis.__version__=="8.1.0"; print("UNCONNECTED_IMPORT_PASS")'
        result=subprocess.run([str(env/'bin/python'),'-I','-B','-c',code],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('UNCONNECTED_IMPORT_PASS',result.stdout)
