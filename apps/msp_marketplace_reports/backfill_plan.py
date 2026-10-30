"""Deterministic OFFLINE inventory-to-backfill plan for six WB/Ozon cabinets.

NO network, credentials, Redis, filesystem writes or provider availability
claims. Discovery inventories must come from separately approved provider
requests after P01; missing discovery is UNKNOWN, not zero reports.
A local CSV/meta checksum is not independent proof of provider completeness.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date
from pathlib import Path

from .archive import (
    CABINETS, DATASETS, _location, _ozon_annual_path, _rows,
    _verify_previous, _preflight_ozon_group,
)
from .generation_store import GenerationError, read_active
from .versioned_archive import _legacy_scope_occupied


def _scope(root, dataset, cabinet, period):
    return root / ".b7-generations" / dataset / cabinet / period


def _archived(root, dataset, cabinet, period):
    """Return (state, set of WB reportIds). Always reject mixed layouts."""
    scope_period = period[:4] if dataset == "ozon_final_realization" else period
    new = _scope(root, dataset, cabinet, scope_period)
    old = _location(root, dataset, cabinet, period)
    old_meta = old.with_name(old.name + ".meta.json")
    try:
        legacy_exists = _legacy_scope_occupied(root, dataset, cabinet, period)
    except (OSError, ValueError):
        return ("MIXED_UNSAFE" if new.exists() or new.is_symlink()
                else "VERIFY_FAILED"), set()
    if new.exists() or new.is_symlink():
        if legacy_exists:
            return "MIXED_UNSAFE", set()
        try:
            snap = read_active(root, dataset, cabinet, scope_period)
            if snap is None:
                return "MISSING", set()
            filename = ("monthly/" + period + ".csv"
                        if dataset == "ozon_final_realization" else "data.csv")
            raw = snap["files"].get(filename)
            if raw is None:
                return "MISSING", set()
            if dataset.startswith("wb_weekly_finance_"):
                _, rows = _rows(raw, DATASETS[dataset][1])
                return "LOCAL_VERIFIED", {str(key[0]) for key in rows}
            return "LOCAL_VERIFIED", set()
        except (OSError, ValueError, KeyError, TypeError):
            return "VERIFY_FAILED", set()
    if not legacy_exists:
        return "MISSING", set()
    try:
        if dataset == "ozon_final_realization":
            _preflight_ozon_group(root, cabinet, period[:4])
        _, rows = _verify_previous(old, dataset, cabinet, period, DATASETS[dataset][1])
        if not old.exists():
            return "MISSING", set()
        if dataset.startswith("wb_weekly_finance_"):
            return "LOCAL_VERIFIED", {str(key[0]) for key in rows}
        return "LOCAL_VERIFIED", set()
    except (OSError, ValueError, TypeError, KeyError):
        return "VERIFY_FAILED", set()


def _inventory(source, cabinet, year):
    """Accept one cabinet's JSON output from ingest.py wb-list.

    No hidden discovery or empty-inventory assumptions.
    """
    if source is None:
        return None
    if type(source) is not dict or source.get("cabinet") != cabinet or (
            type(source.get("year")) is not int or source["year"] != year):
        raise ValueError("WB discovery cabinet/year identity mismatch")
    if source.get("status") != "DISCOVERED_NOT_DOWNLOADED":
        raise ValueError("WB discovery status not accepted")
    rows = source.get("items")
    if type(rows) is not list:
        raise ValueError("WB discovery must include complete report metadata items")
    reports = {}
    for row in rows:
        if type(row) is not dict:
            raise ValueError("WB discovery item must be object")
        id_ = row.get("reportId")
        kind = row.get("reportType")
        if type(id_) is not int or id_ <= 0 or type(kind) is not int or kind not in (1, 2):
            raise ValueError("WB discovery reportId/reportType malformed")
        start, end = row.get("dateFrom"), row.get("dateTo")
        try:
            start = date.fromisoformat(start[:10]) if type(start) is str else None
            end = date.fromisoformat(end[:10]) if type(end) is str else None
        except ValueError:
            raise ValueError("WB report period malformed") from None
        if start is None or end is None or start > end:
            raise ValueError("WB report period missing/reversed")
        if not (start.year <= year <= end.year):
            raise ValueError("WB report does not overlap selected year")
        if id_ in reports:
            raise ValueError("WB duplicated reportId in discovery")
        reports[id_] = (kind, start, end)
    return sorted(reports.items())


def build_backfill_plan(root: Path, *, year: int, as_of: date,
                        wb_discoveries: dict | None = None):
    """Build a read-only plan. No provider calls, no COMPLETE status."""
    if type(year) is not int or year < 2024 or year > as_of.year:
        raise ValueError("invalid historical year")
    if type(as_of) is not date:
        raise ValueError("as_of date required")
    if wb_discoveries is None:
        wb_discoveries = {}
    if type(wb_discoveries) is not dict or set(wb_discoveries) - set(CABINETS["wb"]):
        raise ValueError("unexpected WB discovery cabinet")
    root = Path(root).expanduser()
    tasks = []
    for cabinet in CABINETS["wb"]:
        inventory = _inventory(wb_discoveries.get(cabinet), cabinet, year)
        if inventory is None:
            tasks.append({"marketplace": "wb", "cabinet": cabinet, "year": year,
                          "action": "DISCOVER_REPORT_IDS", "status": "DISCOVERY_REQUIRED"})
            continue
        for kind in (1, 2):
            dataset = ("wb_weekly_finance_main" if kind == 1
                       else "wb_weekly_finance_buyout")
            state, ids = _archived(root, dataset, cabinet, str(year))
            listed = [(rid, value) for rid, value in inventory if value[0] == kind]
            if state in ("MIXED_UNSAFE", "VERIFY_FAILED"):
                tasks.append({"marketplace": "wb", "cabinet": cabinet,
                              "dataset": dataset, "year": year,
                              "action": "REVIEW_ARCHIVE", "status": state})
                continue
            for rid, item in listed:
                present = str(rid) in ids
                tasks.append({"marketplace": "wb", "cabinet": cabinet,
                              "dataset": dataset, "year": year, "report_id": rid,
                              "report_type": kind, "date_from": item[1].isoformat(),
                              "date_to": item[2].isoformat(),
                              "action": "VERIFY_PROVIDER_COVERAGE" if present else "DOWNLOAD_REPORT_DETAIL",
                              "status": "LOCAL_VERIFIED_NOT_PROVIDER_COMPLETE" if present
                                        else "NOT_ARCHIVED"})
            if not listed:
                tasks.append({"marketplace": "wb", "cabinet": cabinet,
                              "dataset": dataset, "year": year,
                              "action": "REVIEW_ZERO_REPORT_DISCOVERY",
                              "status": "SOURCE_EMPTY_UNCONFIRMED"})
    # Ozon FINAL: only closed months, never count open month as missing FINAL.
    last_month = (12 if year < as_of.year else as_of.month - 1)
    for cabinet in CABINETS["ozon"]:
        for month in range(1, last_month + 1):
            period = "%04d-%02d" % (year, month)
            state, _ = _archived(root, "ozon_final_realization", cabinet, period)
            tasks.append({"marketplace": "ozon", "cabinet": cabinet,
                          "dataset": "ozon_final_realization", "period": period,
                          "action": "VERIFY_PROVIDER_COVERAGE" if state == "LOCAL_VERIFIED"
                                    else ("DOWNLOAD_CLOSED_MONTH" if state == "MISSING"
                                          else "REVIEW_ARCHIVE"),
                          "status": ("LOCAL_VERIFIED_NOT_PROVIDER_COMPLETE" if state == "LOCAL_VERIFIED"
                                     else state)})
        if year == as_of.year:
            period = as_of.strftime("%Y-%m")
            for dataset in ("ozon_current_orders_fbo", "ozon_current_orders_fbs",
                            "ozon_current_accruals"):
                state, _ = _archived(root, dataset, cabinet, period)
                tasks.append({"marketplace": "ozon", "cabinet": cabinet,
                              "dataset": dataset, "period": period,
                              "action": "VERIFY_PROVIDER_COVERAGE" if state == "LOCAL_VERIFIED"
                                        else ("DOWNLOAD_CURRENT" if state == "MISSING"
                                              else "REVIEW_ARCHIVE"),
                              "status": ("LOCAL_VERIFIED_NOT_PROVIDER_COMPLETE"
                                         if state == "LOCAL_VERIFIED" else state)})
    totals = Counter(t["action"] for t in tasks)
    return {"schema": 1, "year": year, "as_of": as_of.isoformat(),
            "provider_coverage_proven": False, "network_calls": 0,
            "cabinet_count": 6, "tasks": tasks,
            "action_counts": dict(sorted(totals.items()))}


def main(argv=None):
    p = argparse.ArgumentParser(description="READ-ONLY WB/Ozon yearly gap plan: no API")
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--year", type=int, default=2026)
    p.add_argument("--as-of", type=date.fromisoformat, required=True)
    p.add_argument("--wb-inventory-json", type=Path,
                   help="optional JSON object mapping each WB cabinet to wb-list output")
    args = p.parse_args(argv)
    inventory = (json.loads(args.wb_inventory_json.read_text("utf-8"))
                 if args.wb_inventory_json is not None else None)
    result = build_backfill_plan(args.root, year=args.year,
                                 as_of=args.as_of, wb_discoveries=inventory)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
