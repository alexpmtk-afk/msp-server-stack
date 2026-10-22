"""MSP-SELF historical comparison of observed MPSTATS periods, without causal claims.

No network, marketplace writes, feedback content or SKU requirement.
Inputs: recorded review date plus purchase date, two metric windows, optional approved peers.
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


def windows(review_date: str, days: int = 14, *, purchase_date: str) -> dict:
    if isinstance(days, bool) or not isinstance(days, int) or days < 1:
        raise InvalidObservation("INVALID_WINDOW_DAYS")
    try:
        t = date.fromisoformat(review_date)
    except (ValueError, TypeError) as e:
        raise InvalidObservation("REVIEW_DATE_REQUIRED") from e
    try:
        bought = date.fromisoformat(purchase_date)
    except (ValueError, TypeError) as e:
        raise InvalidObservation("PURCHASE_DATE_REQUIRED") from e
    if t < bought:
        raise InvalidObservation("REVIEW_DATE_BEFORE_PURCHASE")
    return {
        "review_date": t.isoformat(),
        "anchor_kind": "REGISTRY_REVIEW_DATE_NOT_AUTOMATICALLY_PUBLICATION_VERIFIED",
        "purchase_date": purchase_date,
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


def analyze(review_date: str, before: dict, after: dict, *,
            purchase_date: str,
            review_publication_verified: bool = False,
            business_goal: str = "unknown",
            period_days: int = 14, competitors: list[dict] | None = None) -> dict:
    """Describe post-review patterns. Purchase date is NEVER the implicit anchor."""
    if business_goal not in ("first_reviews", "rating_recovery", "unknown"):
        raise InvalidObservation("UNKNOWN_BUSINESS_GOAL")
    win = windows(review_date, period_days, purchase_date=purchase_date)
    pre = _sample(before, "BEFORE", win["before"], period_days)
    post = _sample(after, "AFTER", win["after"], period_days)
    result = {
        "report_type": "RETROSPECTIVE_OBSERVATION_NOT_CAUSAL_EFFECT",
        "review_date": win["review_date"],
        "purchase_date": win["purchase_date"],
        "business_goal": business_goal,
        "outcome_fields": {
            "mpstats_estimated_sales": "OBSERVED_IF_VALID_WINDOW",
            "orders": "NOT_VERIFIED_IN_CURRENT_MPSTATS_PILOT",
            "review_count_history": "NOT_VERIFIED_IN_CURRENT_MPSTATS_PILOT",
            "rating_history": "NOT_VERIFIED_AS_OF_DATES",
            "review_publication_date": (
                "VERIFIED" if review_publication_verified else "REPORTED_BY_REGISTRY"
            ),
        },
        "anchor_kind": win["anchor_kind"],
        "publication_evidence": (
            "VERIFIED" if review_publication_verified is True else
            "REGISTRY_DATE_ONLY_NOT_VERIFIED"
        ),
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
    if review_publication_verified is not True:
        result["confounders"].append("REVIEW_PUBLICATION_DATE_NOT_INDEPENDENTLY_VERIFIED")
    if purchase_date != review_date:
        result["confounders"].append("PURCHASE_PRECEDED_REVIEW_DATE")
    b_days, a_days = pre.get("provider_days_in_stock"), post.get("provider_days_in_stock")
    if b_days is None or a_days is None:
        result["confounders"].append("STOCK_DAYS_UNAVAILABLE")
    elif b_days != a_days:
        result["confounders"].append("STOCK_DAYS_DIFFERENT")
    if pre.get("rating_in_period_field") != post.get("rating_in_period_field"):
        result["confounders"].append("RATING_FIELD_CHANGED_ASOF_UNKNOWN")
    if pre.get("sales") == 0 or post.get("sales") == 0:
        # Zero-count windows make relative changes unstable or undefined.
        result["confounders"].append("ZERO_ESTIMATED_SALES_IN_A_WINDOW")
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
