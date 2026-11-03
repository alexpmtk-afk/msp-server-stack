import asyncio
import importlib.util
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
import test_msp_quota_redis as fixtures
spec=importlib.util.spec_from_file_location('synthetic',ROOT/'docs/marketplace-reports/pilot-next-20261103/synthetic_quota.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class SyntheticBoundaries(unittest.TestCase):
    def test_refuses_nonapproved_targets(self):
        for u in ['redis://quota_runtime:fake@127.0.0.1:6379/0','redis://quota_runtime:fake@external:16379/0','redis://quota_runtime:fake@127.0.0.1:16379/1','redis://quota_readonly:fake@127.0.0.1:16379/0']:
            with self.assertRaises(ValueError):m.loopback_url(u)

@unittest.skipUnless(fixtures.redis is not None and (fixtures.RUNTIME/'bin/redis-server').exists(),'offline runtime required')
class SyntheticRuntime(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.RealRedis(methodName='test_readonly_default_resp2_and_no_write')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
    def test_prepared_probe_on_isolated_server(self):
        result=asyncio.run(m.exercise(self.fixture.url()))
        self.assertEqual(result['synthetic_quota'],'PASS')
        self.assertEqual(result['provider_calls'],0)
        keys=list(self.fixture.client.scan_iter(match='marketplace-rate:v1:wb:synthetic-pilot-*'))
        self.assertEqual(len(keys),4)
        for key in keys:
            self.assertTrue(key.startswith('marketplace-rate:v1:wb:synthetic-pilot-'))
            self.assertLessEqual(self.fixture.reader.pttl(key),715000)
            self.assertGreater(self.fixture.reader.pttl(key),0)
