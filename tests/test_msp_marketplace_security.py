"""Offline verification of guarded transport and staging; never opens an API socket."""
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from apps.msp_marketplace_reports.archive import verify
from apps.msp_marketplace_reports.ingest import ingest_rows, write_staging_csv
from apps.msp_marketplace_reports.providers import ProviderError, Request, WB_LIST
from apps.msp_marketplace_reports.runtime import (
    _endpoint, credential_status, load_credentials, ReadOnlyHTTP,
)


class SecureTransportTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.credentials = self.root / "credentials.json"
        self.credentials.write_text(json.dumps({
            "wb_laser_master": {"token": "DUMMY_TEST_TOKEN_DO_NOT_USE"},
            "ozon_dmitrieva": {"client_id": "TEST_ONLY", "api_key": "DUMMY"},
        }))
        self.credentials.chmod(0o600)

    def test_local_credential_presence_only(self):
        status = credential_status(self.credentials)
        self.assertTrue(status["wb_laser_master"])
        self.assertTrue(status["ozon_dmitrieva"])
        self.assertFalse(status["wb_novokshenov"])
        self.assertNotIn("DUMMY", str(status))

    def test_unprotected_secret_file_refused(self):
        self.credentials.chmod(0o644)
        with self.assertRaisesRegex(ProviderError, "permissions"):
            load_credentials(self.credentials)

    def test_symlink_refused(self):
        alias = self.root / "link.json"
        alias.symlink_to(self.credentials)
        with self.assertRaisesRegex(ProviderError, "symlink"):
            load_credentials(alias)

    def test_fixed_hosts_only(self):
        self.assertEqual(_endpoint(Request("wb", WB_LIST, {})),
                         "https://finance-api.wildberries.ru" + WB_LIST)
        with self.assertRaises(ProviderError):
            _endpoint(Request("ozon", "/v4/posting/fbs/ship", {}))
        with self.assertRaises(ProviderError):
            _endpoint(Request("wb", "/api/finance/v1/sales-reports/detailed/2/../malicious", {}))

    def test_transport_does_not_call_api_on_creation(self):
        client = ReadOnlyHTTP(
            cabinet="wb_laser_master", credentials_file=self.credentials, state_root=self.root
        )
        self.assertEqual(client.marketplace, "wb")
        with self.assertRaisesRegex(ProviderError, "mismatch"):
            client(Request("ozon", "/v1/finance/realization/posting", {"year": 2026, "month": 9}))

    def test_shared_quota_unverified_blocks_provider_before_network(self):
        client = ReadOnlyHTTP(
            cabinet="wb_laser_master", credentials_file=self.credentials, state_root=self.root
        )
        def fail_if_called(*args, **kwargs):
            self.fail("Network must not be used before shared quota verification")
        client.opener.open = fail_if_called
        with self.assertRaisesRegex(ProviderError, "API DOWNLOAD BLOCKED"):
            client(Request("wb", WB_LIST, {"dateFrom": "2026-10-01",
                                           "dateTo": "2026-10-27", "period": "weekly",
                                           "limit": 1, "offset": 0}))

    def test_live_pilot_runner_wrong_identity_cannot_read_credentials(self):
        import importlib.util
        from unittest.mock import patch
        source=Path(__file__).resolve().parents[1]/'scripts/wb_live_pilot/runner.py'
        spec=importlib.util.spec_from_file_location('pilot_identity_boundary',source)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with patch.object(os,'geteuid',return_value=1001), patch.object(Path,'read_bytes',side_effect=AssertionError('no credential/code read')):
            with self.assertRaisesRegex(ValueError,'msp-reports'):
                module.main()


class StagingTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_nested_ozon_preserves_raw_json_and_local_integrity(self):
        rows = [{"row_number": 1, "report_year": 2026, "report_month": "2026-09",
                 "item": {"offer_id": "ABC", "sku": 12}}]
        result = ingest_rows(self.root, "ozon_final_realization", "ozon_dmitrieva", "2026-09",
                             rows, ("report_year", "report_month", "row_number"))
        self.assertEqual(result["annual_rows"], 1)
        file = Path(result["path"])
        self.assertIn(b"_raw_json", file.read_bytes())
        self.assertTrue(verify(self.root)["ok"])

    def test_duplicate_report_row_rejected_without_write(self):
        rows = [{"reportId": 11, "rrdId": 12}, {"reportId": 11, "rrdId": 12}]
        with self.assertRaises(ProviderError):
            ingest_rows(self.root, "wb_weekly_finance_main", "wb_laser_master", "2026",
                        rows, ("reportId", "rrdId"))
        self.assertFalse((self.root / "База данных").exists())

    def test_empty_source_not_silent_zero(self):
        with self.assertRaisesRegex(ProviderError, "zero rows"):
            ingest_rows(self.root, "wb_weekly_finance_main", "wb_laser_master", "2026", [],
                        ("reportId", "rrdId"))


