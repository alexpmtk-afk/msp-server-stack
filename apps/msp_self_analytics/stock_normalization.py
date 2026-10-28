"""Read-only descriptive stock-exposure normalization for MPSTATS order estimates.

Only computes observed estimated orders per *recorded in-stock day*.
Does not extrapolate missed days, certify paid/organic sales, or infer
self-purchase/review causality. No external dependencies or writes.
"""
from __future__ import annotations
from math import isfinite


def _orders(value):
    return float(value) if type(value) in (int, float) and isfinite(value) and value >= 0 else None


def _stock(value, maximum):
    if (type(value) not in (int, float) or not isfinite(value)
            or value != int(value) or not 0 <= value <= maximum):
        return None
    return int(value)


def normalize_stock_exposure(orders_before, orders_after, stock_before, stock_after,
                             *, window_days: int) -> dict:
    """Keep missing/zero exposure distinct from measured zero *orders*."""
    if type(window_days) is not int or not 1 <= window_days <= 90:
        raise ValueError("INVALID_STOCK_WINDOW")
    b, a = _orders(orders_before), _orders(orders_after)
    sb, sa = _stock(stock_before, window_days), _stock(stock_after, window_days)
    out = {
        "status": "UNKNOWN",
        "metric": "MPSTATS_ESTIMATED_ORDERS_PER_RECORDED_IN_STOCK_DAY",
        "window_days_each": window_days,
        "estimated_orders_before": b, "estimated_orders_after": a,
        "in_stock_days_before": sb, "in_stock_days_after": sa,
        "in_stock_coverage_percent_before": 100 * sb / window_days if sb is not None else None,
        "in_stock_coverage_percent_after": 100 * sa / window_days if sa is not None else None,
        "orders_per_in_stock_day_before": None,
        "orders_per_in_stock_day_after": None,
        "rate_absolute_change": None, "rate_percent_change": None,
        "rate_percent_baseline_defined": False,
        "small_observed_sample": None,
        "stock_coverage_differs": sb != sa if sb is not None and sa is not None else None,
        "causal_inference_allowed": False,
        "verified_paid_or_organic_orders": False,
        "missing_day_extrapolation_allowed": False,
    }
    if b is None or a is None:
        out["status"] = "ESTIMATED_ORDERS_MISSING"
    elif sb is None or sa is None:
        out["status"] = "STOCK_DAYS_MISSING_OR_INVALID"
    elif sb == 0 or sa == 0:
        out["status"] = "ZERO_STOCK_EXPOSURE"
    else:
        before_rate, after_rate = b / sb, a / sa
        out["orders_per_in_stock_day_before"] = before_rate
        out["orders_per_in_stock_day_after"] = after_rate
        out["rate_absolute_change"] = after_rate - before_rate
        out["rate_percent_baseline_defined"] = before_rate > 0
        out["rate_percent_change"] = (100 * (after_rate / before_rate - 1)
                                      if before_rate > 0 else None)
        out["small_observed_sample"] = min(b, a) < 10
        out["status"] = ("READY_LOW_SAMPLE" if out["small_observed_sample"]
                         else "READY_DESCRIPTIVE")
    return out
