"""Pure read-only prefilter for possible competitor listings.

MPSTATS' 'similar' relation or matching subject cannot establish that two
goods have equal purpose, dimensions, composition, pack size or sale conditions.
No marketplace mutations, expert approvals or causal conclusions.
"""
from __future__ import annotations
from collections import Counter
import re
from typing import Any


def _text(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("name", "description", "title"):
            if isinstance(value.get(key), str):
                value = value[key]
                break
    if not isinstance(value, str):
        return None
    normalized = re.sub(r"\s+", " ", value.casefold().strip())
    return normalized or None


def _identity(row: dict) -> int | None:
    if not isinstance(row, dict):
        return None
    for key in ("id", "sku", "nm_id", "nmId", "product_id", "productId"):
        value = row.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
        if isinstance(value, str) and value.isdecimal() and 6 <= len(value) <= 15:
            return int(value)
    return None


def prefilter(own: dict, candidates: list[dict], *, max_candidates: int = 20) -> dict:
    """Count potential analogs by a narrowly proved shared subject.

    Returns aggregates, deliberately not SKUs, product names, seller IDs,
    prices or text. Even perfect subject matches remain UNVERIFIED.
    """
    if not isinstance(own, dict) or not isinstance(candidates, list):
        raise ValueError("INVALID_PEER_INPUT")
    if (isinstance(max_candidates, bool) or not isinstance(max_candidates, int)
            or max_candidates <= 0):
        raise ValueError("INVALID_CANDIDATE_LIMIT")
    if len(candidates) > max_candidates:
        raise ValueError("CANDIDATE_LIMIT_EXCEEDED")
    own_id = _identity(own)
    own_subject = _text(own.get("subject"))
    own_subject_id = own.get("subject_id")
    counts = Counter()
    seen = set()
    for item in candidates:
        if not isinstance(item, dict):
            counts["INVALID_ROW"] += 1
            continue
        ident = _identity(item)
        if ident is None:
            counts["MISSING_PRODUCT_ID"] += 1
            continue
        if own_id is not None and ident == own_id:
            counts["OWN_PRODUCT_EXCLUDED"] += 1
            continue
        if ident in seen:
            counts["DUPLICATE_EXCLUDED"] += 1
            continue
        seen.add(ident)
        peer_subject = _text(item.get("subject"))
        peer_subject_id = item.get("subject_id")
        if (own_subject_id is not None and peer_subject_id is not None
                and str(own_subject_id) != str(peer_subject_id)):
            counts["SUBJECT_ID_DIFFERENT"] += 1
        elif own_subject and peer_subject:
            counts["SUBJECT_NAME_MATCH"] += bool(own_subject == peer_subject)
            counts["SUBJECT_NAME_DIFFERENT"] += bool(own_subject != peer_subject)
        else:
            counts["SUBJECT_UNKNOWN"] += 1
    result = {
        "candidate_count": len(candidates),
        "unique_identified_external_candidates": len(seen),
        "subject_name_usable_on_own_card": own_subject is not None,
        "subject_id_usable_on_own_card": own_subject_id is not None,
        "counts": {k: int(v) for k, v in sorted(counts.items())},
        "automatically_verified_competitors": 0,
        "validation": "PRELIMINARY_SUBJECT_ONLY",
        "category_and_intended_use_independently_verified": False,
        "product_characteristics_independently_verified": False,
        "price_and_package_size_comparability_verified": False,
        "can_compute_peer_control_comparison": False,
    }
    return result
