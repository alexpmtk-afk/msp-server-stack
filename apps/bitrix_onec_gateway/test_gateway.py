"""Offline contract/security tests. Synthetic data only; no CRM, VPS or 1C."""
import hashlib
import hmac
import json
import os
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path

from gateway import (CREATE_PATH, CLAIM_PATH, PORTAL, connect, handler_factory,
                     initialize, make_config)

APP_KEY = "A" * 64
SRV_KEY = "B" * 64
MEMBER = "test_member_0123456789"


class GatewayTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        env = {"B24_GW_APP_HMAC_KEY": APP_KEY, "B24_GW_SRV_BEARER": SRV_KEY,
               "B24_GW_MEMBER_ID": MEMBER,
               "B24_GW_DB": str(Path(self.tmp.name) / "commands.sqlite3")}
        self.cfg = make_config(env)
        initialize(self.cfg["db"])
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler_factory(self.cfg))
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:" + str(self.httpd.server_port)

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=3)
        self.tmp.cleanup()

    def command(self, deal=3, request_id=None):
        return {
            "schema_version": 1,
            "request_id": request_id or str(uuid.uuid4()),
            "action": "CUSTOMER_ORDER_REQUEST",
            "portal": PORTAL,
            "portal_member_id": MEMBER,
            "entity_type_id": 2,
            "deal_id": deal,
            "requested_by_user_id": 1,
            "target": "TEST_NEWBASE",
            "created_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    def call(self, path, data=None, role="app", nonce=None, method=None,
             stamp=None, wrong_key=False):
        body = json.dumps(data, separators=(",", ":")).encode() if data is not None else b""
        method = method or ("POST" if data is not None else "GET")
        headers = {}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if role == "app":
            ts = stamp or str(int(time.time()))
            n = nonce or uuid.uuid4().hex
            msg = "\n".join([method, path, ts, n, hashlib.sha256(body).hexdigest()]).encode()
            key = (b"Z" * 64) if wrong_key else APP_KEY.encode()
            headers.update({"X-B24-Timestamp": ts, "X-B24-Nonce": n,
                            "X-B24-Signature": hmac.new(key, msg, hashlib.sha256).hexdigest()})
        if role == "srv":
            headers["Authorization"] = "Bearer " + SRV_KEY
        req = urllib.request.Request(self.base + path,
                                     data=body if method == "POST" else None,
                                     headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=3) as resp:
                return resp.status, json.load(resp)
        except urllib.error.HTTPError as ex:
            return ex.code, json.load(ex)

    def test_delivery_ack_and_status(self):
        command = self.command()
        code, created = self.call(CREATE_PATH, command)
        self.assertEqual((code, created["status"]), (202, "QUEUED"))
        rid = created["request_id"]
        status = CREATE_PATH + "/" + rid
        self.assertEqual(self.call(status)[1]["status"], "QUEUED")
        self.assertEqual(self.call(CLAIM_PATH, {"worker_id": "SRV", "max_jobs": 1}, role="none")[0], 401)
        code, leased = self.call(CLAIM_PATH, {"worker_id": "SRV", "max_jobs": 1}, role="srv")
        self.assertEqual((code, leased["job"]["deal_id"]), (200, 3))
        self.assertIsNone(self.call(CLAIM_PATH, {"worker_id": "SRV", "max_jobs": 1}, role="srv")[1]["job"])
        ack_path = CREATE_PATH + "/" + rid + "/ack"
        self.assertEqual(self.call(ack_path, {"lease_token": "x" * 43}, role="srv")[0], 409)
        self.assertEqual(self.call(ack_path, {"lease_token": leased["job"]["lease_token"]}, role="srv")[1]["status"],
                         "RECEIVED_BY_SRV")
        self.assertEqual(self.call(status)[1]["status"], "RECEIVED_BY_SRV")
        self.assertIsNone(self.call(CLAIM_PATH, {"worker_id": "SRV", "max_jobs": 1}, role="srv")[1]["job"])

    def test_duplicate_and_nonce_replay(self):
        cmd = self.command()
        n = uuid.uuid4().hex
        self.assertEqual(self.call(CREATE_PATH, cmd, nonce=n)[0], 202)
        self.assertEqual(self.call(CREATE_PATH, cmd, nonce=n)[0], 409)
        code, repeated = self.call(CREATE_PATH, cmd)
        self.assertEqual(code, 200)
        self.assertTrue(repeated["duplicate"])
        code, new_id_same_deal = self.call(CREATE_PATH, self.command())
        self.assertEqual(code, 200)
        self.assertEqual(new_id_same_deal["request_id"], cmd["request_id"])
        with connect(self.cfg["db"]) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM commands").fetchone()[0], 1)

    def test_bounded_roles_and_failed_delivery(self):
        command = self.command()
        self.assertEqual(self.call(CREATE_PATH, command, wrong_key=True)[0], 401)
        self.assertEqual(self.call(CREATE_PATH, command,
                         stamp=str(int(time.time()) - 900))[0], 401)
        bad = dict(command, portal="evil.example")
        self.assertEqual(self.call(CREATE_PATH, bad)[0], 400)
        bad = dict(command, target="PRODUCTION")
        self.assertEqual(self.call(CREATE_PATH, bad)[0], 400)
        self.assertEqual(self.call(CREATE_PATH, command)[0], 202)
        self.call(CLAIM_PATH, {"worker_id": "SRV", "max_jobs": 1}, role="srv")
        with connect(self.cfg["db"]) as db:
            db.execute("UPDATE commands SET attempts=3,lease_until=0")
        self.assertIsNone(self.call(CLAIM_PATH, {"worker_id": "SRV", "max_jobs": 1}, role="srv")[1]["job"])
        self.assertEqual(self.call(CREATE_PATH + "/" + command["request_id"])[1]["status"], "FAILED_DELIVERY")

    def test_concurrent_requests_one_logical_job(self):
        def submit(_):
            return self.call(CREATE_PATH, self.command(deal=27))
        with ThreadPoolExecutor(max_workers=6) as pool:
            result = list(pool.map(submit, range(12)))
        self.assertEqual(sum(status == 202 for status, _ in result), 1)
        self.assertEqual(sum(status == 200 for status, _ in result), 11)
        with connect(self.cfg["db"]) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM commands").fetchone()[0], 1)
        initialize(self.cfg["db"])
        with connect(self.cfg["db"]) as db:
            self.assertEqual(db.execute("SELECT status FROM commands").fetchone()[0], "QUEUED")


if __name__ == "__main__":
    unittest.main()
