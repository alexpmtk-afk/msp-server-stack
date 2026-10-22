"""Build one privacy-safe historical observation from verified, dated inputs.

This report neither attributes causality nor recommends marketplace interventions.
It keeps registry purchase quantities separate from proven published feedback.
No network access, secrets or database writes.
"""
from __future__ import annotations

from datetime import date
from typing import Any

try:
    from apps.msp_self_analytics.retrospective import analyze, InvalidObservation
    from apps.msp_self_analytics.review_event import classify_review_event
    from apps.msp_self_analytics.purchase_unit_audit import audit_units
except ModuleNotFoundError:
    from retrospective import analyze, InvalidObservation
    from review_event import classify_review_event
    from purchase_unit_audit import audit_units


def build_case_report(
    event: dict,
    before: dict,
    after: dict,
    *,
    as_of: str,
    window_days: int = 14,
    verified_review_ids: list[str] | None = None,
    verified_publication_date: str | None = None,
    checked_competitors: list[dict] | None = None,
) -> dict:
    """LEGACY single-row technical report, not the card-level series outcome.

    event: purchase_date, review_date, quantity and optional review_url_present,
    business_goal. Explicit source_status cannot be silently upgraded.
    """
    if not isinstance(event, dict):
        raise ValueError("EVENT_INPUT_REQUIRED")
    state = event.get("purchase_status")
    if state != "completed":
        raise ValueError("PURCHASE_NOT_COMPLETED")
    quantity = event.get("quantity")
    quantity_info = audit_units(quantity, verified_review_ids)
    life = classify_review_event(
        event.get("purchase_date"), event.get("review_date"),
        publication_date_verified=verified_publication_date,
        review_url_present=event.get("review_url_present") is True,
    )
    if not life["analyze_review_outcome"]:
        return {
            "status": "REVIEW_ANALYSIS_NOT_ELIGIBLE",
            "event_state": life["status"],
            "purchase_units": quantity_info["purchase_units"],
            "no_purchase_date_fallback": True,
            "reported_review_date": life["review_date_registry"],
            "verified_publication": False,
            "historical_outcomes": None,
            "no_causal_claim": True,
        }
    try:
        evaluated = date.fromisoformat(as_of)
    except (ValueError, TypeError) as exc:
        raise ValueError("AS_OF_DATE_INVALID") from exc
    outcome = analyze(
        life["anchor_date"], before, after,
        purchase_date=life["purchase_date"],
        period_days=window_days,
        business_goal=event.get("business_goal", "unknown"),
        review_publication_verified=life["date_quality"] == "PUBLICATION_VERIFIED",
        competitors=checked_competitors,
    )
    if date.fromisoformat(outcome["windows"]["after"]["d2"]) >= evaluated:
        return {
            "status": "POST_WINDOW_INCOMPLETE",
            "event_state": life["status"],
            "purchase_units": quantity_info["purchase_units"],
            "review_date": life["review_date_registry"],
            "post_window_end": outcome["windows"]["after"]["d2"],
            "no_purchase_date_fallback": True,
            "historical_outcomes": None,
            "no_causal_claim": True,
        }
    confounders = list(outcome["confounders"])
    if quantity_info["multiple_units_single_date_ambiguous"]:
        confounders.append("MULTIPLE_UNITS_SINGLE_REVIEW_DATE")
    if quantity_info["individually_verified_review_count"] is None:
        confounders.append("INDIVIDUAL_REVIEW_PUBLICATIONS_UNKNOWN")
    if quantity_info["more_reviews_than_units"]:
        confounders.append("REVIEW_ASSOCIATION_REQUIRES_RECONCILIATION")
    if outcome["competitors"]["accepted"] == 0:
        confounders.append("CONTROL_GROUP_NOT_VALIDATED")
    return {
        "status": outcome["report_status"],
        "report_kind": "LEGACY_SINGLE_ROW_TECHNICAL_OBSERVATION_NOT_SERIES",
        "card_series_outcome_requires": "series_analysis.analyze_series",
        "business_goal": outcome["business_goal"],
        "event_state": life["status"],
        "review_date_from_registry": life["review_date_registry"],
        "publication_date_verification": life["date_quality"],
        "purchase_date": life["purchase_date"],
        "elapsed_days_purchase_to_review": life["days_between_purchase_and_review"],
        "windows": outcome["windows"],
        "purchase_quantity_evidence": quantity_info,
        "observed_metrics": {
            "provider_estimated_sales": {
                "before": outcome["before"].get("sales"),
                "after": outcome["after"].get("sales"),
                "change": outcome["provider_sales_change"],
            },
            "provider_stock_days": {
                "before": outcome["before"].get("provider_days_in_stock"),
                "after": outcome["after"].get("provider_days_in_stock"),
                "per_stock_day_change": outcome["provider_stock_day_sales_change"],
                "data_quality": "PROVIDER_PROXY_NOT_VERIFIED_SELLABLE_DAYS",
            },
            "verified_historical_rating": None,
            "historical_review_count": None,
            "actual_paid_cabinet_orders": None,
        },
        "comparable_products": outcome["competitors"],
        "confidence_limitations": sorted(set(confounders)),
        "causal_effect_proven": False,
        "automated_marketplace_action": False,
    }
