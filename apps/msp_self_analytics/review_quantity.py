"""Historical review evidence model; counts purchases without fabricating reviews.

The owner described a 1-purchased-unit : 1-expected-five-star scenario.
It is a *hypothesis* for audit/sensitivity, never proof of public feedback.
"""
from __future__ import annotations

from datetime import date


class ReviewEvidenceError(ValueError):
    pass


def _iso(value: object) -> str:
    if not isinstance(value, str):
        raise ReviewEvidenceError("REVIEW_DATE_INVALID")
    try:
        return date.fromisoformat(value.strip()).isoformat()
    except ValueError as exc:
        raise ReviewEvidenceError("REVIEW_DATE_INVALID") from exc


def review_evidence(
    purchase_units: int,
    *,
    registry_review_date: str | None,
    verified_reviews: list[dict] | None = None,
    one_unit_one_five_star_scenario: bool = True,
) -> dict:
    """Separate quantity, scenario and independently confirmed review identities.

    verified_reviews require distinct ID, date, rating (1..5), verified=True,
    linked_to_purchase=True. Never infer these fields from registry URL/date.
    """
    if isinstance(purchase_units, bool) or not isinstance(purchase_units, int) or purchase_units <= 0:
        raise ReviewEvidenceError("PURCHASE_UNITS_MUST_BE_POSITIVE_INTEGER")
    if not isinstance(one_unit_one_five_star_scenario, bool):
        raise ReviewEvidenceError("SCENARIO_FLAG_INVALID")
    reported = _iso(registry_review_date) if registry_review_date else None
    observations = verified_reviews or []
    if not isinstance(observations, list):
        raise ReviewEvidenceError("REVIEW_RECORDS_INVALID")
    verified = {}
    for record in observations:
        if not isinstance(record, dict):
            raise ReviewEvidenceError("REVIEW_RECORD_INVALID")
        # A review ID is not the marketplace SKU or the registry row ID.
        identifier = record.get("review_id")
        if not isinstance(identifier, str) or not identifier.strip():
            raise ReviewEvidenceError("VERIFIED_REVIEW_ID_REQUIRED")
        identifier = identifier.strip()
        if record.get("verified") is not True or record.get("linked_to_purchase") is not True:
            raise ReviewEvidenceError("REVIEW_PUBLICATION_AND_LINK_MUST_BE_VERIFIED")
        review_date = _iso(record.get("date"))
        rating = record.get("rating")
        if isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 5:
            raise ReviewEvidenceError("VERIFIED_RATING_MUST_BE_1_TO_5")
        observation = (review_date, rating)
        if identifier in verified and verified[identifier] != observation:
            raise ReviewEvidenceError("DUPLICATE_ID_CONFLICT")
        verified[identifier] = observation
    confirmed_count = len(verified)
    confirmed_five_stars = sum(rating == 5 for _, rating in verified.values())
    if confirmed_count > purchase_units:
        raise ReviewEvidenceError("REVIEW_COUNT_EXCEEDS_PURCHASE_UNITS_ASSUMPTION")
    confirmed_dates = sorted({d for d, _ in verified.values()})
    return {
        "purchased_unit_count": purchase_units,
        "review_date_registry": reported,
        "review_date_is_publication_proof": False,
        "one_unit_one_five_star_is_assumption": one_unit_one_five_star_scenario,
        "scenario_five_star_ceiling_not_observed": (
            purchase_units if one_unit_one_five_star_scenario else None
        ),
        "verified_distinct_review_count": confirmed_count,
        "verified_five_star_review_count": confirmed_five_stars,
        "verified_review_dates": confirmed_dates,
        "unverified_review_count": purchase_units - confirmed_count,
        "all_units_have_verified_review": confirmed_count == purchase_units,
        "one_registry_date_covers_all_units": (
            None if purchase_units > 1 else bool(reported)
        ),
        "review_timing_status": (
            "MULTIPLE_DATES_CONFIRMED" if len(confirmed_dates) > 1
            else "MULTI_UNIT_PUBLICATION_DATES_UNRESOLVED"
            if purchase_units > 1 and confirmed_count < purchase_units
            else "SINGLE_VERIFIED_DATE" if len(confirmed_dates) == 1
            else "REGISTRY_DATE_ONLY" if reported
            else "NO_REVIEW_DATE"
        ),
        "organic_reviews_derived": False,
        "purchase_units_are_confirmed_reviews": False,
        "five_star_hypothesis_is_actual_rating": False,
    }
