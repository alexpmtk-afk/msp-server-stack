"""Source-aware price event context for historical review-date checkpoint analytics.

Read-only pure helper. The MSP v_price_history is a dated *event* journal,
not proof of complete observed retail prices or marketplace discounts. No
event does not mean price never changed.
"""
from __future__ import annotations
from datetime import date


def _date(value):
    if not isinstance(value,str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def price_event_context(report: dict, events: list[dict] | None,
                        *, source_status: str) -> dict:
    """Annotate checkpoints with known dated internal price journal changes.

    Source must be the exact same marketplace/store/SKU and a successful
    read-only view query. It must have been filtered before passing here.
    No prices, seller names or commercial event notes are returned.
    """
    if not isinstance(report,dict) or not isinstance(report.get("checkpoints"),list):
        raise ValueError("CHECKPOINT_REPORT_REQUIRED")
    if source_status != "VERIFIED_READONLY_VIEW":
        return {"status":"UNKNOWN_PRICE_HISTORY",
                "reason":"PRICE_JOURNAL_NOT_VERIFIED",
                "total_dated_rows":None, "checkpoints":[]}
    if not isinstance(events,list):
        raise ValueError("PRICE_EVENTS_REQUIRED")
    dates=[]
    invalid=0
    for entry in events:
        if not isinstance(entry,dict):
            invalid+=1
            continue
        value=_date(entry.get("event_date"))
        if value is None:
            invalid+=1
        else:
            dates.append(value)
    reports=[]
    for checkpoint in report["checkpoints"]:
        cp={"checkpoint_number":checkpoint["checkpoint_number"],
            "status":"UNKNOWN_WINDOW",
            "recorded_price_changes_before_window":None,
            "recorded_price_changes_between_windows":None,
            "recorded_price_changes_after_window":None,
            "confounding_price_events":None}
        w=checkpoint.get("windows")
        if not isinstance(w,dict):
            reports.append(cp)
            continue
        before=w["before"];after=w["after"]
        b1,b2=_date(before.get("d1")),_date(before.get("d2"))
        a1,a2=_date(after.get("d1")),_date(after.get("d2"))
        if None in (b1,b2,a1,a2) or not (b1<=b2<a1<=a2):
            reports.append(cp)
            continue
        bcount=sum(b1<=d<=b2 for d in dates)
        middle=sum(b2<d<a1 for d in dates)
        acount=sum(a1<=d<=a2 for d in dates)
        cp.update({
            "status":"DATED_PRICE_EVENTS_FOUND" if bcount+middle+acount else
                     "NO_RECORDED_PRICE_EVENTS_IN_PERIOD",
            "recorded_price_changes_before_window":bcount,
            "recorded_price_changes_between_windows":middle,
            "recorded_price_changes_after_window":acount,
            "confounding_price_events":bool(bcount+middle+acount),
        })
        reports.append(cp)
    return {"status":"PARTIAL_INVALID_DATES" if invalid else "READONLY_VIEW_AUDITED",
            "total_dated_rows":len(dates),
            "invalid_date_rows":invalid,
            "historical_price_levels_independently_verified":False,
            "no_events_does_not_prove_no_price_changes":True,
            "checkpoints":reports,
            "marketplace_actions_allowed":False}
