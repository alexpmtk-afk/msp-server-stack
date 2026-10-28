"""Source-aware numeric MSP seller-price event context by review checkpoint.

The recorded price journal is NOT a complete WB/Ozon buyer-price timeline.
Events here are price corrections, not proof of buyer-facing final price or
of causal effects on orders. No persistence, network or outbound actions.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation


def _date(value):
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _money(value):
    """Normalize recorded decimal TEXT without treating blank as zero."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal, str)):
        raw = str(value).replace("\u00a0", "").replace(" ", "").replace(",", ".")
        if not raw:
            return None
        try:
            number = Decimal(raw)
        except InvalidOperation:
            return None
        if number.is_finite() and Decimal("0") <= number <= Decimal("1000000000000"):
            return format(number, "f")
    return None


def _event_record(entry):
    old = _money(entry.get("old_price"))
    new = _money(entry.get("new_price"))
    difference = None
    percent = None
    if old is not None and new is not None:
        o, n = Decimal(old), Decimal(new)
        difference = format(n - o, "f")
        if o > 0:
            percent = format((n - o) * Decimal(100) / o, ".2f")
    segment = entry.get("source_segment")
    return {
        "event_date": entry["event_date"],
        "source_segment": segment if segment in ("current", "archive") else None,
        "source_ordinal": entry.get("source_ordinal"),
        "old_seller_price_rub": old,
        "new_seller_price_rub": new,
        "change_rub": difference,
        "change_percent": percent,
        "list_price_rub": _money(entry.get("list_price")),
        "minimum_price_rub": _money(entry.get("minimum_price")),
        "discount_percent_recorded": _money(entry.get("discount_percent")),
        "old_new_pair_verified": old is not None and new is not None,
        "price_kind": "seller_price_after_seller_discount_not_buyer_final",
        "source": "MSP_SQLITE_V_PRICE_HISTORY",
    }


def price_event_context(report: dict, events: list[dict] | None,
                        *, source_status: str) -> dict:
    """Match exact historical price corrections to each symmetrical window.

    The caller must query v_price_history with the exact already-resolved
    marketplace/store/SKU identity. All numeric fields are optional.
    """
    if not isinstance(report, dict) or not isinstance(report.get("checkpoints"), list):
        raise ValueError("CHECKPOINT_REPORT_REQUIRED")
    if source_status != "VERIFIED_READONLY_VIEW":
        return {"status": "UNKNOWN_PRICE_HISTORY",
                "reason": "PRICE_JOURNAL_NOT_VERIFIED",
                "total_dated_rows": None, "checkpoints": []}
    if not isinstance(events, list):
        raise ValueError("PRICE_EVENTS_REQUIRED")
    validated = []
    invalid = 0
    for entry in events:
        if not isinstance(entry, dict):
            invalid += 1
            continue
        d = _date(entry.get("event_date"))
        if d is None:
            invalid += 1
            continue
        normalized = _event_record(entry)
        validated.append((d, normalized))
    validated.sort(key=lambda record: (
        record[0],
        record[1].get("source_segment") or "",
        str(record[1].get("source_ordinal") or "")))

    checkpoints = []
    for checkpoint in report["checkpoints"]:
        cp = {"checkpoint_number": checkpoint["checkpoint_number"],
              "status": "UNKNOWN_WINDOW",
              "recorded_price_changes_before_window": None,
              "recorded_price_changes_between_windows": None,
              "recorded_price_changes_after_window": None,
              "confounding_price_events": None,
              "before_window_price_events": [],
              "between_windows_price_events": [],
              "after_window_price_events": []}
        w = checkpoint.get("windows")
        if not isinstance(w, dict):
            checkpoints.append(cp)
            continue
        before, after = w["before"], w["after"]
        b1, b2 = _date(before.get("d1")), _date(before.get("d2"))
        a1, a2 = _date(after.get("d1")), _date(after.get("d2"))
        if None in (b1, b2, a1, a2) or not (b1 <= b2 < a1 <= a2):
            checkpoints.append(cp)
            continue
        pre = [entry for day, entry in validated if b1 <= day <= b2]
        middle = [entry for day, entry in validated if b2 < day < a1]
        post = [entry for day, entry in validated if a1 <= day <= a2]
        cp.update({
            "status": "DATED_PRICE_EVENTS_FOUND" if pre or middle or post
                      else "NO_RECORDED_PRICE_EVENTS_IN_PERIOD",
            "recorded_price_changes_before_window": len(pre),
            "recorded_price_changes_between_windows": len(middle),
            "recorded_price_changes_after_window": len(post),
            "confounding_price_events": bool(pre or middle or post),
            "before_window_price_events": pre,
            "between_windows_price_events": middle,
            "after_window_price_events": post,
            "post_review_seller_price_changed_in_journal": bool(post),
            "seller_price_confounds_review_attribution": bool(post),
        })
        checkpoints.append(cp)
    return {
        "status": "PARTIAL_INVALID_DATES" if invalid else "READONLY_VIEW_AUDITED",
        "total_dated_rows": len(validated),
        "invalid_date_rows": invalid,
        "historical_price_levels_independently_verified": False,
        "recorded_seller_price_not_buyer_final": True,
        "no_events_does_not_prove_no_price_changes": True,
        "checkpoints": checkpoints,
        "marketplace_actions_allowed": False,
    }
