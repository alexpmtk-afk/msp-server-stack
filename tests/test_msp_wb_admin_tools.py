"""New admin preparation tools only; never reruns provider tests or real Redis."""
import importlib.util
import json
import os
import stat
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'docs/marketplace-reports/admin-ready'/f'{name}.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
c=load('select_pilot_credential');r=load('redis_readonly_probe')

class AdminTools(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.src=self.root/'source';self.dst=self.root/'destination'
        self.src.mkdir(mode=0o700);self.dst.mkdir(mode=0o700)
        self.file=self.src/'cabinets.json'
        self.raw=json.dumps({'wb_laser_master':{'token':'SYNTHETIC-PILOT','extra':'drop'},
                             'wb_dmitrieva':{'token':'SYNTHETIC-OTHER'},
                             'ozon_laser_master':{'api_key':'SYNTHETIC-OZON','client_id':'123'}}).encode()
        self.file.write_bytes(self.raw);self.file.chmod(0o600)
    def test_copy_only_one_cabinet_one_field_source_unchanged_and_no_replace(self):
        c.copy_one(self.src,self.dst,expected_uid=os.geteuid())
        dst=self.dst/c.NAME
        self.assertEqual(json.loads(dst.read_bytes()),{'wb_laser_master':{'token':'SYNTHETIC-PILOT'}})
        self.assertEqual(stat.S_IMODE(dst.stat().st_mode),0o600);self.assertEqual(self.file.read_bytes(),self.raw)
        before=dst.read_bytes()
        with self.assertRaises(FileExistsError):c.copy_one(self.src,self.dst,expected_uid=os.geteuid())
        self.assertEqual(dst.read_bytes(),before)
    def test_bad_or_duplicate_source_has_no_destination_write(self):
        for raw in [b'{}',b'{"wb_laser_master":{"token":true}}',b'{"x":1,"x":2}',b'[]',b'not-json']:
            self.file.write_bytes(raw)
            with self.assertRaises(ValueError):c.copy_one(self.src,self.dst,expected_uid=os.geteuid())
            self.assertFalse((self.dst/c.NAME).exists())
    def test_source_and_destination_symlinks_refused_without_external_write(self):
        link=self.root/'linked';link.symlink_to(self.dst,target_is_directory=True)
        with self.assertRaises(OSError):c.copy_one(self.src,link,expected_uid=os.geteuid())
        self.assertFalse((self.dst/c.NAME).exists())
        original=self.root/'original';self.file.rename(original);self.file.symlink_to(original)
        with self.assertRaises(OSError):c.copy_one(self.src,self.dst,expected_uid=os.geteuid())
        self.assertFalse((self.dst/c.NAME).exists())
    def test_fsync_failure_preserves_private_uncertain_copy_no_rewrite(self):
        with patch.object(os,'fsync',side_effect=OSError('synthetic failure')):
            with self.assertRaises(OSError):c.copy_one(self.src,self.dst,expected_uid=os.geteuid())
        dst=self.dst/c.NAME;self.assertTrue(dst.exists());self.assertEqual(self.file.read_bytes(),self.raw)
        with self.assertRaises(FileExistsError):c.copy_one(self.src,self.dst,expected_uid=os.geteuid())
    def test_cli_nonroot_refuses_before_protected_source_open(self):
        with patch.object(os,'geteuid',return_value=1001),patch('sys.argv',['tool','--owner-approved-create-pilot-copy']),patch.object(c,'copy_one',side_effect=AssertionError('no read')),patch('builtins.print'):
            self.assertEqual(c.main(),2)
    def test_readonly_probe_command_allowlist_and_identity_redaction(self):
        clients=[]
        class Fake:
            def __init__(self,protocol):
                self.calls=[];self.connection_pool=types.SimpleNamespace(connection_kwargs={'protocol':3 if protocol is None else protocol})
            def ping(self):self.calls.append('PING');return True
            def time(self):self.calls.append('TIME');return (1000,0)
            def info(self,section):self.calls.append('INFO '+section);return {'redis_version':'7.2.4','redis_mode':'standalone','run_id':'PRIVATE-IDENTITY'}
            def exists(self,key):self.calls.append('EXISTS');return 0
            def pttl(self,key):self.calls.append('PTTL');return -2
            def close(self):self.calls.append('CLOSE')
        def factory(proto):
            client=Fake(proto);clients.append(client);return client
        result=r.probe(factory,['marketplace-rate:v1:wb:PRIVATE-KEY:catalog:placeholder'])
        raw=json.dumps(result);self.assertNotIn('PRIVATE',raw);self.assertEqual(result['read_only_protocol_check'],'PASS')
        self.assertEqual(result['shared_across_other_integrations'],'NOT_VERIFIED')
        for client in clients:self.assertEqual(client.calls,['PING','TIME','INFO server','EXISTS','PTTL','CLOSE'])
    def test_unknown_explicit_keys_refused_before_any_redis_command(self):
        fake=types.SimpleNamespace(ping=lambda:self.fail('must not contact Redis'))
        for keys in [['unapproved-key'],['marketplace-rate:v1:x']*4]:
            with self.assertRaises(ValueError):r.one(fake,keys)
    def test_different_backend_id_and_cluster_never_become_compatibility_pass(self):
        class Fake:
            connection_pool=types.SimpleNamespace(connection_kwargs={'protocol':2})
            def ping(self):return True
            def time(self):return (1000,0)
            def info(self,section):return {'redis_version':'7.2.4','redis_mode':'cluster','run_id':str(id(self))}
            def close(self):pass
        result=r.probe(lambda protocol:Fake())
        self.assertEqual(result['read_only_protocol_check'],'NOT_VERIFIED')