if __name__ == "__main__":
    unittest.main()

class RealApprovalPermissionTest(unittest.TestCase):
    def test_actual_unprivileged_process_reads_only_fixed_group_approval(self):
        import subprocess
        import shutil
        import sys
        repo=Path(__file__).resolve().parents[1]
        helper=repo/'scripts/wb_live_pilot/permission_harness.py'
        args=['/usr/bin/python3','-I','-B',str(helper),str(repo/'scripts/wb_live_pilot/launch.py')]
        if os.geteuid()!=0:
            if os.environ.get('GITHUB_ACTIONS')!='true' or not shutil.which('sudo'):
                self.skipTest('real root-owned fixture requires hosted CI sudo; no production escalation')
            args=['sudo','-n',*args]
        p=subprocess.run(args,capture_output=True,timeout=60)
        self.assertEqual(p.returncode,0,p.stderr.decode(errors='replace'))
        result=json.loads(p.stdout)
        print('REAL_APPROVAL_PERMISSION_PROOF '+json.dumps(result,sort_keys=True))
        self.assertEqual(result['old0600'],'PermissionError');self.assertEqual(result['fixed0640'],'PASS')
        self.assertNotEqual(result['actual_reader_uid'],0);self.assertTrue(result['root_owner_preserved']);self.assertEqual(result['provider_calls'],0)

class HistoryWorkerSecurity(unittest.TestCase):
    def test_history_worker_wrong_uid_cannot_read_credentials_or_authorization(self):
        import importlib.util
        from unittest.mock import patch
        root=Path(__file__).resolve().parents[1]
        spec=importlib.util.spec_from_file_location('fixed_history_worker',root/'scripts/wb_history/worker.py')
        worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
        with patch.object(os,'geteuid',return_value=1001),patch.object(Path,'read_text',side_effect=AssertionError('no secret reads')):
            with self.assertRaisesRegex(ValueError,'msp-reports'):worker.main()

class CampaignWakeSecurity(unittest.TestCase):
    def test_unprivileged_wake_cannot_supply_root_command_or_override_paths(self):
        import importlib.util
        root=Path(__file__).resolve().parents[1]
        spec=importlib.util.spec_from_file_location('campaign_admission',root/'scripts/finance_campaign/scope.py')
        scope=importlib.util.module_from_spec(spec);spec.loader.exec_module(scope)
        policy={'campaign_ids':['wb2026'],'max_wake_entries':3}
        for field in ('command','env','credentials_file','redis_url','reset_budget','report_id','release'):
            with self.assertRaises(ValueError):scope.admit_wake({'campaign_id':'wb2026','max_entries':1,field:'untrusted'},policy)

class FinanceControlActualSystemd(unittest.TestCase):
    def test_two_nonroot_wakes_real_systemd_cleanup_and_boot_equivalent_recovery(self):
        import subprocess,shutil
        root=Path(__file__).resolve().parents[1]
        if os.environ.get('GITHUB_ACTIONS')!='true':self.skipTest('ephemeral hosted CI root/systemd fixture only; no VPS mutation')
        args=['sudo','-n','/usr/bin/python3','-I','-B',str(root/'scripts/finance_control/systemd_fixture.py'),str(root)]
        p=subprocess.run(args,capture_output=True,timeout=240)
        self.assertEqual(p.returncode,0,p.stderr.decode(errors='replace')+p.stdout.decode(errors='replace'))
        proof=json.loads(p.stdout);self.assertEqual(proof['polkit_sequential_wakes'],2);self.assertTrue(proof['network_block_restored']);self.assertEqual(proof['entries_after_two'],2);self.assertEqual(proof['boot_equivalent_recovery_entries'],3);self.assertEqual(proof['provider_calls'],0);self.assertEqual(proof['diagnostics_nonroot_read'],'PASS');self.assertTrue(proof['diagnostics_no_financial_start'])
        print('REAL_SYSTEMD_CONTROL_PROOF '+json.dumps(proof,sort_keys=True))
