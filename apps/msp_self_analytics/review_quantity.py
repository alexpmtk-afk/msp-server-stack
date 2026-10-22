"""Read-only accounting of historical purchase units and verified review records.

The count of purchased units is factual from the registry. Individual feedback
remains unknown unless independently dated and identified. No changes to
marketplaces or advice about generating feedback.
"""
from __future__ import annotations

def quantity_audit(purchase_units: int, distinct_verified_review_ids: list[str] | None = None) -> dict:
    if isinstance(purchase_units, bool) or not isinstance(purchase_units, int) or purchase_units <= 0:
        raise ValueError("INVALID_PURCHASE_UNITS")
    count = None
    if distinct_verified_review_ids is not None:
        if not isinstance(distinct_verified_review_ids, list):
            raise ValueError("INVALID_EVIDENCE_LIST")
        if any(not isinstance(i, str) or not i.strip() for i in distinct_verified_review_ids):
            raise ValueError("INVALID_EVIDENCE_ID")
        count = len(set(distinct_verified_review_ids))
    return {
        "purchase_units": purchase_units,
        "verified_distinct_review_count": count,
        "unverified_potential_review_count": None if count is None else max(0, purchase_units - count),
        "verified_count_exceeds_unit_count": count is not None and count > purchase_units,
        "multiple_units_require_individual_review_dates": purchase_units > 1,
        "registry_single_review_date_does_not_prove_all_publications": True,
        "do_not_treat_purchase_units_as_observed_reviews": True,
        "do_not_attribute_rating_change_to_purchases_without_evidence": True,
    }
