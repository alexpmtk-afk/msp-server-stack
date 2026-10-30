"""Credential-safe, fixed-endpoint HTTP read transport for the marketplace archive.

This module makes NO requests on import. A caller must explicitly construct
the transport with a locally protected credential file and run a read action.
It deliberately does not permit arbitrary URLs or marketplace mutations.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import stat
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .archive import CABINETS
from .quota import SharedQuota, QuotaBusy
from .providers import (
    ProviderError, Request, WB_LIST, WB_DETAIL, OZON_FINAL, OZON_FBO, OZON_FBS, OZON_ACCRUAL,
)

MAX_RESPONSE_BYTES = 128 * 1024 * 1024
# Local file gate deliberately exceeds the Redis safety bucket (65 sec).
# Otherwise a fast first response makes the next request self-block at 63 sec.
WB_WAIT_SECONDS = 66.0
OZON_WAIT_SECONDS = 5.0
ALLOWED_OZON = frozenset({OZON_FINAL, OZON_FBO, OZON_FBS, OZON_ACCRUAL})


def load_credentials(path: Path):
    """Read 0600-or-0640 local JSON; refuse symlinks, world/group access.

    Format: {cabinet_id: {"token": "..."} or {"client_id": "...", "api_key": "..."}}.
    File itself and its parent are controlled by server provisioning.
    Never return credentials to the CLI output or logs.
    """
    path = Path(path)
    if path.is_symlink():
        raise ProviderError("credential file must not be a symlink")
    try:
        status = path.stat()
    except OSError:
        raise ProviderError("credential file unavailable") from None
    if not stat.S_ISREG(status.st_mode) or status.st_mode & 0o037:
        raise ProviderError("credential file permissions unsafe (requires 0600 or private-group 0640)")
    if status.st_uid not in (0, os.geteuid()):
        raise ProviderError("credential file owner not trusted")
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError, UnicodeError):
        raise ProviderError("invalid credential file") from None
    if not isinstance(data, dict):
        raise ProviderError("invalid credential map")
    return data


def credential_status(path: Path):
    """Names only; no token values or portions of Client-Id."""
    values = load_credentials(path)
    result = {}
    for marketplace, cabinets in CABINETS.items():
        for cabinet in cabinets:
            cred = values.get(cabinet)
            required = ("token",) if marketplace == "wb" else ("client_id", "api_key")
            result[cabinet] = bool(
                isinstance(cred, dict)
                and all(isinstance(cred.get(k), str) and cred[k].strip() for k in required)
            )
    return result


def _endpoint(request: Request):
    if request.marketplace == "wb":
        if request.path == WB_LIST or (
            request.path.startswith(WB_DETAIL)
            and re.fullmatch(r"[0-9]+", request.path[len(WB_DETAIL):])
        ):
            return "https://finance-api.wildberries.ru" + request.path
    elif request.marketplace == "ozon" and request.path in ALLOWED_OZON:
        return "https://api-seller.ozon.ru" + request.path
    raise ProviderError("endpoint not permitted")


def _headers(marketplace: str, credentials: dict[str, Any]):
    if marketplace == "wb":
        token = credentials.get("token")
        if not isinstance(token, str) or not token.strip():
            raise ProviderError("WB token missing")
        return {"Authorization": token, "Content-Type": "application/json"}
    if marketplace == "ozon":
        client_id, api_key = credentials.get("client_id"), credentials.get("api_key")
        if not isinstance(client_id, str) or not client_id.strip() or not isinstance(api_key, str) or not api_key.strip():
            raise ProviderError("Ozon credential pair missing")
        return {"Client-Id": client_id, "Api-Key": api_key, "Content-Type": "application/json"}
    raise ProviderError("unsupported marketplace")


@contextmanager
def _rate_gate(root: Path, marketplace: str, cabinet: str):
    """Persistent per-cabinet quota reservation, including across processes."""
    rate_dir = Path(root) / ".rate-limits"
    rate_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    file = rate_dir / (marketplace + "_" + cabinet + ".json")
    with file.open("a+b") as handle:
        os.fchmod(handle.fileno(), 0o600)
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            handle.seek(0)
            try:
                last = float(json.loads(handle.read().decode("ascii") or "{}").get("last_attempt_epoch", 0))
            except (ValueError, TypeError):
                raise ProviderError("rate-limit state damaged; manual review required") from None
            delay = WB_WAIT_SECONDS if marketplace == "wb" else OZON_WAIT_SECONDS
            remaining = max(0.0, last + delay - time.time())
            if remaining > delay:
                raise ProviderError("invalid rate-limit clock; manual review required")
            if remaining:
                time.sleep(remaining)
            now = time.time()
            handle.seek(0)
            handle.truncate()
            handle.write(json.dumps({"last_attempt_epoch": now}).encode("ascii"))
            handle.flush()
            os.fsync(handle.fileno())
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ReadOnlyHTTP:
    def __init__(self, *, cabinet: str, credentials_file: Path, state_root: Path):
        self.cabinet = cabinet
        self.marketplace = next((market for market, cabinets in CABINETS.items() if cabinet in cabinets), None)
        if self.marketplace is None:
            raise ProviderError("unknown cabinet")
        credentials = load_credentials(credentials_file).get(cabinet)
        if not isinstance(credentials, dict):
            raise ProviderError("cabinet not configured")
        self.headers = _headers(self.marketplace, credentials)
        self.quota = SharedQuota(self.marketplace, credentials)
        self.state_root = Path(state_root)
        self.opener = urllib.request.build_opener(_NoRedirect())

    def __call__(self, request: Request):
        if request.marketplace != self.marketplace:
            raise ProviderError("marketplace/cabinet mismatch")
        # Fail closed unless the operator has verified deployment's common
        # Redis namespace. All pages and attempts reserve shared quota first.
        self.quota._approved_url()
        url = _endpoint(request)
        body = json.dumps(request.body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(body) > 20000:
            raise ProviderError("request too large")
        req = urllib.request.Request(url, data=body, headers=self.headers, method="POST")
        with _rate_gate(self.state_root, self.marketplace, self.cabinet):
            rules = self.quota.reserve(request)
            try:
                with self.opener.open(req, timeout=60) as response:
                    status = response.status
                    if status == 204:
                        return 204, None
                    if status != 200:
                        return status, None
                    # Bound memory use, and fail before JSON decoding if over the limit.
                    raw = response.read(MAX_RESPONSE_BYTES + 1)
                    if len(raw) > MAX_RESPONSE_BYTES:
                        raise ProviderError("provider response exceeds size limit")
                    try:
                        return status, json.loads(raw.decode("utf-8"))
                    except (ValueError, UnicodeError):
                        raise ProviderError("provider returned invalid JSON") from None
            except urllib.error.HTTPError as e:
                # Record a global shared provider cooldown; do not retry or
                # expose response body, headers or the request containing keys.
                if int(e.code) == 429:
                    delay = self.quota.cooldown(rules, e.headers)
                    raise QuotaBusy(delay, "provider rate limit after shared cooldown") from None
                return int(e.code), None
            except (urllib.error.URLError, TimeoutError, OSError):
                raise ProviderError("provider transport unavailable; retry with saved cursor") from None
