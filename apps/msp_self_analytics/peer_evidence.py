"""Strict, pure evidence gate for potential competitor listings.

A marketplace's 'similar' list is NOT a verified comparator. Matching structured
fields is only an invitation to independent human/source review; this module
never certifies comparators or infers effects on sales, ratings or reviews.
No networking, database queries, file writes or marketplace actions.
"""
from __future__ import annotations

from datetime import date
from math import isfinite
import re
from typing import Any


FIELDS = ("subject", "intended_use", "dimensions_mm", "material", "package_units")


def _label(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return re.sub(r"\s+", " ", value.casefold().strip()) or None


def _identity(row: dict) -> str | None:
    if not isinstance(row, dict):
        return None
    value = row.get("id", row.get("sku"))
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return str(value)
    if isinstance(value, str) and value.isascii() and value.isdecimal() and len(value) >= 6:
        return value
    return None


def _spec(row: dict, field: str):
    value = row.get(field)
    if field == "dimensions_mm":
        if not isinstance(value, (list, tuple)) or len(value) != 3:
            return None
        if any(type(v) not in (int, float) or not isfinite(v) or v <= 0 for v in value):
            return None
        return tuple(float(v) for v in value)
    if field == "package_units":
        return value if type(value) is int and value >= 1 else None
    return _label(value)


def _evidence(row: dict, field: str, today: date, max_age_days: int) -> bool:
    all_proofs = row.get("evidence")
    if not isinstance(all_proofs, dict):
        return False
    proof = all_proofs.get(field)
    if not isinstance(proof, dict):
        return False
    # A provenance marker is not independent verification of truth.
    if not _label(proof.get("source_type")) or not _label(proof.get("source_ref")):
        return False
    stamp = proof.get("observed_on")
    if not isinstance(stamp, str):
        return False
    try:
        observed = date.fromisoformat(stamp)
    except ValueError:
        return False
    return 0 <= (today - observed).days <= max_age_days


def _field_status(row: dict, today: date, max_age_days: int):
    absent, unsupported = [], []
    parsed = {}
    for field in FIELDS:
        value = _spec(row, field)
        if value is None:
            absent.append(field)
        else:
            parsed[field] = value
            if not _evidence(row, field, today, max_age_days):
                unsupported.append(field)
    return parsed, absent, unsupported


def evaluate_peer_evidence(
    own: dict, candidates: list[dict], *, as_of: str, max_candidates: int = 20,
    max_evidence_age_days: int = 90,
) -> dict:
    """Evaluate comparison prerequisites, NOT a confirmed competitor control group.

    All recognized evidence metadata must include source type, source reference
    and observation date. Still no candidate is automatically approved: actual
    intended use and product quality require separately documented human review.
    Outputs omit all product identifiers, names, raw evidence refs and prices.
    """
    if not isinstance(own, dict) or not isinstance(candidates, list):
        raise ValueError("INVALID_PEER_EVIDENCE_INPUT")
    if type(max_candidates) is not int or not 1 <= max_candidates <= 20:
        raise ValueError("INVALID_CANDIDATE_LIMIT")
    if len(candidates) > max_candidates:
        raise ValueError("CANDIDATE_LIMIT_EXCEEDED")
    if type(max_evidence_age_days) is not int or not 1 <= max_evidence_age_days <= 365:
        raise ValueError("INVALID_EVIDENCE_AGE_LIMIT")
    try:
        today = date.fromisoformat(as_of)
    except (TypeError, ValueError) as exc:
        raise ValueError("INVALID_AS_OF_DATE") from exc
    own_id = _identity(own)
    if own_id is None:
        raise ValueError("OWN_LISTING_ID_REQUIRED")
    own_fields, own_missing, own_unproven = _field_status(
        own, today, max_evidence_age_days
    )
    results = []
    seen = set()
    counts: dict[str, int] = {}
    for index, candidate in enumerate(candidates, start=1):
        status = None
        reasons: list[str] = []
        if not isinstance(candidate, dict):
            status = "INVALID_CANDIDATE"
        else:
            peer_id = _identity(candidate)
            if peer_id is None:
                status = "MISSING_ID"
            elif own_id is not None and peer_id == own_id:
                status = "OWN_LISTING_EXCLUDED"
            elif peer_id in seen:
                status = "DUPLICATE_LISTING_EXCLUDED"
            else:
                seen.add(peer_id)
                peer_fields, peer_missing, peer_unproven = _field_status(
                    candidate, today, max_evidence_age_days
                )
                if own_missing or own_unproven:
                    status = "OWN_EVIDENCE_INCOMPLETE"
                    reasons = sorted(set(own_missing + own_unproven))
                elif peer_missing or peer_unproven:
                    status = "PEER_EVIDENCE_INCOMPLETE"
                    reasons = sorted(set(peer_missing + peer_unproven))
                else:
                    mismatch = [field for field in FIELDS
                                if own_fields[field] != peer_fields[field]]
                    if mismatch:
                        status = "STRUCTURED_FIELDS_DIFFER"
                        reasons = mismatch
                    else:
                        status = "MATCHED_FIELDS_REVIEW_REQUIRED"
        counts[status] = counts.get(status, 0) + 1
        # Relative index only, never private SKU, seller, product name, price or proof.
        results.append({"candidate_number": index, "status": status,
                        "field_names_to_review": reasons,
                        "independently_verified_comparator": False})
    return {"status": "DESCRIPTIVE_EVIDENCE_SCREEN_ONLY",
            "candidate_count": len(candidates),
            "counts": dict(sorted(counts.items())),
            "candidates": results,
            "matched_field_candidate_count": counts.get("MATCHED_FIELDS_REVIEW_REQUIRED", 0),
            "verified_comparator_count": 0,
            "manual_independent_approval_required": True,
            "may_use_as_causal_control": False,
            "may_infer_review_effect": False,
            "marketplace_actions_allowed": False}
