"""Real isolated Redis on a temporary UNIX socket. No public port/provider API.

Synthetic writes affect only this scratch Redis. No host installation/systemd.
"""
import asyncio
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
RUNTIME=Path(os.environ.get('MSP_REDIS_TEST_RUNTIME','/home/hermes/.hermes/cache/scratch/wb-redis-runtime-20261103'))
sys.path.insert(0,str(ROOT/'scripts/quota_redis'))
import common
# Use the accepted client's wheel locally, not a global installation.
WHEEL=Path('/home/hermes/.hermes/cache/scratch/redis-8.1.0-py3-none-any.whl')
if WHEEL.exists():sys.path.insert(0,str(WHEEL))
try:import redis
except ImportError:redis=None
from apps.msp_marketplace_reports.shared_rate_limit import GlobalRateController,RateRule,RateLimitUnavailable
spec=importlib.util.spec_from_file_location('probe',ROOT/'docs/marketplace-reports/admin-ready/redis_readonly_probe.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)

class Pure(unittest.TestCase):
    def test_config_is_local_persistent_strict_and_noeviction(self):
        s=common.config_text(Path('/data'),Path('/acl'))
        for line in ['bind 127.0.0.1','protected-mode yes','appendonly yes','appendfsync always','aof-load-truncated no','maxmemory-policy noeviction']:
            self.assertIn(line,s)
        self.assertNotIn('0.0.0.0',s)
    def test_acl_hides_password_and_admin_commands(self):
        p='a'*64;q='b'*64;s=common.acl_text(p,q)
        self.assertNotIn(p,s);self.assertNotIn(q,s)
        self.assertIn('user default off',s)
        self.assertNotIn('+@all',s);self.assertNotIn('+config',s);self.assertNotIn('+flush',s)
    def test_explicit_public_mode_under_private_umask(self):
        with tempfile.TemporaryDirectory() as d:
            prev=os.umask(0o077)
            try:
                common.write_new(Path(d)/'public',b'code',0o644,os.geteuid(),os.getegid())
                common.write_new(Path(d)/'private',b'synthetic',0o600,os.geteuid(),os.getegid())
            finally:os.umask(prev)
            self.assertEqual(stat.S_IMODE((Path(d)/'public').stat().st_mode),0o644)
            self.assertEqual(stat.S_IMODE((Path(d)/'private').stat().st_mode),0o600)
            with self.assertRaises(FileExistsError):common.write_new(Path(d)/'private',b'replace',uid=os.geteuid(),gid=os.getegid())
    def test_nonroot_installer_refuses_before_reads(self):
        spec=importlib.util.spec_from_file_location('redis_install',ROOT/'scripts/quota_redis/install.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        with patch.object(os,'geteuid',return_value=1001),patch.object(m,'verify_bundle',side_effect=AssertionError('no read')),patch('builtins.print'):
            self.assertEqual(m.main(),2)

@unittest.skipUnless(redis is not None and (RUNTIME/'bin/redis-server').exists(),'offline runtime/wheel required')
class RealRedis(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR'));self.addCleanup(self.temp.cleanup)
        self.p=Path(self.temp.name);self.data=self.p/'data';self.data.mkdir(mode=0o700)
        self.pw=secrets.token_hex(32);self.ro=secrets.token_hex(32)
        (self.p/'acl').write_text(common.acl_text(self.pw,self.ro))
        (self.p/'conf').write_text(common.config_text(self.data,self.p/'acl',port=0,socket_path=self.p/'sock'))
        self.env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','LD_LIBRARY_PATH':str(RUNTIME/'lib')}
        self.process=None;self.log=None;self.start();self.addCleanup(self.stop)
        self.client=redis.Redis(unix_socket_path=str(self.p/'sock'),username='quota_runtime',password=self.pw,decode_responses=True)
        self.reader=redis.Redis(unix_socket_path=str(self.p/'sock'),username='quota_readonly',password=self.ro,decode_responses=True)
        self.addCleanup(self.client.close);self.addCleanup(self.reader.close)
        self.key='marketplace-rate:v1:wb:synthetic-'+secrets.token_hex(6)+':catalog:test'
    def start(self):
        if (self.p/'sock').exists():(self.p/'sock').unlink()
        self.log=(self.p/'log').open('a+')
        self.process=subprocess.Popen([str(RUNTIME/'bin/redis-server'),str(self.p/'conf')],env=self.env,stdout=self.log,stderr=self.log)
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            if self.process.poll() is not None:raise AssertionError('isolated Redis failed; see private test log')
            if (self.p/'sock').exists():return
            time.sleep(.02)
        raise AssertionError('Redis startup timeout')
    def stop(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate();self.process.wait(timeout=8)
        if self.log:self.log.close()
    def url(self):return 'unix://quota_runtime:'+self.pw+'@'+str(self.p/'sock')+'?db=0'
    async def controller(self):return GlobalRateController(redis_url=self.url(),sqlite_path=self.p/'never.sqlite3')
    async def closec(self,c):
        if c._redis is not None:await c._redis.aclose()
    def test_readonly_default_resp2_and_no_write(self):
        def factory(protocol):
            kw={} if protocol is None else {'protocol':protocol}
            return redis.Redis(unix_socket_path=str(self.p/'sock'),username='quota_readonly',password=self.ro,decode_responses=True,**kw)
        result=probe.probe(factory,[self.key])
        self.assertEqual(result['read_only_protocol_check'],'PASS')
        with self.assertRaises(redis.exceptions.ResponseError):self.reader.set(self.key,'bad')
        with self.assertRaises(redis.exceptions.ResponseError):self.reader.eval('return 1',0)
    def test_auth_acl_namespace_and_destructive_commands_denied(self):
        anonymous=redis.Redis(unix_socket_path=str(self.p/'sock'));self.addCleanup(anonymous.close)
        with self.assertRaises(redis.exceptions.AuthenticationError):anonymous.ping()
        for command,args in [('set',('outside-scope','bad')),('flushdb',()),('config_get',('*',)),('eval',("return redis.call('SET','outside-scope','bad')",0))]:
            with self.assertRaises(redis.exceptions.ResponseError):getattr(self.client,command)(*args)
    def test_real_async_atomic_competition_shared_seller_and_ozon(self):
        async def go():
            one=await self.controller();two=await self.controller()
            try:
                rule=[RateRule(self.key,60)]
                results=await asyncio.gather(one.try_acquire(rule),two.try_acquire(rule))
                self.assertEqual(sorted(x[0] for x in results),[False,True])
                allowed,_=await one.try_acquire([RateRule(self.key+'-another-seller',60)])
                self.assertTrue(allowed)
                allowed,_=await one.try_acquire([RateRule('marketplace-rate:v1:ozon:synthetic-client:global',.02)])
                self.assertTrue(allowed)
            finally:await self.closec(one);await self.closec(two)
        asyncio.run(go())
        self.assertFalse((self.p/'never.sqlite3').exists())
    def test_429_cooldown_defer_and_reserve_use_real_acl(self):
        async def go():
            c=await self.controller()
            try:
                rules=[RateRule(self.key,.1)]
                await c.defer(rules,30)
                allowed,wait=await c.try_acquire(rules)
                self.assertFalse(allowed);self.assertGreater(wait,20)
                delay=await c._reserve_redis([RateRule(self.key+'-reserve',1)])
                self.assertEqual(delay,0)
            finally:await self.closec(c)
        asyncio.run(go())
    def test_acknowledged_state_survives_sigkill_restart(self):
        self.client.set(self.key,'synthetic-persisted',px=600000)
        self.process.kill();self.process.wait(timeout=5);self.log.close();self.start()
        self.client.close()
        self.assertEqual(self.client.get(self.key),'synthetic-persisted')
    def test_corrupt_aof_refuses_start_without_auto_truncation(self):
        self.client.set(self.key,'synthetic-persisted');self.stop()
        f=next((self.data/'appendonlydir').glob('*.incr.aof'))
        with f.open('ab') as out:out.write(b'INVALID_RESP\n');out.flush();os.fsync(out.fileno())
        p=subprocess.Popen([str(RUNTIME/'bin/redis-server'),str(self.p/'conf')],env=self.env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:self.assertNotEqual(p.wait(timeout=5),0)
        finally:
            if p.poll() is None:p.kill();p.wait()
    def test_stopped_backup_restore_copy_aof_check_and_replay(self):
        self.client.set(self.key,'restored-value',px=600000);self.stop()
        copy=self.p/'restored';shutil.copytree(self.data,copy)
        result=subprocess.run([str(RUNTIME/'bin/redis-check-aof'),str(copy/'appendonlydir/appendonly.aof.manifest')],env=self.env,capture_output=True)
        self.assertEqual(result.returncode,0,'AOF offline check failed')
        self.data=copy;(self.p/'conf').write_text(common.config_text(copy,self.p/'acl',port=0,socket_path=self.p/'sock'))
        self.start();self.client.close();self.assertEqual(self.client.get(self.key),'restored-value')
    def test_backend_unavailable_fails_without_sqlite_fallback(self):
        self.stop()
        async def go():
            c=await self.controller()
            try:
                with self.assertRaises(RateLimitUnavailable):await c.try_acquire([RateRule(self.key,1)])
            finally:await self.closec(c)
        asyncio.run(go());self.assertFalse((self.p/'never.sqlite3').exists())


    def test_separate_processes_share_one_atomic_quota(self):
        import multiprocessing
        context=multiprocessing.get_context('fork');gate=context.Event();queue=context.Queue()
        url=self.url();key=self.key
        def child():
            async def go():
                c=GlobalRateController(redis_url=url)
                try:
                    grant,_=await c.try_acquire([RateRule(key,60)]);queue.put(grant)
                finally:
                    if c._redis is not None:await c._redis.aclose()
            gate.wait(5);asyncio.run(go())
        children=[context.Process(target=child) for _ in range(2)]
        for proc in children:proc.start()
        try:
            gate.set();results=[queue.get(timeout=8) for _ in children]
            self.assertEqual(sorted(results),[False,True])
            for proc in children:proc.join(8);self.assertEqual(proc.exitcode,0)
        finally:
            for proc in children:
                if proc.is_alive():proc.kill();proc.join()
            queue.close()
    def test_existing_controller_snapshot_real_acl(self):
        async def go():
            c=await self.controller()
            try:
                await c.try_acquire([RateRule(self.key,60)])
                data=await c.snapshot(self.key.rsplit(':catalog:',1)[0])
                self.assertEqual(data['backend'],'redis');self.assertEqual(len(data['active_queues']),1)
            finally:await self.closec(c)
        asyncio.run(go())

class PersistenceGuard(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.p=Path(self.tmp.name);self.data=self.p/'data';self.data.mkdir(mode=0o700)
        self.init=self.p/'initialized';self.permit=self.p/'permit';self.uid=os.geteuid()
    def file(self,p,data=b'allowed'):
        p.write_bytes(data);p.chmod(0o640)
    def test_no_first_start_without_private_root_permit(self):
        with self.assertRaises(FileNotFoundError):common.guard(self.data,self.init,self.permit,self.uid,marker_uid=self.uid)
        self.file(self.permit);common.guard(self.data,self.init,self.permit,self.uid,marker_uid=self.uid)
    def test_initialized_missing_aof_is_hold_not_empty_reset(self):
        self.file(self.init)
        with self.assertRaises(FileNotFoundError):common.guard(self.data,self.init,self.permit,self.uid,marker_uid=self.uid)
        aof=self.data/'appendonlydir';aof.mkdir(mode=0o700)
        self.file(aof/'appendonly.aof.manifest')
        common.guard(self.data,self.init,self.permit,self.uid,marker_uid=self.uid)
    def test_nonempty_partial_first_start_refused(self):
        self.file(self.permit);self.file(self.data/'unknown')
        with self.assertRaises(ValueError):common.guard(self.data,self.init,self.permit,self.uid,marker_uid=self.uid)
    def test_installer_does_not_recreate_AB_or_enable_provider(self):
        s=(ROOT/'scripts/quota_redis/install.py').read_text()
        for forbidden in ['MSP_REPORTS_SHARED_QUEUE_VERIFIED=YES','copy_one(',"'msp-reports','--no-create-home'",'wb_finance','try_acquire(','.eval(']:
            self.assertNotIn(forbidden,s)
        self.assertIn("'partial install; reconcile, no automatic retry'",s)

class InstallerRecoveryBoundaries(unittest.TestCase):
    def installer(self):
        spec=importlib.util.spec_from_file_location('redis_install_boundary',ROOT/'scripts/quota_redis/install.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
    def test_partial_install_refuses_without_password_generation_or_service_change(self):
        m=self.installer()
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'BEGIN.json').write_text('{}')
            previous=os.umask(0o077)
            try:
                with patch.object(os,'geteuid',return_value=0),patch.object(m,'STATE',p),patch.object(m,'verify_bundle',return_value=({},'synthetic-sha')),patch.object(m,'run') as run,patch.object(m.secrets,'token_hex') as rng,patch('builtins.print'):
                    self.assertEqual(m.main(),1);run.assert_not_called();rng.assert_not_called()
            finally:os.umask(previous)
    def test_complete_install_only_checks_no_restart_or_rotation(self):
        m=self.installer()
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'complete.json').write_text('{}')
            previous=os.umask(0o077)
            try:
                with patch.object(os,'geteuid',return_value=0),patch.object(m,'STATE',p),patch.object(m,'verify_bundle',return_value=({},'synthetic-sha')),patch.object(m,'check_existing') as check,patch.object(m,'run') as run,patch.object(m.secrets,'token_hex') as rng,patch('builtins.print'):
                    self.assertEqual(m.main(),0);check.assert_called_once_with('synthetic-sha');run.assert_not_called();rng.assert_not_called()
            finally:os.umask(previous)
    def test_backup_helper_preserves_source_and_refuses_symlink(self):
        spec=importlib.util.spec_from_file_location('redis_manage',ROOT/'scripts/quota_redis/manage.py')
        m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'data';source.mkdir(mode=0o700)
            f=source/'synthetic.aof';f.write_bytes(b'SYNTHETIC');f.chmod(0o600)
            def write(p,data):return common.write_new(p,data,uid=os.geteuid(),gid=os.getegid())
            with patch.object(m,'write_new',side_effect=write):rows=m.snapshot(source,root/'backup',uid=os.geteuid())
            self.assertEqual(rows,[{'path':'synthetic.aof','sha256':common.sha(b'SYNTHETIC')}])
            self.assertEqual((root/'backup/synthetic.aof').read_bytes(),f.read_bytes())
            (source/'link').symlink_to(f)
            with self.assertRaises(ValueError):m.snapshot(source,root/'refused',uid=os.geteuid())
            self.assertFalse((root/'refused').exists())

class ListenerValidation(unittest.TestCase):
    def test_accept_only_configured_loopback(self):
        common.assert_local_listener('LISTEN 0 511 127.0.0.1:16379 0.0.0.0:*\n')
    def test_reject_public_or_absent_listener(self):
        for text in ['', 'LISTEN 0 511 0.0.0.0:16379 0.0.0.0:*\n','LISTEN 0 511 [::]:16379 [::]:*\n']:
            with self.assertRaises(ValueError):common.assert_local_listener(text)

class RecoveryHold(unittest.TestCase):
    def test_hold_survives_restart_even_with_valid_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);data=root/'data';data.mkdir(mode=0o700)
            aof=data/'appendonlydir';aof.mkdir(mode=0o700)
            for p in [root/'initialized',root/'HOLD',aof/'appendonly.aof.manifest']:
                p.write_bytes(b'present');p.chmod(0o640)
            with self.assertRaises(ValueError):common.guard(data,root/'initialized',root/'absent',os.geteuid(),marker_uid=os.geteuid(),hold=root/'HOLD')
