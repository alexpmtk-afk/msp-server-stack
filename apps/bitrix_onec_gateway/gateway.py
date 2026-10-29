"""Isolated Bitrix24 -> SRV command transport, PHASE B ONLY. No 1C integration."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CREATE_PATH = "/api/v1/onec-order-requests"
CLAIM_PATH = CREATE_PATH + "/claim"
ACK_RE = re.compile(r"^/api/v1/onec-order-requests/([0-9a-f-]{36})/ack$")
STATUS_RE = re.compile(r"^/api/v1/onec-order-requests/([0-9a-f-]{36})$")
NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{20,90}$")
SIGNATURE_RE = re.compile(r"^[0-9a-f]{64}$")
PORTAL = "b24-uwmjda.bitrix24.ru"
MAX_BODY = 2048
LEASE_SECONDS = 120
MAX_ATTEMPTS = 3


def make_config(environ=None):
    e = os.environ if environ is None else environ
    app_key = e.get("B24_GW_APP_HMAC_KEY", "")
    srv_key = e.get("B24_GW_SRV_BEARER", "")
    member = e.get("B24_GW_MEMBER_ID", "")
    db_path = e.get("B24_GW_DB", "")
    if min(len(app_key), len(srv_key)) < 48 or app_key == srv_key:
        raise ValueError("Independent strong application and SRV keys required")
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", member):
        raise ValueError("Verified portal member ID required")
    if not db_path or not Path(db_path).is_absolute() or not Path(db_path).parent.is_dir():
        raise ValueError("Existing absolute database parent directory required")
    return {"app_key": app_key.encode("utf-8"), "srv_key": srv_key,
            "member": member, "db": db_path}


def connect(db_path):
    db = sqlite3.connect(db_path, timeout=8, isolation_level=None)
    db.execute("PRAGMA busy_timeout=8000")
    db.execute("PRAGMA synchronous=FULL")
    db.row_factory = sqlite3.Row
    return db


def initialize(db_path):
    db = connect(db_path)
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS commands (
                request_id TEXT PRIMARY KEY,
                logical_key TEXT NOT NULL UNIQUE,
                body_hash TEXT NOT NULL,
                portal TEXT NOT NULL,
                portal_member_id TEXT NOT NULL,
                deal_id INTEGER NOT NULL,
                requested_by_user_id INTEGER NOT NULL,
                created_at_utc TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN (
                    'QUEUED','LEASED','RECEIVED_BY_SRV','FAILED_DELIVERY')),
                attempts INTEGER NOT NULL DEFAULT 0,
                lease_hash TEXT,
                lease_until INTEGER,
                received_at INTEGER
            );
            CREATE TABLE IF NOT EXISTS auth_nonces (
                nonce TEXT PRIMARY KEY, received_at INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS commands_poll_idx
              ON commands(status, created_at_utc);
        """)
    finally:
        db.close()


def canonical_signature(method, path, timestamp, nonce, body):
    return "\n".join([method, path, timestamp, nonce,
                      hashlib.sha256(body).hexdigest()]).encode("ascii")


def validate_command(body, member):
    if not isinstance(body, dict) or set(body) != {
        "schema_version", "request_id", "action", "portal",
        "portal_member_id", "entity_type_id", "deal_id",
        "requested_by_user_id", "target", "created_at_utc"
    }:
        raise ValueError("Invalid schema")
    if type(body["schema_version"]) is not int or body["schema_version"] != 1:
        raise ValueError("Invalid version")
    if body["action"] != "CUSTOMER_ORDER_REQUEST" or body["target"] != "TEST_NEWBASE":
        raise ValueError("Invalid action or target")
    if body["portal"] != PORTAL or body["portal_member_id"] != member:
        raise ValueError("Invalid portal")
    if type(body["entity_type_id"]) is not int or body["entity_type_id"] != 2:
        raise ValueError("Not a deal")
    if any(type(body[k]) is not int or not 1 <= body[k] <= 2147483647
           for k in ("deal_id", "requested_by_user_id")):
        raise ValueError("Invalid identifiers")
    rid = str(uuid.UUID(body["request_id"]))
    if rid != body["request_id"] or rid == str(uuid.UUID(int=0)):
        raise ValueError("Invalid request id")
    created = datetime.strptime(body["created_at_utc"], "%Y-%m-%dT%H:%M:%SZ")
    age = abs(time.time() - created.replace(tzinfo=timezone.utc).timestamp())
    if age > 300:
        raise ValueError("Stale command")
    return body


