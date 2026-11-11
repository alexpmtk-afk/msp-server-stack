import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

BASE = Path(__file__).parent
sys.path.insert(0, str(BASE / 'payload'))
import pilot
import run_root

def deny_network(event, args):
    if event in ('socket.connect', 'socket.bind', 'socket.getaddrinfo'):
        raise AssertionError('test network forbidden')
sys.addaudithook(deny_network)

def sample():
    return {'header': {'start_date': '2026-01-01', 'stop_date': '2026-01-31', 'number': 'FIXTURE'},
            'rows': [{'row_number': 2, 'item': {'sku': '001234'}, 'seller_price_per_instance': 2.50},
                     {'row_number': 1, 'item': {'sku': '003'}, 'return_commission': {'amount': 1}}]}

class PilotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=BASE)
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name)

    def retain(self, data=None):
        raw = pilot.doc(data if data is not None else sample())
        pilot.save(self.state / 'entry.json', pilot.doc(pilot.PLAN))
        pilot.save(self.state / 'response.json', raw)
        pilot.save(self.state / 'response.meta.json', pilot.doc({'status': 200, 'sha256': pilot.sha(raw)}))

    def test_synthetic_probe_digest_is_not_receipt_digest(self):
        evidence = {'probe_sha256': 'a'*64, 'result': {'synthetic_quota': 'PASS',
                    'clients': 2, 'keys': 4, 'ttl_ceiling_seconds': 715,
                    'provider_calls': 0, 'live_seller_keys_touched': 0, 'api_enabled': False}}
        raw = json.dumps(evidence).encode()
        self.assertNotEqual(pilot.sha(raw), evidence['probe_sha256'])
        run_root.verify_synthetic(raw, 'a'*64)
        # Formatting is not part of probe-origin identity.
        run_root.verify_synthetic(json.dumps(evidence, indent=2).encode(), 'a'*64)
        with self.assertRaises(ValueError):
            run_root.verify_synthetic(raw, 'b'*64)
        for key, value in [('synthetic_quota', 'FAIL'), ('clients', True),
                           ('provider_calls', 1), ('api_enabled', 0),
                           ('live_seller_keys_touched', 1), ('ttl_ceiling_seconds', 714)]:
            broken = json.loads(raw); broken['result'][key] = value
            with self.assertRaises(ValueError):
                run_root.verify_synthetic(json.dumps(broken).encode(), 'a'*64)
        with self.assertRaises(ValueError):
            run_root.verify_synthetic(b'{"probe_sha256":"a","probe_sha256":"a"}', 'a')

    def test_drop_directory_under_strict_umask_and_known_partial(self):
        path = self.state / 'drop.d'
        mask = os.umask(0o077)
        try:
            # Ownership mocked only because real root ownership isn't available.
            with patch.object(run_root, 'trust'):
                run_root.prepare_drop_directory(path, recovering=False)
                self.assertEqual(path.stat().st_mode & 0o777, 0o755)
                path.chmod(0o700)
                run_root.prepare_drop_directory(path, recovering=True)
                self.assertEqual(path.stat().st_mode & 0o777, 0o755)
                path.chmod(0o700)
                (path / 'foreign.conf').write_text('preserve')
                with self.assertRaises(ValueError):
                    run_root.prepare_drop_directory(path, recovering=True)
                self.assertEqual(path.stat().st_mode & 0o777, 0o700)
                self.assertEqual((path / 'foreign.conf').read_text(), 'preserve')
        finally:
            os.umask(mask)

    def test_partial_recovery_refuses_any_prior_budget_before_secrets(self):
        (self.state / 'entry.json').write_text('preserved')
        with patch.object(run_root, 'STATE', self.state), patch.object(run_root, 'trust'):
            with self.assertRaises(ValueError):
                run_root.verify_empty_partial({})
        self.assertEqual((self.state / 'entry.json').read_text(), 'preserved')

    def test_exact_empty_partial_validates_without_deleting_evidence(self):
        partial = self.state / 'partial'; partial.mkdir()
        state = self.state / 'state'; state.mkdir()
        drop = self.state / 'unit.d'; drop.mkdir(); drop.chmod(0o700)
        minimal = {'ozon_dmitrieva': {'client_id': '123', 'api_key': 'fixture'}}
        (partial / 'program.py').write_bytes(b'fixture')
        manifest = json.dumps({'program.py': pilot.sha(b'fixture')}).encode()
        (partial / 'MANIFEST.json').write_bytes(manifest)
        (partial / 'cabinets.json').write_text(json.dumps(minimal))
        (partial / 'approval.json').write_text(json.dumps({'plan': pilot.PLAN}))
        from types import SimpleNamespace
        real_stat = Path.stat
        def stat_path(path, *a, **kw):
            if path == partial / 'cabinets.json': return SimpleNamespace(st_gid=985)
            return real_stat(path, *a, **kw)
        with patch.object(run_root, 'STATE', state), patch.object(run_root, 'PARTIAL', partial), patch.object(run_root, 'PARTIAL_MANIFEST', pilot.sha(manifest)), patch.object(run_root, 'DROP', drop / 'fixed.conf'), patch.object(run_root, 'trust'), patch.object(Path, 'stat', stat_path):
            run_root.verify_empty_partial(minimal)
            (partial / 'program.py').write_bytes(b'changed')
            with self.assertRaises(ValueError):
                run_root.verify_empty_partial(minimal)
        self.assertTrue((partial / 'cabinets.json').exists())
        self.assertEqual(list(state.iterdir()), [])

    def test_replay_does_not_construct_transport_or_read_credentials(self):
        self.retain()
        with patch.object(pilot, 'load_credentials', side_effect=AssertionError('credentials')), patch.object(pilot.FinalQuota, '__init__', side_effect=AssertionError('quota')):
            result = pilot.execute(self.state, factory=lambda: self.fail('transport'))
            self.assertEqual(result['rows'], 2)
            csv = (self.state / 'report.csv').read_bytes()
            self.assertIn(b'001234', csv)
            self.assertIn(b'_raw_json', csv)
            self.assertEqual(pilot.execute(self.state)['csv_sha256'], result['csv_sha256'])
            self.assertEqual(csv, (self.state / 'report.csv').read_bytes())

    def test_unknown_entry_never_retries(self):
        pilot.save(self.state / 'entry.json', pilot.doc(pilot.PLAN))
        with self.assertRaises(ValueError), patch.object(pilot, 'load_credentials', side_effect=AssertionError('credentials')):
            pilot.execute(self.state)

    def test_corrupt_retained_bytes_hold(self):
        self.retain()
        (self.state / 'response.json').write_bytes(b'{}')
        with self.assertRaises(ValueError):
            pilot.execute(self.state)
        self.assertFalse((self.state / 'report.csv').exists())

    def test_corrupt_csv_does_not_silently_replace(self):
        self.retain()
        pilot.execute(self.state)
        (self.state / 'report.csv').write_bytes(b'bad')
        with self.assertRaises(ValueError):
            pilot.execute(self.state)
        self.assertEqual((self.state / 'report.csv').read_bytes(), b'bad')

    def test_period_identity_and_empty_fail_closed(self):
        for mutate in (lambda d: d['header'].update(start_date='2025-01-01'),
                       lambda d: d['header'].update(number=''),
                       lambda d: d.update(rows=[]),
                       lambda d: d['rows'][1].update(row_number=2),
                       lambda d: d['rows'][1].update(row_number=True),
                       lambda d: d['rows'][1].update(report_month='2025-01')):
            data = sample(); mutate(data)
            with self.assertRaises(ValueError):
                pilot.validate(pilot.doc(data))

    def test_json_ambiguity_rejected(self):
        for raw in (b'{"rows":[],"rows":[]}', b'{"number":NaN}'):
            with self.assertRaises(ValueError):
                pilot.strict(raw)

    def test_only_fixed_final_request_and_original_shared_keys(self):
        from apps.msp_marketplace_reports.providers import Request
        from apps.msp_marketplace_reports.quota import stable_owner_key
        cred = {'client_id': '123', 'api_key': 'fixture'}
        gate = pilot.FinalQuota('ozon', cred)
        seen = []
        async def controller(url, fn):
            class C:
                async def try_acquire(self, rules):
                    seen.extend(rules)
                    return True, 0
            return await fn(C())
        with patch.dict(os.environ, {'MSP_REPORTS_SHARED_QUEUE_VERIFIED': 'YES', 'MARKETPLACE_MCP_REDIS_URL': 'redis://127.0.0.1/0'}), patch.object(pilot.q, '_with_controller', controller):
            gate.reserve(Request('ozon', pilot.PLAN['path'], {'year': 2026, 'month': 1}))
            self.assertEqual(len(seen), 2)
            owner = stable_owner_key('ozon', cred)
            self.assertTrue(all(owner in rule.key for rule in seen))
            self.assertTrue(any(rule.key.endswith(':global') for rule in seen))
            self.assertTrue(any(rule.key.endswith(':msp-finance-safety') and rule.interval_seconds == 60 for rule in seen))
            for req in (Request('ozon', '/v3/posting/fbo/list', {}), Request('ozon', pilot.PLAN['path'], {'year': 2026, 'month': 11})):
                with self.assertRaises(ValueError):
                    gate.reserve(req)

    def test_429_defers_both_existing_buckets(self):
        gate = pilot.FinalQuota('ozon', {'client_id': '123'})
        rules = [pilot.RateRule('x:global', 0.02), pilot.RateRule('x:msp-finance-safety', 60)]
        deferred = []
        async def controller(url, fn):
            class C:
                async def defer(self, rules, delay):
                    deferred.append(([x.key for x in rules], delay))
            return await fn(C())
        with patch.object(gate, '_approved_url', return_value='redis://fixture'), patch.object(pilot.q, '_with_controller', controller):
            gate.cooldown(rules, {'Retry-After': '90'})
        self.assertEqual(deferred, [(['x:global'], 90), (['x:msp-finance-safety'], 90)])

    def test_nonroot_refuses_before_protected_access(self):
        with patch.object(run_root.os, 'geteuid', return_value=1001), patch.object(run_root, 'verify_payload', side_effect=AssertionError('protected access')):
            with self.assertRaises(PermissionError):
                run_root.execute()

    def test_successful_dispatch_retained_before_schema_failure_then_no_refetch(self):
        creds = self.state / 'credentials'; creds.mkdir()
        (creds / 'cabinets.json').write_text(json.dumps({'ozon_dmitrieva': {'client_id': '123', 'api_key': 'fixture'}}))
        (creds / 'cabinets.json').chmod(0o600)
        calls = []
        class Response:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def read(self, limit): return b'{"unexpected":true}'
        class Opener:
            def open(self, req, timeout):
                calls.append((req.full_url, req.get_method(), req.data))
                return Response()
        with patch.dict(os.environ, {'CREDENTIALS_DIRECTORY': str(creds)}), patch.object(pilot.FinalQuota, '_approved_url', return_value='redis://fixture'), patch.object(pilot.FinalQuota, 'reserve', return_value=[]):
            with self.assertRaises(ValueError):
                pilot.execute(self.state, factory=Opener)
        self.assertEqual(calls, [('https://api-seller.ozon.ru/v1/finance/realization/posting', 'POST', b'{"year":2026,"month":1}')])
        self.assertEqual((self.state / 'response.json').read_bytes(), b'{"unexpected":true}')
        with self.assertRaises(ValueError), patch.object(pilot, 'load_credentials', side_effect=AssertionError('credentials')):
            pilot.execute(self.state, factory=lambda: self.fail('refetch'))

    def test_timeout_consumes_only_entry_and_never_retries(self):
        creds = self.state / 'credentials'; creds.mkdir()
        (creds / 'cabinets.json').write_text(json.dumps({'ozon_dmitrieva': {'client_id': '123', 'api_key': 'fixture'}}))
        (creds / 'cabinets.json').chmod(0o600)
        class Opener:
            def open(self, req, timeout): raise TimeoutError()
        with patch.dict(os.environ, {'CREDENTIALS_DIRECTORY': str(creds)}), patch.object(pilot.FinalQuota, '_approved_url', return_value='redis://fixture'), patch.object(pilot.FinalQuota, 'reserve', return_value=[]):
            with self.assertRaises(TimeoutError):
                pilot.execute(self.state, factory=Opener)
        with self.assertRaises(ValueError), patch.object(pilot, 'load_credentials', side_effect=AssertionError('credentials')):
            pilot.execute(self.state)
        self.assertTrue((self.state / 'entry.json').exists())

    def test_coordinator_cleanup_and_receipt_even_worker_hold(self):
        root = self.state / 'release'; root.mkdir()
        state = self.state / 'reports' / 'pilot'; state.parent.mkdir()
        drop = self.state / 'unit.d' / '91.conf'
        result = self.state / 'result.json'
        commands = []
        def command(args, timeout=30):
            commands.append(args)
            if 'start' in args:
                (state / 'worker-result.json').write_text(json.dumps({'status': 'HOLD', 'error_type': 'ValueError', 'secret_unexpected': 'not allowed'}))
                raise RuntimeError('worker failed')
            return b''
        inactive = {'ActiveState': 'inactive', 'PrivateNetwork': 'yes', 'DropInPaths': ''}
        from contextlib import ExitStack
        lock = self.state / 'lock'; lock.write_text('')
        original_path = run_root.Path
        def paths(value):
            if value == '/var/lib/msp-finance-control/controller.lock': return lock
            return original_path(value)
        with ExitStack() as stack:
            for name, value in {'ROOT': root, 'STATE': state, 'ARCHIVE': state.parent, 'DROP': drop, 'RESULT': result}.items():
                stack.enter_context(patch.object(run_root, name, value))
            stack.enter_context(patch.object(run_root, 'Path', paths))
            stack.enter_context(patch.object(run_root.os, 'geteuid', return_value=0))
            stack.enter_context(patch.object(run_root.os, 'chown'))
            stack.enter_context(patch.object(run_root.os, 'fchown'))
            stack.enter_context(patch.object(run_root, 'verify_payload'))
            stack.enter_context(patch.object(run_root, 'trust'))
            stack.enter_context(patch.object(run_root, 'preflight', return_value=({'ozon_dmitrieva': {}}, ['127.0.0.1/32'])))
            stack.enter_context(patch.object(run_root, 'run', command))
            stack.enter_context(patch.object(run_root, 'show', return_value=inactive))
            real_stat = Path.lstat
            # Worker ownership is modelled independently of our current UID.
            from types import SimpleNamespace
            def stat_path(path):
                if path == state / 'worker-result.json':
                    return SimpleNamespace(st_mode=0o100644, st_uid=995, st_nlink=1)
                return real_stat(path)
            stack.enter_context(patch.object(Path, 'lstat', stat_path))
            self.assertEqual(run_root.execute(), 1)
        self.assertFalse(drop.exists())
        self.assertFalse((root / 'cabinets.json').exists())
        receipt = json.loads(result.read_text())
        self.assertTrue(receipt['temporary_activation_removed'])
        self.assertNotIn('secret_unexpected', receipt)
        self.assertEqual(sum('start' in args for args in commands), 1)

if __name__ == '__main__':
    unittest.main()
