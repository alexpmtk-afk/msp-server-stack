"""Pure classification of historical reviews, distinct from the underlying purchase.

The source's 'Дата отзыва' is a registry-reported date; it does not alone prove
that the rating was visible publicly on that exact calendar day. Never guess
a review date from a purchase, a URL, or a model response.
"""
from __future__ import annotations

from datetime import date


def _date(value):
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError("INVALID_DATE_TYPE")
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError("INVALID_DATE_FORMAT") from exc


def classify_review_event(
    purchase_date: str | None,
    review_date: str | None,
    *,
    publication_date_verified: str | None = None,
    review_url_present: bool = False,
) -> dict:
    purchase = _date(purchase_date)
    reported = _date(review_date)
    verified = _date(publication_date_verified)
    info = {
        "purchase_date": purchase.isoformat() if purchase else None,
        "review_date_registry": reported.isoformat() if reported else None,
        "review_publication_date_verified": verified.isoformat() if verified else None,
        "review_url_present": bool(review_url_present),
        "anchor_date": None,
        "date_quality": "UNKNOWN",
        "analyze_review_outcome": False,
        "status": "REVIEW_DATE_NOT_RECORDED",
        "days_between_purchase_and_review": None,
    }
    if purchase is None:
        info["status"] = "PURCHASE_NOT_CONFIRMED"
        return info
    if verified is not None and reported is None:
        # Evidence of a date is useful, but do not silently mutate the registry:
        # such disagreement needs human review before anchoring.
        info["status"] = "SOURCE_DATE_MISMATCH"
        return info
    if reported is None:
        return info
    if reported < purchase or (verified is not None and verified < purchase):
        info["status"] = "INVALID_DATE_ORDER"
        return info
    if verified is not None and verified != reported:
        info["status"] = "SOURCE_DATE_MISMATCH"
        return info
    info["days_between_purchase_and_review"] = (reported - purchase).days
    info["anchor_date"] = reported.isoformat()
    info["date_quality"] = (
        "PUBLICATION_VERIFIED" if verified is not None else "REGISTRY_REPORTED_NOT_VERIFIED"
    )
    info["status"] = (
        "READY_VERIFIED_PUBLICATION" if verified is not None
        else "READY_REGISTRY_DATE_WITH_UNCERTAINTY"
    )
    info["analyze_review_outcome"] = True
    return info
