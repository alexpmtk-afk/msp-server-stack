"""No Redis/API/systemd calls: stage C redaction and approval boundaries."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('c',ROOT/'scripts/wb_redis_c/check.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)

class StageC(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.dir=Path(self.tmp.name);self.file=self.dir/'redis.env'
    def env(self,data):self.file.write_text(data);self.file.chmod(0o600);return self.file
    def test_env_names_only_never_secret_values(self):
        p=self.env('MARKETPLACE_MCP_REDIS_URL=redis://:SYNTHETIC_PASSWORD@PRIVATE_HOST/0\nWB_TOKEN=SYNTHETIC_WB_TOKEN\n')
        result=c.read_env(p,uid=os.geteuid())
        self.assertEqual(result,['MARKETPLACE_MCP_REDIS_URL'])
        self.assertNotIn('PRIVATE',json.dumps(result));self.assertNotIn('PASSWORD',json.dumps(result))
    def test_strict_config_rejects_extra_variables_and_duplicates(self):
        for text in ['WB_TOKEN=synthetic\n','MARKETPLACE_MCP_REDIS_HOST=a\nMARKETPLACE_MCP_REDIS_HOST=b\n','LD_PRELOAD=x\n','MARKETPLACE_MCP_REDIS_PASSWORD=x\n']:
            with self.assertRaises(ValueError):c.read_env(self.env(text),strict=True,uid=os.geteuid())
    def test_symlink_and_large_file_rejected(self):
        p=self.env('x'*65537)
        with self.assertRaises(ValueError):c.read_env(p,uid=os.geteuid())
        p.unlink();p.symlink_to('/not-used')
        with self.assertRaises(ValueError):c.read_env(p,uid=os.geteuid())
    def test_missing_approved_config_never_runs_probe(self):
        output=[]
        with patch.object(os,'geteuid',return_value=0),patch.object(c,'CONFIG',self.dir/'absent'),patch.object(c,'discover',return_value={}),patch.object(c,'verify_release',side_effect=AssertionError('no execution')),patch.object(c.subprocess,'run',side_effect=AssertionError('no execution')),patch('builtins.print',side_effect=output.append):
            self.assertEqual(c.main(),0)
        result=json.loads(output[0]);self.assertEqual(result['C'],'NOT_CONFIGURED_APPROVED_BACKEND_REQUIRED')
        self.assertEqual(result['quota_writes'],0)
    def test_nonroot_stops_before_discovery(self):
        with patch.object(os,'geteuid',return_value=1001),patch.object(c,'discover',side_effect=AssertionError('no read')),patch('builtins.print'):
            self.assertEqual(c.main(),2)
    def test_no_config_writes_or_installation_actions(self):
        source=(ROOT/'scripts/wb_redis_c/check.py').read_text()
        for text in ['write_text(', 'write_bytes(', 'os.chmod(', 'useradd', 'copy_one(', 'try_acquire(', 'defer(', 'eval(', 'MSP_REPORTS_SHARED_QUEUE_VERIFIED=YES']:
            self.assertNotIn(text,source)
