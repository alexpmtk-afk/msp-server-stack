"""Historical series of recorded purchases and reviews, not rating manipulation.

Canonical owner correction 2026-10-22:
  ONE completed source row = ONE recorded purchase occurrence.
  source 'Кол-во выкупов' / SQLite quantity = repeated per-card TARGET,
  not physical purchased units in that row.
  Recorded review_date = ONE reported review event for that row, not a
  verified rating or guaranteed public publication timestamp.

Only builds descriptive series and symmetric pre/post windows. No networking.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any


class SeriesDataError(ValueError):
    pass


def _day(value: Any, *, nullable: bool = False) -> date | None:
    if nullable and (value is None or value == ""):
        return None
    if not isinstance(value, str):
        raise SeriesDataError("INVALID_DATE")
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise SeriesDataError("INVALID_DATE") from exc


def _target(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise SeriesDataError("INVALID_PLANNED_TOTAL")
    return value


def analyze_series(
    rows: list[dict],
    *,
    as_of: str,
    requested_days: int = 30,
    independently_verified_review_ids: list[str] | None = None,
) -> dict:
    """Analyze ONE marketplace/store/SKU series from separate completed rows.

    The caller must only pass rows for a single identity. A missing review_date
    means the purchased row did not yet provide a reported publication date.
    One link shared by multiple rows never proves unique independent reviews.
    """
    if not isinstance(rows, list) or not rows:
        raise SeriesDataError("NO_COMPLETED_ROWS")
    if isinstance(requested_days, bool) or not isinstance(requested_days, int) or requested_days < 1:
        raise SeriesDataError("INVALID_WINDOW_DAYS")
    today = _day(as_of)
    assert today is not None
    entries = []
    identity = None
    seen_source_rows = set()
    targets = set()
    for index, raw in enumerate(rows):
        if not isinstance(raw, dict) or raw.get("purchase_status", "completed") != "completed":
            raise SeriesDataError("NOT_A_COMPLETED_ROW")
        key = (raw.get("marketplace"), raw.get("store"), raw.get("marketplace_sku"))
        if any(not isinstance(v, str) or not v.strip() for v in key):
            raise SeriesDataError("IDENTITY_REQUIRED")
        if identity is None:
            identity = key
        elif identity != key:
            raise SeriesDataError("MIXED_CARD_IDENTITIES")
        source_key = raw.get("source_row")
        if source_key is not None:
            if source_key in seen_source_rows:
                raise SeriesDataError("DUPLICATE_SOURCE_ROW")
            seen_source_rows.add(source_key)
        target = _target(raw.get("quantity"))
        targets.add(target)
        purchase = _day(raw.get("purchase_date"))
        review = _day(raw.get("review_date"), nullable=True)
        assert purchase is not None
        if review is not None and review < purchase:
            raise SeriesDataError("REVIEW_PRECEDES_PURCHASE")
        if purchase > today or (review is not None and review > today):
            raise SeriesDataError("FUTURE_RECORD_DATE")
        entries.append({"purchase": purchase, "review": review, "target": target,
                        "ordinal": index})
    entries.sort(key=lambda r: (r["purchase"], r["review"] or date.max, r["ordinal"]))
    completed = len(entries)
    review_rows = [r for r in entries if r["review"] is not None]
    reported = len(review_rows)
    different_dates = sorted({r["review"] for r in review_rows})
    target = next(iter(targets)) if len(targets) == 1 else None
    ids = independently_verified_review_ids
    verified = None
    if ids is not None:
        if not isinstance(ids, list) or any(not isinstance(x, str) or not x.strip() for x in ids):
            raise SeriesDataError("INVALID_INDEPENDENT_REVIEW_IDS")
        verified = len(set(x.strip() for x in ids))
    if target is None:
        phase = "TARGET_CONFLICT"
    elif completed > target:
        phase = "MORE_ROWS_THAN_TARGET_REQUIRES_RECONCILIATION"
    elif reported == target and completed == target:
        phase = "REPORTED_SERIES_COMPLETE_PUBLICATION_UNVERIFIED"
    else:
        phase = "INTERMEDIATE_SERIES"
    first_review = different_dates[0] if different_dates else None
    last_review = different_dates[-1] if different_dates else None
    out = {
        "status": "NO_REVIEW_DATE" if not review_rows else "READY_FOR_DESCRIPTIVE_HISTORY",
        "series_phase": phase,
        "planned_total_per_card": target,
        "planned_total_values_conflict": sorted(targets) if target is None else [],
        "recorded_completed_purchase_rows": completed,
        "recorded_purchase_occurrences": completed,
        "recorded_review_date_rows": reported,
        "rows_without_review_date": completed - reported,
        "independently_verified_distinct_review_count": verified,
        "five_star_public_rating_confirmed_from_registry": False,
        "individual_publication_dates_independently_verified": False,
        "first_purchase_date": min(r["purchase"] for r in entries).isoformat(),
        "first_review_date": first_review.isoformat() if first_review else None,
        "latest_review_date": last_review.isoformat() if last_review else None,
        "remaining_against_plan": max(0, target - completed) if target is not None else None,
        "repeat_plan_is_not_summed": True,
        "one_completed_row_counts_as_one_occurrence": True,
        "same_review_url_does_not_prove_distinct_public_reviews": True,
        "sale_effect_not_proven": True,
        "marketplace_actions_allowed": False,
        "windows": None,
    }
    # Each distinct review-date checkpoint receives a separate completed-day
    # window. A subsequent review censors the preceding checkpoint's window;
    # its observations are never silently attributed to the earlier event.
    out["checkpoints"] = _review_checkpoints(
        different_dates, review_rows, first_review, target, today, requested_days,
        total_completed=completed,
    )
    if first_review is None or last_review is None:
        return out
    # A completed post day must be strictly before as_of, never the review day.
    available = max(0, (today - last_review).days - 1)
    actual_days = min(requested_days, available)
    if actual_days < 1:
        out["status"] = "POST_WINDOW_PENDING"
        return out
    out["windows"] = {
        "requested_days_each": requested_days,
        "effective_days_each": actual_days,
        "equal_windows": True,
        "baseline_anchor": "BEFORE_FIRST_RECORDED_REVIEW_DATE",
        "outcome_anchor": "AFTER_LATEST_RECORDED_REVIEW_DATE",
        "before": {
            "d1": (first_review - timedelta(days=actual_days)).isoformat(),
            "d2": (first_review - timedelta(days=1)).isoformat(),
        },
        "after": {
            "d1": (last_review + timedelta(days=1)).isoformat(),
            "d2": (last_review + timedelta(days=actual_days)).isoformat(),
        },
        "gap_contains_review_series": first_review != last_review,
        "full_requested_window": actual_days == requested_days,
        "intermediate_observation": phase != "REPORTED_SERIES_COMPLETE_PUBLICATION_UNVERIFIED",
        "note": "Per-card historical comparison only; review dates are registry-reported, not independently verified platform publications.",
    }
    if actual_days < requested_days:
        out["status"] = "SHORTER_EQUAL_WINDOW_PRELIMINARY"
    return out


def _review_checkpoints(
    dates: list[date], review_rows: list[dict], first: date | None,
    target: int | None, as_of: date, requested_days: int,
    *, total_completed: int,
) -> list[dict]:
    """Repeated baseline vs each successive review group, with censoring.

    Excludes the day of each registry review, the current incomplete date,
    and all later review dates from any earlier checkpoint post-window.
    Same-day events are one checkpoint (not distinguishable by daily data).
    """
    if first is None:
        return []
    checkpoints = []
    counted = 0
    for i, when in enumerate(dates):
        number = sum(r["review"] == when for r in review_rows)
        counted += number
        next_day = dates[i + 1] if i + 1 < len(dates) else None
        # As_of is exclusive: yesterday is the last *completed* day.
        completed_since = max(0, (as_of - when).days - 1)
        until_next = ((next_day - when).days - 1) if next_day is not None else requested_days
        n = min(requested_days, completed_since, max(0, until_next))
        status = ("POST_WINDOW_PENDING" if n < 1 else
                  "FULL_EQUAL_WINDOW" if n == requested_days else
                  "SHORTER_EQUAL_WINDOW_PRELIMINARY")
        entry = {
            "checkpoint_number": i + 1,
            "review_date": when.isoformat(),
            "recorded_review_rows_on_date": number,
            "cumulative_recorded_review_rows": counted,
            "plan_target_per_card": target,
            "total_completed_purchase_rows_in_snapshot": total_completed,
            "next_review_date": next_day.isoformat() if next_day else None,
            "status": status,
            "effective_days_each": n,
            "requested_days_each": requested_days,
            "censored_by_next_review": next_day is not None,
            "day_of_review_excluded": True,
            "same_day_events_not_individually_separable": number > 1,
            "independent_publication_verified": False,
            "causal_effect_proven": False,
            "windows": None,
        }
        if n:
            entry["windows"] = {
                "before": {
                    "d1": (first - timedelta(days=n)).isoformat(),
                    "d2": (first - timedelta(days=1)).isoformat(),
                },
                "after": {
                    "d1": (when + timedelta(days=1)).isoformat(),
                    "d2": (when + timedelta(days=n)).isoformat(),
                },
                "baseline": "BEFORE_FIRST_RECORDED_REVIEW_DATE",
                "outcome": "AFTER_THIS_RECORDED_REVIEW_DATE",
                "equal_windows": True,
                "full_requested_window": n == requested_days,
            }
        checkpoints.append(entry)
    return checkpoints
