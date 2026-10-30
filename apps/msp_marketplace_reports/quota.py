"""Fail-closed adapter to the legacy marketplace MCP's atomic shared Redis queue.

This is a guarded implementation stage. Do NOT enable on VPS until the Redis
namespace, endpoint quota scopes and concurrency with existing clients have
been checked. No request is sent when the gate cannot prove a reservation.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Mapping

from .providers import ProviderError, Request, WB_LIST, WB_DETAIL
from .shared_rate_limit import (
    GlobalRateController, RateLimitUnavailable, RateRule, build_rules,
    redis_url_from_env, key_prefix,
)

# Deliberately conservative *additional* bucket, not a claim about the
# provider's published maximum. Keep the original contract's 1 req/min
# bucket for Redis key compatibility; do not replace it with 1 req/65s.
WB_CONTRACT = "1 req/min"
WB_EXTRA_INTERVAL = 65.0
WB_HOST = "finance-api.wildberries.ru"
# Same public Redis catalog identity as Marketplace MCP legacy finance group.
# This keeps the old 60-second group and adds a stricter local safety rule;
# it does NOT prove that the deployed clients share the same Redis DB.
WB_LEGACY_FINANCE_SCOPE = "finance"
# Ozon official general limit: 50/s per Client-Id across methods. Exact
# per-method caps must be verified before the explicit runtime approval.
OZON_FINANCE_EXTRA_INTERVAL = 5.0
OZON_FINANCE_HOST = "api-seller.ozon.ru"
OZON_REQUIRED_METHOD_APPROVAL = "MSP_REPORTS_OZON_FINANCE_METHODS_VERIFIED"
OZON_APPROVED_PATHS = frozenset((
    "/v1/finance/realization/posting",
    "/v3/posting/fbo/list",
    "/v4/posting/fbs/list",
    "/v1/finance/accrual/by-day",
))
REQUIRED_APPROVAL_ENV = "MSP_REPORTS_SHARED_QUEUE_VERIFIED"


def stable_owner_key(marketplace: str, credentials: Mapping[str, str]) -> str:
    """Use the exact account-derived hash as the legacy core/client.py.

    Never use token hash or display name as the quota key: rotations and
    multiple tokens of one seller must consume the same shared quota.
    """
    if marketplace == "wb":
        try:
            token = credentials["token"]
            parts = token.split(".")
            if len(parts) != 3:
                raise ValueError("missing JWT segments")
            payload = parts[1] + "=" * (-len(parts[1]) % 4)
            claims = json.loads(base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8"))
            sid = claims.get("sid")
            if not isinstance(sid, (str, int)) or not str(sid):
                raise ValueError("missing seller id")
            raw = "wb:seller:" + str(sid)
        except (KeyError, TypeError, ValueError, UnicodeError) as exc:
            raise ProviderError("WB stable seller quota identity unavailable") from None
    elif marketplace == "ozon":
        cid = credentials.get("client_id")
        if not isinstance(cid, str) or not cid.isascii() or not cid.isdecimal():
            raise ProviderError("Ozon Client-Id quota identity unavailable")
        raw = "ozon:client:" + cid
    else:
        raise ProviderError("unknown marketplace for quota identity")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def request_rules(marketplace: str, credentials: Mapping[str, str], request: Request):
    """Return rules only for independently reviewed finance endpoints."""
    if request.marketplace != marketplace:
        raise ProviderError("marketplace quota mismatch")
    owner = stable_owner_key(marketplace, credentials)
    if marketplace == "wb" and (request.path == WB_LIST or
                                (request.path.startswith(WB_DETAIL) and
                                 request.path[len(WB_DETAIL):].isdecimal())):
        # Finance-list and finance-detail consume one conservative shared
        # finance bucket across these two endpoints and all valid tokens for
        # the same WB seller, plus a separate 65-second buffer bucket.
        rules = build_rules(service="wb", cabinet_key=owner,
                            host=WB_HOST, operation_id="wb_finance",
                            scope=WB_LEGACY_FINANCE_SCOPE, catalog_rate_limit=WB_CONTRACT)
        rules.append(RateRule(key_prefix("wb", owner) + ":msp-finance-safety", WB_EXTRA_INTERVAL))
        return rules
    if marketplace == "ozon" and request.path in OZON_APPROVED_PATHS:
        # Exact method schema, permission and any method-specific rate limit
        # are NOT established merely by the 50RPS general Client-Id quota.
        # Disabled until a human verifies the exact current four contracts.
        if os.environ.get(OZON_REQUIRED_METHOD_APPROVAL) != "YES":
            raise ProviderError("Ozon finance method-specific approval not verified")
        rules = build_rules(service="ozon", cabinet_key=owner,
                            host=OZON_FINANCE_HOST,
                            operation_id="ozon_finance",
                            scope="finance")
        rules.append(RateRule(
            key_prefix("ozon", owner) + ":msp-finance-safety",
            OZON_FINANCE_EXTRA_INTERVAL))
        return rules
    raise ProviderError("finance endpoint rate contract not yet approved")


def _parse_wait(value: str | None):
    if not value:
        return None
    try:
        n = float(value)
        return min(86400.0, max(0.0, n)) if math.isfinite(n) else None
    except (TypeError, ValueError):
        pass
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return min(86400.0, max(0.0, (dt - datetime.now(timezone.utc)).total_seconds()))
    except (TypeError, ValueError, OverflowError, IndexError):
        return None


def retry_delay(headers, rules):
    values = [_parse_wait(headers.get("Retry-After")),
              _parse_wait(headers.get("X-Ratelimit-Retry"))]
    positive = [v for v in values if v is not None]
    default = max([60.0, *(r.interval_seconds for r in rules)])
    # When the provider supplies an explicit wait, do not undercut it; use
    # at least the known safe bucket window as the default.
    return min(86400.0, max([default, *positive]))


async def _with_controller(redis_url: str, work):
    # Fresh per-call controller: urllib transport is synchronous while the
    # canonical queue API is async. Close the Redis connection and event loop.
    ctl = GlobalRateController(redis_url=redis_url)
    try:
        return await work(ctl)
    finally:
        if ctl._redis is not None:
            await ctl._redis.aclose()


class SharedQuota:
    def __init__(self, marketplace: str, credentials: Mapping[str, str]):
        self.marketplace = marketplace
        self.credentials = credentials

    def _approved_url(self):
        if os.environ.get(REQUIRED_APPROVAL_ENV) != "YES":
            raise ProviderError("API DOWNLOAD BLOCKED: shared Redis queue deployment unverified")
        url = redis_url_from_env()
        if not url:
            raise ProviderError("API DOWNLOAD BLOCKED: shared Redis unavailable")
        if not url.startswith(("redis://", "rediss://")):
            raise ProviderError("API DOWNLOAD BLOCKED: unsafe shared Redis configuration")
        return url

    def reserve(self, request: Request):
        url = self._approved_url()
        rules = request_rules(self.marketplace, self.credentials, request)

        async def execute(ctl):
            return await ctl.try_acquire(rules)

        try:
            granted, wait = asyncio.run(_with_controller(url, execute))
        except (RateLimitUnavailable, OSError, RuntimeError):
            raise ProviderError("API DOWNLOAD BLOCKED: shared queue reservation failed") from None
        if not granted:
            raise ProviderError("API DOWNLOAD PAUSED: shared quota busy; retry later")
        return rules

    def cooldown(self, rules, headers):
        url = self._approved_url()
        delay = retry_delay(headers, rules)

        async def execute(ctl):
            if self.marketplace == "ozon":
                # The legacy controller intentionally prefers method/specific
                # rules when both kinds are passed to defer(). Call it twice:
                # first the shared Client-Id global key (old clients observe
                # the 429), then our additional local safety key.
                global_rules = [r for r in rules if r.key.endswith(":global")]
                safety_rules = [r for r in rules if r.key.endswith(":msp-finance-safety")]
                if len(global_rules) != 1 or len(safety_rules) != 1 or len(rules) != 2:
                    raise RateLimitUnavailable("Ozon finance cooldown rules invalid")
                await ctl.defer(global_rules, delay)
                await ctl.defer(safety_rules, delay)
            else:
                await ctl.defer(rules, delay)

        try:
            asyncio.run(_with_controller(url, execute))
        except (RateLimitUnavailable, OSError, RuntimeError):
            raise ProviderError("API DOWNLOAD BLOCKED: shared cooldown storage failed") from None
