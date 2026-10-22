"""MSP-SELF historical comparison of observed MPSTATS periods, without causal claims.

No network, marketplace writes, feedback content or SKU requirement.
Inputs: anonymized event day + two metric windows + optional approved peer series.
Outputs: descriptive quantities and explicit missing/confounding flags.
"""
from __future__ import annotations

from datetime import date, timedelta
from math import isfinite
from statistics import median


class InvalidObservation(ValueError):
    """Input is not a valid comparable historical observation."""


def _metric(source, name):
    value = source.get(name)
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not isfinite(value):
        return None
    if value < 0:
        raise InvalidObservation("NEGATIVE_" + name.upper())
    return float(value)


def windows(event_date: str, days: int = 14) -> dict:
    if isinstance(days, bool) or not isinstance(days, int) or days < 1:
        raise InvalidObservation("INVALID_WINDOW_DAYS")
    try:
        t = date.fromisoformat(event_date)
    except (ValueError, TypeError) as e:
        raise InvalidObservation("INVALID_EVENT_DATE") from e
    return {
        "event_date": t.isoformat(),
        "days": days,
        "before": {"d1": (t - timedelta(days=days)).isoformat(),
                   "d2": (t - timedelta(days=1)).isoformat()},
        "after": {"d1": (t + timedelta(days=1)).isoformat(),
                  "d2": (t + timedelta(days=days)).isoformat()},
    }


def _sample(value: dict, label: str, expected: dict, days: int) -> dict:
    if not isinstance(value, dict) or value.get("request_status") not in ("PASS_STRUCTURED", "PASS_JSON"):
        return {"valid": False, "reason": label + "_SOURCE_NOT_CONFIRMED"}
    if (value.get("d1"), value.get("d2")) != (expected["d1"], expected["d2"]):
        return {"valid": False, "reason": label + "_DATE_MISMATCH"}
    sales = _metric(value, "sales")
    revenue = _metric(value, "revenue")
    stock = _metric(value, "days_in_stock")
    if stock is not None and (stock > days or int(stock) != stock):
        raise InvalidObservation("INVALID_DAYS_IN_STOCK")
    # The provider's "days_in_stock" is not independently confirmed daily sellable
    # availability. A zero denominator must remain unknown, never zero demand.
    return {
        "valid": sales is not None,
        "reason": None if sales is not None else label + "_SALES_NOT_AVAILABLE",
        "sales": sales,
        "revenue": revenue,
        "provider_days_in_stock": int(stock) if stock is not None else None,
        "sales_per_calendar_day": sales / days if sales is not None else None,
        "sales_per_provider_stock_day": sales / stock if sales is not None and stock else None,
        "stock_normalization_status": (
            "PROVIDER_PROXY_ONLY" if stock and sales is not None else "UNAVAILABLE"),
        "rating_in_period_field": _metric(value, "period_rating"),
        "historical_rating_asof_confirmed": False,
    }


def _delta(before: float | None, after: float | None) -> dict:
    if before is None or after is None:
        return {"absolute": None, "percent": None, "status": "UNAVAILABLE"}
    return {
        "absolute": after - before,
        "percent": 100 * (after / before - 1) if before > 0 else None,
        "status": "COMPARABLE" if before > 0 else "PERCENT_UNDEFINED_ZERO_BASE",
    }


def analyze(event_date: str, before: dict, after: dict, *,
            period_days: int = 14, competitors: list[dict] | None = None) -> dict:
    """Calculate descriptive change; validated competitor flags are required for controls."""
    win = windows(event_date, period_days)
    pre = _sample(before, "BEFORE", win["before"], period_days)
    post = _sample(after, "AFTER", win["after"], period_days)
    result = {
        "report_type": "RETROSPECTIVE_OBSERVATION_NOT_CAUSAL_EFFECT",
        "event_date": win["event_date"],
        "windows": win,
        "before": pre,
        "after": post,
        "provider_sales_change": _delta(pre.get("sales"), post.get("sales")),
        "calendar_day_sales_change": _delta(pre.get("sales_per_calendar_day"),
                                            post.get("sales_per_calendar_day")),
        "provider_stock_day_sales_change": _delta(pre.get("sales_per_provider_stock_day"),
                                                  post.get("sales_per_provider_stock_day")),
        "rating_status": "PERIOD_FIELD_OBSERVED_ASOF_SEMANTICS_NOT_VERIFIED",
        "confounders": [],
        "competitors": {"accepted": 0, "rejected": 0, "status": "NOT_PROVIDED"},
        "causal_effect_proven": False,
        "recommendation_automation_allowed": False,
    }
    b_days, a_days = pre.get("provider_days_in_stock"), post.get("provider_days_in_stock")
    if b_days is None or a_days is None:
        result["confounders"].append("STOCK_DAYS_UNAVAILABLE")
    elif b_days != a_days:
        result["confounders"].append("STOCK_DAYS_DIFFERENT")
    if pre.get("rating_in_period_field") != post.get("rating_in_period_field"):
        result["confounders"].append("RATING_FIELD_CHANGED_ASOF_UNKNOWN")
    if (pre.get("sales") or 0) + (post.get("sales") or 0) <= 5:
        # Only a descriptive small-event flag. Not a statistical hypothesis test.
        result["confounders"].append("VERY_FEW_ESTIMATED_SALES")
    if not (pre.get("valid") and post.get("valid")):
        result["report_status"] = "INCOMPLETE"
    else:
        result["report_status"] = "DESCRIPTIVE_ONLY"
    if competitors is not None:
        if not isinstance(competitors, list):
            raise InvalidObservation("INVALID_COMPETITOR_LIST")
        accepted = []
        rejected = 0
        for candidate in competitors:
            # Provider photo/category similarity alone is insufficient. All three
            # human/attribute checks are explicit prerequisites for comparative use.
            if not isinstance(candidate, dict) or not all(
                candidate.get(flag) is True for flag in
                ("same_product_category", "same_intended_use", "attributes_checked")
            ):
                rejected += 1
                continue
            peer_before = _sample(candidate.get("before"), "BEFORE", win["before"], period_days)
            peer_after = _sample(candidate.get("after"), "AFTER", win["after"], period_days)
            if peer_before.get("valid") and peer_after.get("valid"):
                accepted.append(peer_after["sales_per_calendar_day"] -
                                peer_before["sales_per_calendar_day"])
            else:
                rejected += 1
        comp = {"accepted": len(accepted), "rejected": rejected,
                "status": "VERIFIED_CANDIDATE_SERIES" if accepted else "NO_VERIFIED_COMPARATORS"}
        own = result["calendar_day_sales_change"]["absolute"]
        if accepted and own is not None:
            shift = median(accepted)
            comp["median_peer_daily_change"] = shift
            comp["own_minus_peer_daily_change"] = own - shift
            comp["interpretation"] = "DESCRIPTIVE_DIFFERENCE_NOT_CAUSAL_IMPACT"
        result["competitors"] = comp
    return result
