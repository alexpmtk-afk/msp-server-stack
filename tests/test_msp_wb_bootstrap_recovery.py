"""Permission regression and recovery boundaries; no privileged production calls."""
import importlib.util
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts/wb_bootstrap'/f'{name}.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

class ModeRegression(unittest.TestCase):
    def test_program_mode_644_under_umask_077(self):
        m=module('install')
        with tempfile.TemporaryDirectory() as d:
            old=os.umask(0o077)
            try:m.write_new(Path(d)/'program.py',b'program',0o644)
            finally:os.umask(old)
            self.assertEqual(stat.S_IMODE((Path(d)/'program.py').stat().st_mode),0o644)
    def test_private_default_stays_600_under_umask_077(self):
        m=module('install')
        with tempfile.TemporaryDirectory() as d:
            old=os.umask(0o077)
            try:m.write_new(Path(d)/'receipt',b'private')
            finally:os.umask(old)
            self.assertEqual(stat.S_IMODE((Path(d)/'receipt').stat().st_mode),0o600)

class RecoveryBoundaries(unittest.TestCase):
    def setUp(self):
        self.m=module('recover')
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.uid=os.geteuid()
    def file(self,name,data=b'program',mode=0o600):
        p=self.root/name;p.write_bytes(data);p.chmod(mode);return p
    def test_modes_fixed_and_second_call_is_noop(self):
        p=self.file('program.py');token=self.file('synthetic-token');journal=self.file('journal.json')
        before=[x.stat().st_mode for x in [token,journal]]
        entries=[(p,self.m.sha(p.read_bytes()),True),(journal,self.m.sha(journal.read_bytes()),False)]
        owner=(p.stat().st_uid,p.stat().st_gid)
        self.assertEqual(self.m.verify_and_repair(entries,expected_uid=self.uid),1)
        self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o644)
        self.assertEqual((p.stat().st_uid,p.stat().st_gid),owner)
        self.assertEqual([x.stat().st_mode for x in [token,journal]],before)
        self.assertEqual(self.m.verify_and_repair(entries,expected_uid=self.uid),0)
    def test_later_bad_checksum_means_no_earlier_chmod(self):
        first=self.file('first.py');bad=self.file('last.py',b'drift')
        entries=[(first,self.m.sha(first.read_bytes()),True),(bad,'0'*64,True)]
        with self.assertRaises(ValueError):self.m.verify_and_repair(entries,expected_uid=self.uid)
        self.assertEqual(stat.S_IMODE(first.stat().st_mode),0o600)
    def test_link_or_unsafe_mode_refuses_before_any_chmod(self):
        first=self.file('first.py');target=self.file('target');symlink=self.root/'link';symlink.symlink_to(target)
        hard=self.root/'hard';os.link(target,hard)
        unsafe=self.file('writable',mode=0o666)
        for bad in [symlink,hard,unsafe]:
            with self.assertRaises((ValueError,OSError)):
                self.m.verify_and_repair([(first,self.m.sha(first.read_bytes()),True),(bad,self.m.sha(b'program'),True)],expected_uid=self.uid)
            self.assertEqual(stat.S_IMODE(first.stat().st_mode),0o600)
    def test_nonroot_refusal_before_original_snapshot_or_secrets(self):
        with patch.object(os,'geteuid',return_value=1001),patch.object(Path,'lstat',side_effect=AssertionError('no reads')),patch('builtins.print'):
            self.assertEqual(self.m.main(),2)
    def test_recovery_has_no_identity_or_secret_copy_path(self):
        source=(ROOT/'scripts/wb_bootstrap/recover.py').read_text()
        for forbidden in ['useradd','groupadd','copy_one(',"SOURCE.read_bytes",'chmod -R','MSP_REPORTS_SHARED_QUEUE_VERIFIED=YES']:
            self.assertNotIn(forbidden,source)
        self.assertIn("'--unit=msp-wb-recovery-smoke'",source)
    def test_fchmod_failure_is_uncertain_not_file_rewrite(self):
        p=self.file('program.py');data=p.read_bytes()
        with patch.object(os,'fchmod',side_effect=OSError('synthetic mode failure')):
            with self.assertRaises(OSError):self.m.verify_and_repair([(p,self.m.sha(data),True)],expected_uid=self.uid)
        self.assertEqual(p.read_bytes(),data)
    def test_wrong_owner_refused_before_mode_change(self):
        p=self.file('program.py')
        with self.assertRaises(ValueError):
            self.m.verify_and_repair([(p,self.m.sha(p.read_bytes()),True)],expected_uid=self.uid+1)
        self.assertEqual(stat.S_IMODE(p.stat().st_mode),0o600)
    def test_published_recovery_matches_manifest_and_refuses_nonroot(self):
        import json
        d=ROOT/'docs/marketplace-reports/recovery-20261103'
        manifest=json.loads((d/'REPAIR_MANIFEST.json').read_text())
        self.assertEqual(self.m.sha((d/'repair.py').read_bytes()),manifest['repair_sha256'])
        spec=importlib.util.spec_from_file_location('published_repair',d/'repair.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        self.assertEqual(len(m.GENERATED),5)
        self.assertEqual(m.OLD_INSTALL_SHA,manifest['original_install_sha256'])
        with patch.object(os,'geteuid',return_value=1001),patch('builtins.print'):
            self.assertEqual(m.main(),2)
