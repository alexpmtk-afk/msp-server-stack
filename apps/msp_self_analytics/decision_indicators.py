"""MSP-SELF-05/06: source-gated, read-only own KPI and legal scenario formulas.

Pure mathematics; no DB, API, marketplace actions or causal self-purchase logic.
Do not pass provider-estimated sales as verified organic seller orders.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from datetime import date
from statistics import median

VARIABLE_COSTS = (
    "production_cost", "marketplace_fee", "logistics",
    "fulfillment", "acquiring", "storage", "returns_allowance",
    "taxes", "other_variable_cost",
)
COST_FIELDS = ("seller_price",) + VARIABLE_COSTS


def _num(value):
    if isinstance(value, bool) or value is None:
        return None
    if not isinstance(value, (int, float, str, Decimal)):
        return None
    try:
        n = Decimal(str(value))
    except (ValueError, InvalidOperation):
        return None
    return n if n.is_finite() else None


def _fact(record, source_kind):
    if not isinstance(record, dict):
        return None
    if (record.get("status") != "FACT"
            or record.get("source_kind") != source_kind
            or not isinstance(record.get("source_ref"), str)
            or not record["source_ref"].strip()):
        return None
    return _num(record.get("value"))


def _format(n):
    return format(n.normalize(), "f")


def _unknown(reason, missing=None):
    return {"status": "UNKNOWN", "reason": reason,
            "missing_inputs": list(missing or [])}


def organic_sales_per_available_day(organic_sold, available_days):
    """Only verified own orders/stock, for identical observation intervals."""
    units = _fact(organic_sold, "SELLER_ORGANIC_SALES")
    days = _fact(available_days, "SELLER_AVAILABILITY")
    missing = []
    if units is None or units < 0 or units != units.to_integral_value():
        missing.append("verified_organic_sold_units")
    if days is None or days < 0 or days != days.to_integral_value():
        missing.append("verified_available_days")
    if missing:
        return _unknown("MISSING_VERIFIED_OWN_SOURCES", missing)
    first = organic_sold.get("interval")
    second = available_days.get("interval")
    if (not isinstance(first, dict) or first != second or
            not first.get("d1") or not first.get("d2")):
        return _unknown("OBSERVATION_INTERVAL_NOT_ALIGNED")
    try:
        start = date.fromisoformat(first["d1"])
        end = date.fromisoformat(first["d2"])
        allowed_days = (end - start).days + 1
        if allowed_days <= 0 or days > allowed_days:
            return _unknown("INVALID_AVAILABILITY_WINDOW")
    except (ValueError, TypeError):
        return _unknown("INVALID_AVAILABILITY_WINDOW")
    if days == 0:
        return _unknown("NO_AVAILABLE_DAYS")
    return {
        "status": "FACT_DERIVED",
        "value": _format(units / days),
        "formula": "verified_organic_units / verified_available_days",
        "unit": "organic_units_per_available_day",
        "days_used": int(days),
        "estimated_marketplace_sales_used": False,
    }


def verified_peer_price_index(own_price, competitors):
    """Do not compute a price median from merely 'similar' products."""
    value = _fact(own_price, "VERIFIED_OWN_PRICE")
    if value is None or value <= 0:
        return _unknown("OWN_PRICE_UNVERIFIED")
    if not isinstance(competitors, list):
        return _unknown("COMPARATORS_NOT_PROVIDED")
    as_of = own_price.get("observed_on")
    try:
        if not isinstance(as_of, str):
            raise ValueError("missing")
        date.fromisoformat(as_of)
    except ValueError:
        return _unknown("OWN_PRICE_DATE_UNKNOWN")
    prices = []
    for row in competitors:
        if not isinstance(row, dict) or row.get("comparability") != "VERIFIED_COMPARABLE":
            continue
        if not isinstance(row.get("approval_ref"), str) or not row["approval_ref"].strip():
            continue
        # Only simultaneous prices can form a meaningful price ratio.
        if not isinstance(row.get("price"), dict) or row["price"].get("observed_on") != as_of:
            continue
        cost = _fact(row.get("price"), "VERIFIED_COMPETITOR_PRICE")
        if cost is not None and cost > 0:
            prices.append(cost)
    if not prices:
        return _unknown("NO_VERIFIED_COMPARABLE_PRICES")
    value_median = median(prices)
    return {
        "status": "FACT_DERIVED",
        "value": _format(value / value_median),
        "formula": "verified_own_price / median(verified_comparable_prices)",
        "peer_count": len(prices),
        "peer_prices_source_status": "VERIFIED_COMPARABLE_ONLY",
        "causal_claim": False,
    }


def variable_unit_contribution(costs):
    """Require all expense fields from documented finance/seller records."""
    if not isinstance(costs, dict):
        return _unknown("FINANCE_DATA_REQUIRED", COST_FIELDS)
    missing = []
    verified = {}
    for key in COST_FIELDS:
        val = _fact(costs.get(key), "VERIFIED_FINANCE")
        if val is None or val < 0:
            missing.append(key)
        else:
            verified[key] = val
    if missing:
        return _unknown("FINANCIAL_COSTS_INCOMPLETE", missing)
    margin = verified["seller_price"] - sum(
        (verified[k] for k in VARIABLE_COSTS), Decimal("0")
    )
    return {
        "status": "FACT_DERIVED",
        "value": _format(margin),
        "unit": "currency_per_unit",
        "formula": "seller_price - sum(all_verified_unit_variable_costs)",
        "includes_all_required_cost_categories": True,
        "not_a_net_company_profit": True,
    }


def estimated_incremental_contribution(costs, expected_units, action_spend):
    """A scenario, never causal proof or authority to execute a marketplace action."""
    margin = variable_unit_contribution(costs)
    if margin["status"] != "FACT_DERIVED":
        return _unknown("MARGIN_UNKNOWN", margin.get("missing_inputs"))
    if not isinstance(expected_units, dict):
        return _unknown("SCENARIO_METHOD_MISSING")
    units = _num(expected_units.get("value"))
    if (expected_units.get("status") != "MODEL_ESTIMATE"
            or not isinstance(expected_units.get("method_ref"), str)
            or not expected_units["method_ref"].strip() or units is None):
        return _unknown("SCENARIO_METHOD_MISSING")
    spend = _fact(action_spend, "VERIFIED_FINANCE")
    if spend is None or spend < 0:
        return _unknown("ACTION_COST_UNKNOWN")
    value = units * Decimal(margin["value"]) - spend
    return {
        "status": "MODEL_ESTIMATE",
        "value": _format(value),
        "unit": "currency",
        "formula": "estimated_delta_organic_units * verified_unit_contribution - verified_action_cost",
        "method_ref": expected_units["method_ref"],
        "causal_effect_proved": False,
        "approval_to_execute": False,
        "scenario_is_not_a_recommendation": True,
    }