def handler_factory(cfg):
    class Handler(BaseHTTPRequestHandler):
        server_version = "OrderCommandGateway"
        sys_version = ""

        def log_message(self, *args):
            pass  # No URLs, tokens, user identifiers or payloads in logs.

        def answer(self, status, payload):
            data = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def read_body(self):
            if self.headers.get("Transfer-Encoding"):
                raise ValueError("Transfer encoding forbidden")
            size = self.headers.get("Content-Length", "")
            if not size.isdecimal() or not 0 < int(size) <= MAX_BODY:
                raise ValueError("Invalid content length")
            if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
                raise ValueError("JSON required")
            return self.rfile.read(int(size))

        def srv_auth(self):
            value = self.headers.get("Authorization", "")
            expected = "Bearer " + cfg["srv_key"]
            return hmac.compare_digest(value, expected)

        def app_auth(self, method, path, body):
            if self.headers.get("Authorization"):
                return False
            stamp = self.headers.get("X-B24-Timestamp", "")
            nonce = self.headers.get("X-B24-Nonce", "")
            signature = self.headers.get("X-B24-Signature", "")
            if not stamp.isdecimal() or not NONCE_RE.fullmatch(nonce) or not SIGNATURE_RE.fullmatch(signature):
                return False
            if abs(time.time() - int(stamp)) > 300:
                return False
            msg = canonical_signature(method, path, stamp, nonce, body)
            good = hmac.new(cfg["app_key"], msg, hashlib.sha256).hexdigest()
            return hmac.compare_digest(good, signature)

        def record_nonce(self, db, nonce):
            db.execute("DELETE FROM auth_nonces WHERE received_at < ?", (int(time.time()) - 600,))
            db.execute("INSERT INTO auth_nonces(nonce,received_at) VALUES (?,?)",
                       (nonce, int(time.time())))

        def do_POST(self):
            path = self.path
            if path != CREATE_PATH and path != CLAIM_PATH and not ACK_RE.fullmatch(path):
                return self.answer(404, {"error": "NOT_FOUND"})
            try:
                raw = self.read_body()
            except (ValueError, OSError):
                return self.answer(400, {"error": "INVALID_REQUEST"})
            if path == CREATE_PATH:
                if not self.app_auth("POST", path, raw):
                    return self.answer(401, {"error": "UNAUTHORIZED"})
            elif not self.srv_auth():
                return self.answer(401, {"error": "UNAUTHORIZED"})
            try:
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    raise ValueError("Object required")
            except (ValueError, UnicodeError):
                return self.answer(400, {"error": "INVALID_JSON"})
            try:
                if path == CREATE_PATH:
                    return self.create_command(payload, raw)
                if path == CLAIM_PATH:
                    return self.claim_command(payload)
                return self.ack_command(ACK_RE.fullmatch(path).group(1), payload)
            except (ValueError, KeyError, TypeError):
                return self.answer(400, {"error": "INVALID_REQUEST"})
            except sqlite3.IntegrityError:
                return self.answer(409, {"error": "REPLAY_OR_CONFLICT"})
            except sqlite3.Error:
                return self.answer(503, {"error": "STORAGE_UNAVAILABLE"})

        def create_command(self, payload, raw):
            cmd = validate_command(payload, cfg["member"])
            nonce = self.headers["X-B24-Nonce"]
            digest = hashlib.sha256(raw).hexdigest()
            logical_key = "|".join([PORTAL, cfg["member"], "2",
                                    str(cmd["deal_id"]), cmd["action"], cmd["target"]])
            db = connect(cfg["db"])
            try:
                db.execute("BEGIN IMMEDIATE")
                self.record_nonce(db, nonce)
                old = db.execute("SELECT request_id,body_hash FROM commands WHERE request_id=?",
                                 (cmd["request_id"],)).fetchone()
                if old:
                    if old["body_hash"] != digest:
                        db.rollback()
                        return self.answer(409, {"error": "REQUEST_ID_CONFLICT"})
                    db.commit()
                    return self.answer(200, {"request_id": old["request_id"],
                                             "status": "EXISTING", "duplicate": True})
                old = db.execute("SELECT request_id FROM commands WHERE logical_key=?",
                                 (logical_key,)).fetchone()
                if old:
                    db.commit()
                    return self.answer(200, {"request_id": old["request_id"],
                                             "status": "EXISTING", "duplicate": True})
                db.execute("""INSERT INTO commands(
                    request_id,logical_key,body_hash,portal,portal_member_id,deal_id,
                    requested_by_user_id,created_at_utc,status)
                    VALUES (?,?,?,?,?,?,?,?, 'QUEUED')""",
                    (cmd["request_id"], logical_key, digest, PORTAL, cfg["member"],
                     cmd["deal_id"], cmd["requested_by_user_id"], cmd["created_at_utc"]))
                db.commit()
                return self.answer(202, {"request_id": cmd["request_id"],
                                         "status": "QUEUED", "duplicate": False})
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

        def claim_command(self, payload):
            if set(payload) != {"worker_id", "max_jobs"} or payload["worker_id"] != "SRV" or type(payload["max_jobs"]) is not int or payload["max_jobs"] != 1:
                raise ValueError("Invalid claim parameters")
            now = int(time.time())
            db = connect(cfg["db"])
            try:
                db.execute("BEGIN IMMEDIATE")
                db.execute("""UPDATE commands SET status='FAILED_DELIVERY',lease_until=NULL
                              WHERE status='LEASED' AND lease_until<=? AND attempts>=?""",
                           (now, MAX_ATTEMPTS))
                db.execute("""UPDATE commands SET status='QUEUED',lease_hash=NULL,lease_until=NULL
                              WHERE status='LEASED' AND lease_until<=? AND attempts<?""",
                           (now, MAX_ATTEMPTS))
                row = db.execute("""SELECT request_id,deal_id,portal,portal_member_id
                                     FROM commands WHERE status='QUEUED'
                                     ORDER BY created_at_utc,request_id LIMIT 1""").fetchone()
                if not row:
                    db.commit()
                    return self.answer(200, {"job": None})
                lease = secrets.token_urlsafe(32)
                db.execute("""UPDATE commands SET status='LEASED',attempts=attempts+1,
                              lease_hash=?,lease_until=? WHERE request_id=?""",
                           (hashlib.sha256(lease.encode()).hexdigest(),
                            now + LEASE_SECONDS, row["request_id"]))
                db.commit()
                return self.answer(200, {"job": {
                    "request_id": row["request_id"], "deal_id": row["deal_id"],
                    "portal": row["portal"], "portal_member_id": row["portal_member_id"],
                    "action": "CUSTOMER_ORDER_REQUEST", "target": "TEST_NEWBASE",
                    "lease_token": lease, "lease_until_epoch": now + LEASE_SECONDS}})
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

        def ack_command(self, request_id, payload):
            if set(payload) != {"lease_token"} or not isinstance(payload["lease_token"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", payload["lease_token"]):
                raise ValueError("Invalid acknowledgement")
            hash_value = hashlib.sha256(payload["lease_token"].encode()).hexdigest()
            db = connect(cfg["db"])
            try:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT status,lease_hash,lease_until FROM commands WHERE request_id=?",
                                 (request_id,)).fetchone()
                if not row:
                    db.rollback()
                    return self.answer(404, {"error": "NOT_FOUND"})
                if not hmac.compare_digest(row["lease_hash"] or "", hash_value):
                    db.rollback()
                    return self.answer(409, {"error": "INVALID_LEASE"})
                if row["status"] == "RECEIVED_BY_SRV":
                    db.commit()
                    return self.answer(200, {"status": "RECEIVED_BY_SRV"})
                if row["status"] != "LEASED" or row["lease_until"] < int(time.time()):
                    db.rollback()
                    return self.answer(409, {"error": "LEASE_EXPIRED"})
                db.execute("""UPDATE commands SET status='RECEIVED_BY_SRV',received_at=?,
                              lease_until=NULL WHERE request_id=?""",
                           (int(time.time()), request_id))
                db.commit()
                return self.answer(200, {"status": "RECEIVED_BY_SRV"})
            except Exception:
                db.rollback()
                raise
            finally:
                db.close()

        def do_GET(self):
            match = STATUS_RE.fullmatch(self.path)
            if not match:
                return self.answer(404, {"error": "NOT_FOUND"})
            if not self.app_auth("GET", self.path, b""):
                return self.answer(401, {"error": "UNAUTHORIZED"})
            db = connect(cfg["db"])
            try:
                db.execute("BEGIN IMMEDIATE")
                self.record_nonce(db, self.headers["X-B24-Nonce"])
                row = db.execute("SELECT status,attempts FROM commands WHERE request_id=?",
                                 (match.group(1),)).fetchone()
                db.commit()
                return self.answer(200, {"request_id": match.group(1),
                                         "status": row["status"], "attempts": row["attempts"]}) if row else self.answer(404, {"error": "NOT_FOUND"})
            except sqlite3.IntegrityError:
                db.rollback()
                return self.answer(409, {"error": "REPLAY"})
            except sqlite3.Error:
                db.rollback()
                return self.answer(503, {"error": "STORAGE_UNAVAILABLE"})
            finally:
                db.close()

    return Handler


def main():
    cfg = make_config()
    os.umask(0o077)
    initialize(cfg["db"])
    port = int(os.environ.get("B24_GW_PORT", "9794"))
    if not 1024 <= port <= 65535:
        raise ValueError("Invalid port")
    server = ThreadingHTTPServer(("127.0.0.1", port), handler_factory(cfg))
    server.daemon_threads = True
    print("BITRIX_ONEC_PHASE_B=LISTEN_LOOPBACK_ONLY", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
