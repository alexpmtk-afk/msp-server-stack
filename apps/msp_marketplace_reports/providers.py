"""Strict READ-ONLY request planners and parsers for WB/Ozon archive feeds.

No authentication, network I/O, storage or automatic scheduling in this module.
The caller provides a bounded, rate-limited send(Request)->(status, JSON) function.
Invalid/partial provider replies raise rather than being recorded as empty coverage.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo


WB_LIST = "/api/finance/v1/sales-reports/list"
WB_DETAIL = "/api/finance/v1/sales-reports/detailed/"
OZON_FINAL = "/v1/finance/realization/posting"
OZON_FBO = "/v3/posting/fbo/list"
OZON_FBS = "/v4/posting/fbs/list"
OZON_ACCRUAL = "/v1/finance/accrual/by-day"
Moscow = ZoneInfo("Europe/Moscow")
MAX_PAGES = 200
WB_PAGE = 1000
OZON_PAGE = 100


@dataclass(frozen=True)
class Request:
    marketplace: str
    path: str
    body: dict[str, Any]


class ProviderError(RuntimeError):
    """Safe, content-free failure. Never include response body, token, or headers."""


Send = Callable[[Request], tuple[int, Any]]


def _reply(send: Send, request: Request):
    code, payload = send(request)
    if code == 429:
        raise ProviderError("provider rate limit: retry after verified provider interval")
    if code == 401 or code == 403:
        raise ProviderError("provider rejected credentials or scope")
    if code != 200:
        raise ProviderError("provider returned HTTP %s for %s" % (code, request.path))
    return payload


def _list(value, label: str):
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ProviderError("invalid provider item list: " + label)
    return value


def _obj(value, label: str):
    if not isinstance(value, dict):
        raise ProviderError("invalid provider object: " + label)
    return value


def _positive_id(value: Any, label: str) -> int:
    try:
        number = int(str(value))
        if number <= 0:
            raise ValueError
        return number
    except (TypeError, ValueError):
        raise ProviderError("invalid provider identifier: " + label) from None


def _year(year: int, today: date):
    if not (2025 <= year <= today.year):
        raise ValueError("requested year out of archive range")


def _moscow_bounds(start: date, end: date):
    if start > end:
        raise ValueError("invalid date range")
    since = datetime.combine(start, time.min, tzinfo=Moscow).astimezone(timezone.utc)
    until = datetime.combine(end + timedelta(days=1), time.min, tzinfo=Moscow).astimezone(timezone.utc) - timedelta(seconds=1)
    return since.strftime("%Y-%m-%dT%H:%M:%SZ"), until.strftime("%Y-%m-%dT%H:%M:%SZ")


def wb_discover_all(send: Send, year: int, today: date | None = None):
    """Return every reportType=1 or 2 fragment discovered for the calendar year.

    Reports may span a month/year boundary. The physical fragment, not just the
    weekly bucket, is a separate fetch unit.
    """
    now = today or datetime.now(Moscow).date()
    _year(year, now)
    end = min(date(year, 12, 31), now)
    rows: dict[int, dict[str, Any]] = {}
    offset = 0
    for _ in range(MAX_PAGES):
        body = {"dateFrom": date(year, 1, 1).isoformat(),
                "dateTo": end.isoformat(), "period": "weekly",
                "limit": WB_PAGE, "offset": offset}
        page = _list(_reply(send, Request("wb", WB_LIST, body)), "WB list")
        for item in page:
            report_id = _positive_id(item.get("reportId"), "reportId")
            report_type = item.get("reportType")
            try:
                report_type = int(report_type)
            except (ValueError, TypeError):
                raise ProviderError("WB report type missing or malformed") from None
            if report_type not in (1, 2):
                raise ProviderError("unsupported WB report type")
            item = dict(item, reportType=report_type)
            for k in ("dateFrom", "dateTo"):
                try:
                    date.fromisoformat(str(item[k])[:10])
                except (KeyError, TypeError, ValueError):
                    raise ProviderError("WB report period missing or malformed") from None
            if report_id in rows and rows[report_id] != item:
                raise ProviderError("WB reportId duplicated with conflicting metadata")
            rows[report_id] = item
        if len(page) < WB_PAGE:
            return sorted(rows.values(), key=lambda r: (str(r["dateFrom"]), int(r["reportId"])))
        offset += len(page)
    raise ProviderError("WB report discovery page limit reached")


def wb_discover_main(send: Send, year: int, today: date | None = None):
    """Compatibility filter. New ingestion must use wb_discover_all to retain buyouts."""
    return [row for row in wb_discover_all(send, year, today) if row["reportType"] == 1]


def wb_detail(send: Send, report_id: int, report_type: int = 1):
    """Follow rrdId until explicit 204; verify the listed report type."""
    if report_type not in (1, 2):
        raise ProviderError("unsupported WB report type")
    report_id = _positive_id(report_id, "reportId")
    all_rows = []
    current = 0
    seen = set()
    for _ in range(MAX_PAGES):
        req = Request("wb", WB_DETAIL + str(report_id), {"limit": 10000, "rrdId": current})
        status, payload = send(req)
        if status == 204:
            return all_rows
        if status != 200:
            if status == 429:
                raise ProviderError("provider rate limit: resume current rrdId")
            raise ProviderError("WB detail HTTP %s" % status)
        page = _list(payload, "WB details")
        if not page:
            raise ProviderError("WB detail returned 200 with empty page; 204 required")
        for item in page:
            if _positive_id(item.get("reportId", report_id), "reportId") != report_id:
                raise ProviderError("foreign WB reportId in detail")
            if item.get("reportType") is not None:
                try:
                    actual_type = int(item["reportType"])
                except (TypeError, ValueError):
                    raise ProviderError("invalid WB detail reportType") from None
                if actual_type != report_type:
                    raise ProviderError("WB detail reportType mismatches list")
            cursor = _positive_id(item.get("rrdId"), "rrdId")
            key = (report_id, cursor)
            if key in seen:
                raise ProviderError("duplicate WB detail stable key")
            seen.add(key)
            all_rows.append(item)
        next_cursor = _positive_id(page[-1].get("rrdId"), "rrdId")
        if next_cursor <= current:
            raise ProviderError("WB detail rrdId did not advance")
        current = next_cursor
    raise ProviderError("WB detail page limit reached; incomplete report")


def ozon_final_month(send: Send, year: int, month: int):
    """Read one closed Ozon realization month; row_number is provider-owned."""
    if not (2025 <= year <= 2100 and 1 <= month <= 12):
        raise ValueError("invalid Ozon month")
    payload = _obj(_reply(send, Request("ozon", OZON_FINAL, {"year": year, "month": month})), "Ozon realization")
    # The accepted historical adapter uses top-level 'rows'.
    rows = _list(payload.get("rows"), "Ozon FINAL rows")
    unique = set()
    enriched = []
    for row in rows:
        key = _positive_id(row.get("row_number", row.get("rowNumber")), "row_number")
        if key in unique:
            raise ProviderError("duplicate Ozon FINAL row number")
        unique.add(key)
        copy = dict(row)
        copy["report_year"] = year
        copy["report_month"] = "%04d-%02d" % (year, month)
        copy["row_number"] = key
        enriched.append(copy)
    return enriched


def ozon_current_postings(send: Send, fulfillment: str, start: date, end: date):
    if fulfillment not in ("fbo", "fbs"):
        raise ValueError("fulfillment must be fbo or fbs")
    since, until = _moscow_bounds(start, end)
    path = OZON_FBO if fulfillment == "fbo" else OZON_FBS
    cursor = ""
    seen_cursors = set()
    result = {}
    for _ in range(MAX_PAGES):
        body = {"cursor": cursor, "filter": {"since": since, "to": until},
                "limit": OZON_PAGE, "with": {"analytics_data": True,
                                          "financial_data": True, "legal_info": True}}
        payload = _obj(_reply(send, Request("ozon", path, body)), "Ozon postings")
        page = _list(payload.get("postings"), "Ozon postings")
        for row in page:
            number = str(row.get("posting_number") or "").strip()
            if not number or number in result:
                raise ProviderError("missing/duplicate Ozon posting_number")
            result[number] = row
        has_next = payload.get("has_next")
        if has_next is False:
            return list(result.values())
        if has_next is not True:
            raise ProviderError("Ozon has_next is missing or malformed")
        nxt = payload.get("cursor")
        if not isinstance(nxt, str) or not nxt or nxt == cursor or nxt in seen_cursors:
            raise ProviderError("Ozon posting cursor did not advance")
        seen_cursors.add(nxt)
        cursor = nxt
    raise ProviderError("Ozon posting page limit reached; incomplete month")


def ozon_accrual_day(send: Send, target: date):
    cursor = ""
    seen_cursors = set()
    result = {}
    for _ in range(MAX_PAGES):
        payload = _obj(_reply(send, Request("ozon", OZON_ACCRUAL,
                                           {"date": target.isoformat(), "last_id": cursor})), "Ozon accruals")
        page = _list(payload.get("accruals"), "Ozon accruals")
        for row in page:
            key = str(row.get("accrual_id") or "").strip()
            if not key or key in result:
                raise ProviderError("missing/duplicate Ozon accrual_id")
            result[key] = row
        next_cursor = payload.get("last_id")
        if next_cursor in ("", None):
            return list(result.values())
        if not isinstance(next_cursor, str) or next_cursor == cursor or next_cursor in seen_cursors or not page:
            raise ProviderError("Ozon accrual cursor did not advance")
        seen_cursors.add(next_cursor)
        cursor = next_cursor
    raise ProviderError("Ozon accrual page limit reached; incomplete day")
