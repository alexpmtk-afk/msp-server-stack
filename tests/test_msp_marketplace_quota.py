"""Offline tests for shared seller/method Redis queue safety; no HTTP or Redis."""
import base64
import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path
from unittest.mock import patch

from apps.msp_marketplace_reports.providers import (
    ProviderError, Request, WB_LIST, WB_DETAIL, OZON_FINAL,
)
from apps.msp_marketplace_reports.quota import (
    SharedQuota, request_rules, retry_delay, stable_owner_key,
)


def fake_jwt(sid):
    payload = base64.urlsafe_b64encode(
        json.dumps({"sid": sid, "acc": 3}, separators=(",", ":")).encode()
    ).decode("ascii").rstrip("=")
    return "eyJhbGciOiJub25lIn0." + payload + ".c2ln"


class SharedQuotaOfflineTests(unittest.TestCase):
    def test_wb_uses_same_seller_for_token_rotation(self):
        sid = "seller-tests-only"
        a = stable_owner_key("wb", {"token": fake_jwt(sid)})
        b = stable_owner_key("wb", {"token": fake_jwt(sid) + "OTHER_SIGNATURE"})
        self.assertEqual(a, b)
        self.assertEqual(a, hashlib.sha256(("wb:seller:" + sid).encode()).hexdigest())
        self.assertNotIn(sid, a)
        self.assertNotEqual(a, stable_owner_key("wb", {"token": fake_jwt("other")}))

    def test_list_and_detail_same_conservative_shared_scope(self):
        c = {"token": fake_jwt("seller-1")}
        a = request_rules("wb", c, Request("wb", WB_LIST, {}))
        b = request_rules("wb", c, Request("wb", WB_DETAIL + "123", {"rrdId": 0}))
        self.assertEqual([(x.key, x.interval_seconds) for x in a],
                         [(x.key, x.interval_seconds) for x in b])
        self.assertEqual(len(a), 2)
        self.assertGreaterEqual(max(x.interval_seconds for x in a), 65)
        self.assertTrue(any(":catalog:" in x.key for x in a))

    def test_bad_wb_and_unknown_ozon_contract_fail_closed(self):
        with self.assertRaisesRegex(ProviderError, "identity unavailable"):
            stable_owner_key("wb", {"token": "bad-value"})
        with self.assertRaisesRegex(ProviderError, "not yet approved"):
            request_rules("ozon", {"client_id": "123", "api_key": "fake"},
                          Request("ozon", OZON_FINAL, {"year": 2026, "month": 9}))
        with self.assertRaisesRegex(ProviderError, "not yet approved"):
            request_rules("wb", {"token": fake_jwt("seller-1")},
                          Request("wb", "/api/v1/unknown", {}))

    def test_missing_approval_and_redis_block_network_reservation(self):
        quota = SharedQuota("wb", {"token": fake_jwt("seller-1")})
        with patch.dict(os.environ, {"MSP_REPORTS_SHARED_QUEUE_VERIFIED": "NO",
                                     "MARKETPLACE_MCP_REDIS_URL": "redis://127.0.0.1:6379/0"}):
            with self.assertRaisesRegex(ProviderError, "deployment unverified"):
                quota.reserve(Request("wb", WB_LIST, {}))
        with patch.dict(os.environ, {"MSP_REPORTS_SHARED_QUEUE_VERIFIED": "YES",
                                     "MARKETPLACE_MCP_REDIS_URL": ""}, clear=True):
            with self.assertRaisesRegex(ProviderError, "Redis unavailable"):
                quota.reserve(Request("wb", WB_LIST, {}))

    def test_retry_after_numeric_and_http_date_and_missing(self):
        c = {"token": fake_jwt("seller-1")}
        rules = request_rules("wb", c, Request("wb", WB_LIST, {}))
        self.assertEqual(retry_delay({}, rules), 65.0)
        self.assertEqual(retry_delay({"Retry-After": "180"}, rules), 180.0)
        self.assertEqual(retry_delay({"X-Ratelimit-Retry": "120"}, rules), 120.0)
        dt = datetime.now(timezone.utc) + timedelta(minutes=4)
        self.assertGreater(retry_delay({"Retry-After": format_datetime(dt)}, rules), 220.0)
        self.assertEqual(retry_delay({"Retry-After": "NaN"}, rules), 65.0)

    def test_controller_reservation_must_fail_closed_before_network(self):
        from apps.msp_marketplace_reports.runtime import ReadOnlyHTTP
        with tempfile.TemporaryDirectory() as tmp:
            cred = Path(tmp) / "cred.json"
            cred.write_text(json.dumps({"wb_laser_master": {"token": fake_jwt("seller-1")}}))
            cred.chmod(0o600)
            transport = ReadOnlyHTTP(cabinet="wb_laser_master", credentials_file=cred, state_root=Path(tmp))
            with patch.dict(os.environ, {"MSP_REPORTS_SHARED_QUEUE_VERIFIED": "NO",
                                         "MARKETPLACE_MCP_REDIS_URL": "redis://127.0.0.1:6379/0"}):
                with self.assertRaisesRegex(ProviderError, "API DOWNLOAD BLOCKED"):
                    transport(Request("wb", WB_LIST, {"dateFrom": "2026-10-01"}))
