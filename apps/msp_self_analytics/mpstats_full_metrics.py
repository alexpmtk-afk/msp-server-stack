"""MPSTATS WB external analytics: conservative numeric field extraction.

The provider's 2026 display calls traditional stock-parser 'sales' and
'revenue' 'orders pcs' and 'orders amount'. Field names still differ in the
wb_sku(full) MCP response. Do not label them actual payments or organic units.
'purchase' and 'purchase_after_return' are deliberately left provider-named
until their units and time scope are verified on the endpoint.
"""
from __future__ import annotations

from math import isfinite

FIELDS = (
    "sales", "revenue", "days_in_stock",
    "sales_estimated", "revenue_estimated",
    "purchase", "purchase_after_return",
    "lost_profit",
)
SOURCE_TYPE = "MPSTATS_WB_EXTERNAL_ESTIMATE"


def finite_nonnegative(value):
    return float(value) if type(value) in (int,float) and isfinite(value) and value>=0 else None


def extract_full_period_metrics(stats):
    """Keep all supported fields distinct; absent!=zero and estimate!=fact."""
    data=stats if isinstance(stats,dict) else {}
    numeric={field:finite_nonnegative(data.get(field)) for field in FIELDS}
    return {
        "provider": SOURCE_TYPE,
        "metrics": numeric,
        "fields_present":sorted(k for k in FIELDS if k in data),
        "fields_non_numeric":sorted(k for k in FIELDS if k in data and numeric[k] is None),
        "orders_units_legacy_api_field":"sales",
        "orders_amount_legacy_api_field":"revenue",
        "provider_purchase_fields_unit_verified":False,
        "provider_return_units_independently_verified":False,
        "actual_seller_paid_orders_verified":False,
        "known_organic_orders_verified":False,
        "provider_estimate_includes_self_purchases":True,
    }


def pair_period_metrics(before,after):
    """Before/after side input normalized by extract_full_period_metrics."""
    if not isinstance(before,dict) or not isinstance(after,dict):
        return {"status":"UNKNOWN_SOURCE"}
    x=before.get("metrics") or {}
    y=after.get("metrics") or {}
    fields={}
    for key in FIELDS:
        a=finite_nonnegative(x.get(key))
        b=finite_nonnegative(y.get(key))
        delta=b-a if a is not None and b is not None else None
        fields[key]={
            "before":a,"after":b,"absolute_change":delta,
            "percent_change":100*(b/a-1) if a is not None and b is not None and a>0 else None,
            "state":"AVAILABLE" if a is not None and b is not None else "UNKNOWN",
        }
    return {
        "status":"MPSTATS_EXTERNAL_PERIOD_COMPARISON",
        "fields":fields,
        "orders_units_field":"sales", "orders_amount_field":"revenue",
        "return_count":"UNKNOWN",
        "purchase_rate_or_units":"UNIT_UNVERIFIED",
        "causal_inference":False,
        "money_is_verified_payment":False,
        "all_figures_are_provider_observations":True,
    }
