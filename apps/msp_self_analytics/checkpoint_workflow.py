"""Single-card, multi-review checkpoint planning and source-gated analytics.

Read-only composition of existing series_analysis + series_report. It is the
stable boundary between historical registry rows and *estimated* MPSTATS WB
window observations. It never invents review publication, organic orders, a
counterfactual control group or causal effects.
"""
from __future__ import annotations

from datetime import date
from typing import Any

try:
    from apps.msp_self_analytics.series_analysis import analyze_series, SeriesDataError
    from apps.msp_self_analytics.series_report import build_series_checkpoint_reports
except ModuleNotFoundError:
    from series_analysis import analyze_series, SeriesDataError
    from series_report import build_series_checkpoint_reports


class CheckpointPlanningError(ValueError):
    pass


def _signature(window: dict[str, str]) -> str:
    return window["d1"] + "|" + window["d2"]


def _validate_as_of(date_str: str) -> None:
    try:
        if not isinstance(date_str, str):
            raise ValueError("INVALID_AS_OF")
        date.fromisoformat(date_str)
    except ValueError as exc:
        raise CheckpointPlanningError("INVALID_AS_OF") from exc


def plan_checkpoint_reads(
    rows: list[dict],
    *,
    as_of: str,
    requested_days: int = 30,
    max_checkpoints: int = 12,
    max_provider_reads: int = 24,
) -> dict:
    """Plan explicit MPSTATS window reads; memoize exact identical date ranges.

    Refuse truncated checkpoint series, not silently drop earlier/later reviews.
    Request limits are safety caps, not business restrictions on number of
    recorded purchases. For more than the limit, caller must request a
    separately reviewed larger batch.
    """
    _validate_as_of(as_of)
    if type(max_checkpoints) is not int or max_checkpoints < 1:
        raise CheckpointPlanningError("INVALID_MAX_CHECKPOINTS")
    if type(max_provider_reads) is not int or max_provider_reads < 1:
        raise CheckpointPlanningError("INVALID_MAX_PROVIDER_READS")
    series = analyze_series(rows, as_of=as_of, requested_days=requested_days)
    checkpoints = series["checkpoints"]
    if len(checkpoints) > max_checkpoints:
        raise CheckpointPlanningError("CHECKPOINT_LIMIT_EXCEEDED")
    seen = set()
    reads = []
    mapping = {}
    for cp in checkpoints:
        if cp["windows"] is None:
            continue
        num = cp["checkpoint_number"]
        mapping[num] = {}
        for side in ("before", "after"):
            window = cp["windows"][side]
            key = _signature(window)
            mapping[num][side] = key
            if key not in seen:
                seen.add(key)
                reads.append({"key": key, "d1": window["d1"], "d2": window["d2"],
                              "source": "MPSTATS_WB_SKU_FULL",
                              "expected_observation": "PROVIDER_ESTIMATE"})
    if len(reads) > max_provider_reads:
        raise CheckpointPlanningError("PROVIDER_READ_LIMIT_EXCEEDED")
    return {
        "status": "READY_FOR_SOURCE_READS" if reads else "NO_COMPLETED_POST_WINDOWS",
        "source_identity_required": ("marketplace", "store", "marketplace_sku"),
        "series": series,
        "requests": reads,
        "checkpoint_to_requests": mapping,
        "provider_read_count": len(reads),
        "checkpoint_count": len(checkpoints),
        "excluded_event_days": True,
        "future_review_censors_earlier_post_window": True,
        "estimated_sales_not_paid_orders": True,
        "effect_attribution_forbidden": True,
        "marketplace_actions_allowed": False,
    }


def assemble_checkpoint_analysis(
    rows: list[dict],
    observations: dict[str, dict],
    *,
    as_of: str,
    requested_days: int = 30,
    max_checkpoints: int = 12,
    max_provider_reads: int = 24,
) -> dict:
    """Require exact keyed provider windows and return source/stock quality flags.

    'observations' is a map indexed only by 'd1|d2'. Values must be already
    normalized to request_status/sales/revenue/days_in_stock and exact dates.
    Missing or rejected reads are UNKNOWN; they are never counted as zeros.
    """
    if not isinstance(observations, dict):
        raise CheckpointPlanningError("OBSERVATIONS_MAPPING_REQUIRED")
    plan = plan_checkpoint_reads(
        rows, as_of=as_of, requested_days=requested_days,
        max_checkpoints=max_checkpoints, max_provider_reads=max_provider_reads,
    )
    by_cp = {}
    for num, sides in plan["checkpoint_to_requests"].items():
        by_cp[num] = {side: observations.get(key) for side, key in sides.items()}
    report = build_series_checkpoint_reports(
        rows, by_cp, as_of=as_of, requested_days=requested_days)
    summary = {"checkpoint_count": len(report["checkpoints"]),
               "with_estimated_sales": 0, "incomplete_source": 0,
               "post_window_pending": 0, "unequal_stock_availability": 0,
               "missing_availability_evidence": 0}
    for cp in report["checkpoints"]:
        cp["interpretation"] = "DESCRIPTIVE_NOT_CAUSAL"
        cp["historical_rating_status"] = "UNKNOWN"
        cp["verified_paid_organic_orders"] = "UNKNOWN"
        cp["verified_comparator_count"] = 0
        cp["economics_status"] = "UNKNOWN"
        cp["source_quality_flags"] = []
        if cp["status"] == "POST_WINDOW_PENDING":
            summary["post_window_pending"] += 1
            cp["source_quality_flags"].append("NO_FINISHED_POST_DAY")
            continue
        obs = cp.get("provider_observations")
        before = obs.get("before") if isinstance(obs, dict) else None
        after = obs.get("after") if isinstance(obs, dict) else None
        if not (isinstance(before, dict) and before.get("valid") and
                isinstance(after, dict) and after.get("valid")):
            summary["incomplete_source"] += 1
            cp["source_quality_flags"].append("MPSTATS_EXACT_WINDOWS_UNAVAILABLE")
            continue
        summary["with_estimated_sales"] += 1
        a = after.get("provider_stock_days")
        b = before.get("provider_stock_days")
        if a is None or b is None:
            summary["missing_availability_evidence"] += 1
            cp["source_quality_flags"].append("STOCK_DAYS_UNKNOWN")
        elif a != b:
            summary["unequal_stock_availability"] += 1
            cp["source_quality_flags"].append("STOCK_AVAILABILITY_DIFFERS")
        if a == 0 or b == 0:
            cp["source_quality_flags"].append("STOCK_NORMALIZED_RATE_UNAVAILABLE")
        if before.get("sales") == 0:
            cp["source_quality_flags"].append("PERCENT_CHANGE_FROM_ZERO_UNDEFINED")
        if not cp["windows"]["full_requested_window"]:
            cp["source_quality_flags"].append("SHORT_EQUAL_OBSERVATION_WINDOW")
        cp["source_quality_flags"].append("OTHER_PRICE_ADVERTISING_DEMAND_CONFOUNDERS_UNVERIFIED")
    return {
        "status": "COMPLETE_DESCRIPTIVE" if summary["incomplete_source"] == 0
                  and summary["post_window_pending"] == 0
                  and summary["with_estimated_sales"] > 0
                  else "PARTIAL_DESCRIPTIVE",
        "series": plan["series"],
        "checkpoints": report["checkpoints"],
        "summary": summary,
        "provider_windows_planned": plan["provider_read_count"],
        "data_class": "MPSTATS_ESTIMATED_SALES_AND_AVAILABILITY",
        "public_reviews_independently_verified": False,
        "causal_conclusion": False,
        "automated_purchase_or_review_actions": False,
    }
