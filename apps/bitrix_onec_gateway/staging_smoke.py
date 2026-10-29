"""Synthetic-only loopback smoke for unprivileged Phase B staging gateway."""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import stat
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

from gateway import CREATE_PATH, CLAIM_PATH, PORTAL

# Only test inside STAGING home path. No actual Bitrix or 1C API calls.
def main():
    base = Path.home() / ".config/bitrix-onec-gateway-staging/gateway.env"
    if not base.is_file() or stat.S_IMODE(base.stat().st_mode) != 0o600:
        raise RuntimeError("INVALID_STAGING_SECRET_FILE")
    settings = {}
    for line in base.read_text(encoding="ascii").splitlines():
        key, _, value = line.partition("=")
        settings[key] = value
    if settings.get("B24_GW_MEMBER_ID") != "STAGING_ONLY_20261029":
        raise RuntimeError("NOT_STAGING_MEMBER")
    appkey = settings["B24_GW_APP_HMAC_KEY"].encode("ascii")
    srvkey = settings["B24_GW_SRV_BEARER"]
    url = "http://127.0.0.1:9794"
    def send(path, body=None, role="app", method=None, sig_valid=True):
        method = method or ("POST" if body is not None else "GET")
        raw = json.dumps(body, separators=(",", ":")).encode() if body is not None else b""
        headers = {}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if role == "app":
            timestamp = str(int(time.time()))
            nonce = secrets.token_urlsafe(24)
            signed = "\n".join([method, path, timestamp, nonce, hashlib.sha256(raw).hexdigest()]).encode("ascii")
            digest = hmac.new(appkey, signed, hashlib.sha256).hexdigest()
            if not sig_valid:
                digest = "0" * 64 if digest != "0" * 64 else "1" * 64
            headers.update({"X-B24-Timestamp": timestamp, "X-B24-Nonce": nonce, "X-B24-Signature": digest})
        elif role == "srv":
            headers["Authorization"] = "Bearer " + srvkey
        req = urllib.request.Request(url + path,
                   data=raw if method == "POST" else None,
                   method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=4) as resp:
                return resp.status, json.loads(resp.read(4096))
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read(4096))
    # No public routes and no unauthorized access.
    assert send(CREATE_PATH, {"invalid": True}, sig_valid=False)[0] == 401
    assert send(CLAIM_PATH, {"worker_id": "SRV", "max_jobs": 1}, role="none")[0] == 401
    assert send("/health", role="none")[0] == 404
    payload = {
        "schema_version": 1, "request_id": str(uuid.uuid4()),
        "action": "CUSTOMER_ORDER_REQUEST",
        "portal": PORTAL, "portal_member_id": "STAGING_ONLY_20261029",
        "entity_type_id": 2, "deal_id": 999999,
        "requested_by_user_id": 1, "target": "TEST_NEWBASE",
        "created_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    code, result = send(CREATE_PATH, payload)
    assert code == 202 and result["status"] == "QUEUED"
    job = send(CLAIM_PATH, {"worker_id": "SRV", "max_jobs": 1}, role="srv")[1]["job"]
    assert job and job["request_id"] == payload["request_id"] and job["deal_id"] == 999999
    path = CREATE_PATH + "/" + payload["request_id"] + "/ack"
    assert send(path, {"lease_token": job["lease_token"]}, role="srv")[1]["status"] == "RECEIVED_BY_SRV"
    status_path = CREATE_PATH + "/" + payload["request_id"]
    assert send(status_path)[1]["status"] == "RECEIVED_BY_SRV"
    payload["request_id"] = str(uuid.uuid4())
    code, duplicate = send(CREATE_PATH, payload)
    assert code == 200 and duplicate["duplicate"]
    with sqlite3.connect(settings["B24_GW_DB"]) as db:
        assert db.execute("SELECT COUNT(*) FROM commands").fetchone()[0] == 1
    print("B24_GATEWAY_STAGING_SMOKE")
    print("INVALID_SIGNATURE_DENIED=YES")
    print("SRV_AUTH_ENFORCED=YES")
    print("NO_PUBLIC_HEALTH=YES")
    print("SIGNED_QUEUE_CREATE=PASS")
    print("SRV_CLAIM_ACK=PASS")
    print("IDEMPOTENT_DEAL=PASS")
    print("STATUS_READBACK=PASS")
    print("SYNTHETIC_DEAL_ONLY=YES")
    print("ONEC_CALLS=0")
    print("CRM_CALLS=0")
    print("RESULT=PASS")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("B24_GATEWAY_STAGING_SMOKE")
        print("ERROR_TYPE=" + type(exc).__name__)
        print("RESULT=FAIL")
        raise SystemExit(1)
