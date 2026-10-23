"""Pure card SERIES report: before first recorded review vs after latest review.

Entirely descriptive. Do not estimate a causal contribution from historical
purchases or from reportedly published reviews.
"""
from __future__ import annotations

from math import isfinite
try:
    from apps.msp_self_analytics.series_analysis import analyze_series
except ModuleNotFoundError:
    from series_analysis import analyze_series


def _num(v):
    if isinstance(v, bool) or not isinstance(v,(int,float)) or not isfinite(v) or v<0:
        return None
    return float(v)


def _window(raw, dates, days):
    if not isinstance(raw,dict) or raw.get("request_status") not in ("PASS_STRUCTURED","PASS_JSON"):
        return {"valid":False,"reason":"MPSTATS_SOURCE_UNAVAILABLE"}
    if raw.get("d1")!=dates["d1"] or raw.get("d2")!=dates["d2"]:
        return {"valid":False,"reason":"PROVIDER_WINDOW_MISMATCH"}
    sales=_num(raw.get("sales"))
    stock=_num(raw.get("days_in_stock"))
    if stock is not None and (stock>days or int(stock)!=stock):
        return {"valid":False,"reason":"INVALID_STOCK_DAY_COUNT"}
    return {"valid":sales is not None,"sales":sales,
            "revenue":_num(raw.get("revenue")),
            "provider_stock_days":int(stock) if stock is not None else None,
            "sales_per_calendar_day":sales/days if sales is not None else None,
            "sales_per_provider_stock_day":sales/stock if sales is not None and stock else None}


def _change(a,b):
    return {"absolute": b-a if a is not None and b is not None else None,
            "percent": (100*(b/a-1) if a is not None and b is not None and a>0 else None)}


def build_series_report(rows, before, after, *, as_of, requested_days=30):
    series=analyze_series(rows,as_of=as_of,requested_days=requested_days)
    output={"report_type":"CARD_REVIEW_SERIES_DESCRIPTIVE",
            "series":series,"status":series["status"],
            "provider_observations":None,
            "independent_publication_verification":False,
            "historical_rating_verified":False,
            "real_seller_order_count_verified":False,
            "verified_comparator_count":0,
            "causal_conclusion":False,
            "marketplace_actions_allowed":False}
    windows=series.get("windows")
    if windows is None:return output
    days=windows["effective_days_each"]
    b=_window(before,windows["before"],days)
    a=_window(after,windows["after"],days)
    if not (b.get("valid") and a.get("valid")):
        output["status"]="MPSTATS_WINDOWS_INCOMPLETE"
        output["provider_observations"]={"before":b,"after":a}
        return output
    output["provider_observations"]={
        "before":b,"after":a,
        "estimated_sales_change":_change(b["sales"],a["sales"]),
        "sales_per_calendar_day_change":_change(
            b["sales_per_calendar_day"],a["sales_per_calendar_day"]),
        "sales_per_provider_stock_day_change":_change(
            b["sales_per_provider_stock_day"],a["sales_per_provider_stock_day"]),
        "stock_day_differences_flag":b["provider_stock_days"]!=a["provider_stock_days"],
        "provider_is_estimate_not_verified_paid_orders":True,
    }
    output["status"]=("INTERMEDIATE_FULL_WINDOW" if windows["full_requested_window"]
                      and windows["intermediate_observation"] else
                      "FINAL_REPORTED_FULL_WINDOW" if windows["full_requested_window"]
                      else "INTERMEDIATE_SHORT_EQUAL_WINDOW")
    return output


def build_series_checkpoint_reports(rows, observations_by_checkpoint, *,
                                    as_of, requested_days=30):
    """Create one independent MPSTATS observation per *dated* review checkpoint.

    observations_by_checkpoint maps 1-based checkpoint index to:
      {"before": <provider payload>, "after": <provider payload>}
    The caller must independently request provider windows *for each checkpoint*;
    this function rejects mismatched windows instead of recycling a final-stage
    MPSTATS observation as earlier-stage evidence.
    """
    series = analyze_series(rows, as_of=as_of, requested_days=requested_days)
    if not isinstance(observations_by_checkpoint, dict):
        raise ValueError("CHECKPOINT_OBSERVATIONS_DICTIONARY_REQUIRED")
    results = []
    for cp in series["checkpoints"]:
        num = cp["checkpoint_number"]
        row = {
            "checkpoint_number": num,
            "review_date": cp["review_date"],
            "recorded_review_rows_on_date": cp["recorded_review_rows_on_date"],
            "cumulative_recorded_review_rows": cp["cumulative_recorded_review_rows"],
            "status": cp["status"],
            "windows": cp["windows"],
            "provider_observations": None,
            "causal_conclusion": False,
        }
        if cp["windows"] is None:
            results.append(row)
            continue
        incoming = observations_by_checkpoint.get(num)
        if not isinstance(incoming, dict):
            row["status"] = "MPSTATS_WINDOWS_NOT_PROVIDED"
            results.append(row)
            continue
        dates = cp["windows"]
        days = cp["effective_days_each"]
        before = _window(incoming.get("before"), dates["before"], days)
        after = _window(incoming.get("after"), dates["after"], days)
        if not (before.get("valid") and after.get("valid")):
            row["status"] = "MPSTATS_WINDOWS_INCOMPLETE"
            row["provider_observations"] = {"before": before, "after": after}
            results.append(row)
            continue
        row["provider_observations"] = {
            "before": before, "after": after,
            "estimated_sales_change": _change(before["sales"], after["sales"]),
            "sales_per_provider_stock_day_change": _change(
                before["sales_per_provider_stock_day"],
                after["sales_per_provider_stock_day"]),
            "provider_is_estimate_not_verified_paid_orders": True,
        }
        results.append(row)
    return {
        "report_type": "CARD_REVIEW_EACH_CHECKPOINT_DESCRIPTIVE",
        "series": series,
        "checkpoints": results,
        "recorded_reviews_are_not_independent_publication_proof": True,
        "estimated_sales_are_not_verified_paid_orders": True,
        "causal_conclusion": False,
        "marketplace_actions_allowed": False,
    }
