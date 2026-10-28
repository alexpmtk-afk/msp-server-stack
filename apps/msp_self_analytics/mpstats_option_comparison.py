"""Pure, value-private comparison of two MPSTATS wb_card_content snapshots.

Reads the observed options list of name/value pairs for own and external cards.
Repeated section options are deduplicated. The result NEVER exports
characteristic values, SKU, product name or vendor. Matching visible fields
are not proof of interchangeable products.
"""
from __future__ import annotations

from math import isfinite
import re
from typing import Any

FIELDS = {
    "material": ("Материал изделия",),
    "volume_l": ("Объем (л)", "Объём (л)"),
    "item_height": ("Высота предмета",),
    "item_width": ("Ширина предмета",),
    "mounting": ("Тип установки",),
    "kit": ("Комплектация",),
    "color": ("Цвет",),
    "country": ("Страна производства",),
    "package_length": ("Длина упаковки",),
    "package_width": ("Ширина упаковки",),
    "package_height": ("Высота упаковки",),
    "package_weight_kg": ("Вес с упаковкой (кг)",),
    "extra_options": ("Доп. опции ведра",),
    "shape": ("Форма",),
    "bucket_type": ("Тип ведра",),
}
PACKAGE_FIELDS = {"package_length", "package_width", "package_height", "package_weight_kg"}
ITEM_DIMENSION_FIELDS = {"item_height", "item_width"}
LABEL_MAP = {
    re.sub(r"\s+", " ", v.strip().casefold()).replace("ё", "е"): field
    for field, labels in FIELDS.items() for v in labels
}


def _label(v: Any) -> str | None:
    if not isinstance(v, str):
        return None
    x = re.sub(r"\s+", " ", v.strip().casefold()).replace("ё", "е")
    return x or None


def _value(v: Any) -> str | None:
    """Format simple nonempty values for private in-memory equality only."""
    if isinstance(v, str):
        t = _label(v)
        return t if t and len(t) <= 500 else None
    if type(v) is int:
        return str(v)
    if type(v) is float and isfinite(v):
        return format(v, ".15g")
    if isinstance(v, list) and 0 < len(v) <= 20:
        parts = [_value(item) for item in v]
        if any(part is None for part in parts):
            return None
        return "\0".join(sorted(set(parts)))
    return None


def _extract(payload: Any) -> tuple[dict[str, set[str]], dict[str, int], int]:
    values: dict[str, set[str]] = {field: set() for field in FIELDS}
    unreadable: dict[str, int] = {field: 0 for field in FIELDS}
    observed = 0
    scanned = 0

    def visit(x: Any, depth: int = 0):
        nonlocal observed, scanned
        if depth > 6 or scanned >= 1000:
            return
        scanned += 1
        if isinstance(x, dict):
            for key, item in x.items():
                if isinstance(key, str) and key.casefold() == "options" and isinstance(item, list):
                    for row in item[:150]:
                        if not isinstance(row, dict):
                            continue
                        label = _label(row.get("name"))
                        field = LABEL_MAP.get(label)
                        if field is None:
                            continue
                        observed += 1
                        normalized = _value(row.get("value"))
                        if normalized is None:
                            unreadable[field] += 1
                        else:
                            values[field].add(normalized)
                if isinstance(item, (dict, list)):
                    visit(item, depth+1)
        elif isinstance(x, list):
            for item in x[:150]:
                visit(item, depth+1)

    visit(payload)
    return values, unreadable, observed


def compare_option_snapshots(own: dict, peer: dict) -> dict:
    """Compare MPSTATS options, preserving missing and conflicting source data.

    Snapshot is undated unless the calling source separately establishes the
    observation date. No historical characteristic claims are permitted.
    """
    if not isinstance(own, dict) or not isinstance(peer, dict):
        raise ValueError("STRUCTURED_CARD_PAYLOADS_REQUIRED")
    own_values, own_unreadable, own_seen = _extract(own)
    peer_values, peer_unreadable, peer_seen = _extract(peer)
    comparisons = {}
    counts = {k: 0 for k in ("MATCH", "DIFFERENT", "ONLY_OWN", "ONLY_PEER",
                              "BOTH_MISSING", "AMBIGUOUS")}
    for field in FIELDS:
        left, right = own_values[field], peer_values[field]
        if len(left) > 1 or len(right) > 1:
            status = "AMBIGUOUS"
        elif (own_unreadable[field] and not left) or (peer_unreadable[field] and not right):
            status = "AMBIGUOUS"
        elif not left and not right:
            status = "BOTH_MISSING"
        elif not left:
            status = "ONLY_PEER"
        elif not right:
            status = "ONLY_OWN"
        elif left == right:
            status = "MATCH"
        else:
            status = "DIFFERENT"
        counts[status] += 1
        comparisons[field] = {
            "status": status,
            "own_value_available": bool(left),
            "peer_value_available": bool(right),
            "is_packaging_not_item_dimension": field in PACKAGE_FIELDS,
            "item_dimension_unit_explicit": False if field in ITEM_DIMENSION_FIELDS else None,
            "source": "MPSTATS_WB_CARD_CONTENT_OPTIONS",
        }
    return {
        "status": "OBSERVED_OPTIONS_SNAPSHOT_ONLY",
        "own_labeled_rows_seen_including_repeated_sections": own_seen,
        "peer_labeled_rows_seen_including_repeated_sections": peer_seen,
        "fields": comparisons,
        "counts": counts,
        "item_dimension_completeness": "NOT_THREE_DIMENSIONS",
        "historic_attributes_verified": False,
        "verified_comparable_competitors": 0,
        "safe_for_causal_control_group": False,
        "automated_marketplace_actions": False,
    }
