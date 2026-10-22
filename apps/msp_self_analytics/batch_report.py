"""Deterministic, read-only batch preparation for historical purchase-series reports.

No marketplace actions, HTTP calls, SQL queries or credential reads occur here.
Rows come from an independently controlled, read-only source. A data provider
must fetch each explicit window returned by plan_portfolio(), with rate limits.
"""
from __future__ import annotations

import json
from typing import Any

try:
    from apps.msp_self_analytics.series_analysis import analyze_series, SeriesDataError
    from apps.msp_self_analytics.series_report import build_series_report
    from apps.msp_self_analytics.series_report_ru import format_series_report_ru
except ModuleNotFoundError:
    from series_analysis import analyze_series, SeriesDataError
    from series_report import build_series_report
    from series_report_ru import format_series_report_ru


class PortfolioDataError(ValueError):
    pass


def _identity(row: dict) -> tuple[str, str, str]:
    value = tuple(row.get(k) for k in ("marketplace", "store", "marketplace_sku"))
    if any(not isinstance(v, str) or not v.strip() for v in value):
        raise PortfolioDataError("IDENTITY_REQUIRED")
    return value


def card_key(identity: tuple[str, str, str]) -> str:
    """A collision-free JSON key, preserving distinct marketplace/store/SKU."""
    if len(identity) != 3 or any(not isinstance(v, str) or not v.strip() for v in identity):
        raise PortfolioDataError("IDENTITY_REQUIRED")
    return json.dumps(list(identity), ensure_ascii=False, separators=(",", ":"))


def _group_completed(rows: list[dict], *, max_cards: int) -> tuple[dict, int]:
    if not isinstance(rows, list):
        raise PortfolioDataError("ROWS_LIST_REQUIRED")
    if isinstance(max_cards, bool) or not isinstance(max_cards, int) or not 1 <= max_cards <= 100:
        raise PortfolioDataError("INVALID_CARD_LIMIT")
    groups: dict[str, list[dict]] = {}
    excluded = 0
    for row in rows:
        if not isinstance(row, dict):
            raise PortfolioDataError("INVALID_SOURCE_ROW")
        if row.get("purchase_status", "completed") != "completed":
            excluded += 1
            continue
        key = card_key(_identity(row))
        groups.setdefault(key, []).append(row)
        if len(groups) > max_cards:
            raise PortfolioDataError("CARD_LIMIT_EXCEEDED")
    return groups, excluded


def plan_portfolio(
    rows: list[dict], *, as_of: str, requested_days: int = 30,
    max_cards: int = 20,
) -> dict:
    """Group cards and issue at most two exact period requests per eligible card.

    Conflicted plans, absent review dates, and uncompleted post-observation days
    never lead to provider requests. Returned card IDs are internal and must
    not be posted to public issue comments or logs.
    """
    groups, excluded = _group_completed(rows, max_cards=max_cards)
    cards = []
    for key in sorted(groups):
        group = groups[key]
        try:
            series = analyze_series(group, as_of=as_of, requested_days=requested_days)
        except SeriesDataError as error:
            cards.append({"card_key": key, "status": "INVALID_SERIES",
                          "reason": str(error), "source_rows": len(group),
                          "requests": []})
            continue
        phase = series["series_phase"]
        windows = series["windows"]
        if phase in {"TARGET_CONFLICT", "MORE_ROWS_THAN_TARGET_REQUIRES_RECONCILIATION"}:
            state = "RECONCILIATION_REQUIRED"
        elif series["status"] == "NO_REVIEW_DATE":
            state = "NO_RECORDED_REVIEW_DATE"
        elif windows is None:
            state = "POST_WINDOW_PENDING"
        else:
            state = "READY_FOR_MPSTATS"
        requests = []
        if state == "READY_FOR_MPSTATS":
            requests = [
                {"side": side, "d1": windows[side]["d1"], "d2": windows[side]["d2"]}
                for side in ("before", "after")
            ]
        cards.append({"card_key": key, "status": state,
                      "source_rows": len(group), "series": series,
                      "requests": requests})
    return {"status": "READ_ONLY_REQUEST_PLAN", "as_of": as_of,
            "requested_days": requested_days,
            "card_count": len(cards), "noncompleted_rows_excluded": excluded,
            "provider_request_count": sum(len(c["requests"]) for c in cards),
            "cards": cards,
            "marketplace_actions_allowed": False}


def build_portfolio_report(
    rows: list[dict], observations: dict[str, dict] | None, *,
    as_of: str, requested_days: int = 30, max_cards: int = 20,
) -> dict:
    """Produce individual human-readable observations after provider readback.

    Observations are keyed by card_key() and each contains exact dated 'before'
    and 'after' provider results. Missing or stale results are never guessed.
    """
    if observations is None:
        observations = {}
    if not isinstance(observations, dict):
        raise PortfolioDataError("INVALID_PROVIDER_OBSERVATIONS")
    plan = plan_portfolio(rows, as_of=as_of, requested_days=requested_days,
                          max_cards=max_cards)
    groups, _ = _group_completed(rows, max_cards=max_cards)
    reports = []
    counts = {"ready_with_both_sources": 0, "provider_data_incomplete": 0,
              "reconciliation_required": 0, "review_date_missing": 0,
              "post_window_pending": 0, "invalid_series": 0}
    for card in plan["cards"]:
        key, state = card["card_key"], card["status"]
        if state == "INVALID_SERIES":
            counts["invalid_series"] += 1
            reports.append({"card_key": key, "status": state,
                            "reason": card["reason"], "report": None})
            continue
        if state == "RECONCILIATION_REQUIRED":
            counts["reconciliation_required"] += 1
            reports.append({"card_key": key, "status": state,
                            "series": card["series"], "report": None})
            continue
        raw = observations.get(key)
        if raw is not None and not isinstance(raw, dict):
            raise PortfolioDataError("INVALID_PROVIDER_CARD")
        raw = raw or {}
        report = build_series_report(groups[key], raw.get("before"), raw.get("after"),
                                     as_of=as_of, requested_days=requested_days)
        if state == "NO_RECORDED_REVIEW_DATE":
            counts["review_date_missing"] += 1
        elif state == "POST_WINDOW_PENDING":
            counts["post_window_pending"] += 1
        elif report["status"] == "MPSTATS_WINDOWS_INCOMPLETE":
            counts["provider_data_incomplete"] += 1
        else:
            counts["ready_with_both_sources"] += 1
        reports.append({"card_key": key, "status": report["status"],
                        "report": report,
                        "text_ru": format_series_report_ru(report)})
    return {"status": "DESCRIPTIVE_PORTFOLIO_ONLY",
            "as_of": as_of, "requested_days": requested_days,
            "card_count": plan["card_count"],
            "noncompleted_rows_excluded": plan["noncompleted_rows_excluded"],
            "provider_request_count_planned": plan["provider_request_count"],
            "summary": counts, "cards": reports,
            "causal_effect_estimated": False,
            "marketplace_actions_allowed": False}
