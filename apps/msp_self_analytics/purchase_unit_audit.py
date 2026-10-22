"""Historical accounting: units purchased are not automatically public reviews.

Pure offline function. No API calls or marketplace modifications.
"""
from __future__ import annotations

def audit_units(planned_total: int, observed_review_ids: list[str] | None = None) -> dict:
    if isinstance(planned_total, bool) or not isinstance(planned_total, int) or planned_total < 1:
        raise ValueError("INVALID_PURCHASE_UNIT_COUNT")
    observed = None
    if observed_review_ids is not None:
        if not isinstance(observed_review_ids, list):
            raise ValueError("INVALID_REVIEW_EVIDENCE")
        if any(not isinstance(x, str) or not x.strip() for x in observed_review_ids):
            raise ValueError("INVALID_REVIEW_IDENTIFIER")
        observed = len(set(x.strip() for x in observed_review_ids))
    return {
        "planned_total_per_card": planned_total,
        "purchase_units": 1,
        "individually_verified_review_count": observed,
        "unmatched_units": None if observed is None else max(0,1-observed),
        "more_reviews_than_units": observed is not None and observed > 1,
        "multiple_units_single_date_ambiguous": False,
        "do_not_assume_purchases_are_reviews": True,
    }
