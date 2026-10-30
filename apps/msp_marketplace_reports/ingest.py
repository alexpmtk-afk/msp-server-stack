"""Explicit, one-cabinet manual ingestion of read-only WB/Ozon reports.

Not an automated job runner. No secret values are ever printed. Provider
completeness requires separate coverage reconciliation before COMPLETE.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import tempfile
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .archive import DEFAULT_ROOT, import_csv, _reject_versioned_scope
from .providers import (
    ProviderError, wb_discover_all, wb_detail, ozon_final_month,
    ozon_current_postings, ozon_accrual_day,
)
from .runtime import ReadOnlyHTTP, credential_status

MOSCOW = ZoneInfo("Europe/Moscow")


def _cell(value):
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def write_staging_csv(path: Path, rows: list[dict], required: tuple[str, ...]):
    """Lossless provider JSON retained in _raw_json; CSV is UTF-8-BOM / semicolon."""
    if not rows:
        raise ProviderError("source returned zero rows; explicit empty-coverage acceptance required")
    seen = set()
    for row in rows:
        key = tuple(str(row.get(f) if row.get(f) is not None else "").strip() for f in required)
        if not all(key) or key in seen:
            raise ProviderError("invalid/duplicate source stable key")
        seen.add(key)
    fields = list(dict.fromkeys([*required, *(field for row in rows for field in row)]))
    if "_raw_json" not in fields:
        fields.append("_raw_json")
    with Path(path).open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, delimiter=";", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            values = {field: _cell(row.get(field)) for field in fields}
            values["_raw_json"] = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            writer.writerow(values)


def ingest_rows(root: Path, dataset: str, cabinet: str, period: str, rows: list[dict], key: tuple[str, ...]):
    with tempfile.TemporaryDirectory(prefix="msp-report-stage-") as temp:
        path = Path(temp) / "report.csv"
        write_staging_csv(path, rows, key)
        return import_csv(root, dataset, cabinet, period, path)


def _closed_month(period: str):
    try:
        start = date.fromisoformat(period + "-01")
    except ValueError:
        raise ValueError("period must be YYYY-MM") from None
    now = datetime.now(MOSCOW).date()
    if start >= now.replace(day=1):
        raise ValueError("Ozon FINAL requires a closed month")
    return start


def run(argv=None, *, factory=ReadOnlyHTTP):
    parser = argparse.ArgumentParser(description="Explicit read-only provider trial / local archive")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--creds-file", type=Path, default=None, help="protected local JSON path, never token values")
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("credential-status", help="local presence only; no network")
    p_list = actions.add_parser("wb-list", help="read-only report discovery, no import")
    p_list.add_argument("--cabinet", required=True)
    p_list.add_argument("--year", type=int, default=2026)
    wb = actions.add_parser("wb-one", help="read and import exactly one WB reportId")
    wb.add_argument("--cabinet", required=True)
    wb.add_argument("--year", type=int, default=2026)
    wb.add_argument("--report-id", type=int, required=True)
    wb.add_argument("--report-type", type=int, choices=(1, 2), required=True, help="confirmed WB report type from report list")
    versioned_wb = actions.add_parser(
        "wb-versioned-step",
        help="explicit one-step WB durable resume/versioned archive; needs approved quota")
    versioned_wb.add_argument("--cabinet", required=True)
    versioned_wb.add_argument("--year", type=int, default=2026)
    versioned_wb.add_argument("--report-id", type=int, required=True)
    versioned_wb.add_argument("--report-type", type=int, choices=(1, 2), required=True)
    final = actions.add_parser("ozon-final-one", help="read one closed month and import")
    final.add_argument("--cabinet", required=True)
    final.add_argument("--period", required=True)
    current = actions.add_parser("ozon-current", help="read all three open-month feeds for one cabinet")
    current.add_argument("--cabinet", required=True)
    args = parser.parse_args(argv)

    if args.creds_file is None:
        raise SystemExit("protected --creds-file path is required (not a token)")
    if args.action == "credential-status":
        result = {"credentials_configured": credential_status(args.creds_file), "network_calls": 0}
    else:
        sender = factory(cabinet=args.cabinet, credentials_file=args.creds_file, state_root=args.root)
        if args.action == "wb-list":
            if not args.cabinet.startswith("wb_"):
                raise ValueError("WB cabinet required")
            values = wb_discover_all(sender, args.year)
            # The offline backfill planner requires ID/type/dates, not monetary
            # figures or any provider payload. Include an explicit metadata-only
            # inventory; this is NOT evidence of complete API coverage.
            items = [
                {"reportId": int(r["reportId"]), "reportType": int(r["reportType"]),
                 "dateFrom": str(r["dateFrom"]), "dateTo": str(r["dateTo"])}
                for r in values
            ]
            result = {"cabinet": args.cabinet, "year": args.year, "report_ids": [r["reportId"] for r in items],
                      "items": items, "reports": len(values),
                      "main": sum(r["reportType"] == 1 for r in values),
                      "buyout": sum(r["reportType"] == 2 for r in values),
                      "status": "DISCOVERED_NOT_DOWNLOADED"}
        elif args.action == "wb-one":
            # For this operator-confirmed ID, use a single report's detail endpoint.
            # The ID/type pairing must first be obtained from the provider's list.
            # Avoid a full-year rediscovery before each individual archive action.
            report_type = args.report_type
            dataset = "wb_weekly_finance_main" if report_type == 1 else "wb_weekly_finance_buyout"
            # Early read-only preflight: avoid spending provider quota on a
            # legacy write that is already known to be disallowed by B7.
            # The locked import_csv repeats the guard against races.
            _reject_versioned_scope(Path(args.root).expanduser(), dataset,
                                    args.cabinet, str(args.year))
            rows = wb_detail(sender, args.report_id, report_type)
            dataset = "wb_weekly_finance_main" if report_type == 1 else "wb_weekly_finance_buyout"
            result = ingest_rows(args.root, dataset, args.cabinet, str(args.year), rows,
                                 ("reportId", "rrdId"))
            result["report_type"] = report_type
            result["report_id"] = args.report_id
            result["status"] = "LOCAL_VERIFIED_NOT_PROVIDER_COMPLETE"
        elif args.action == "wb-versioned-step":
            # Explicit opt-in only, never silent replacement of legacy wb-one.
            # No scheduler, no retry loop, no API call without shared Redis gate.
            from .wb_worker_adapter import run_one_step
            result = run_one_step(args.root, args.cabinet, args.year,
                                  args.report_id, args.report_type, sender)
        elif args.action == "ozon-final-one":
            target = _closed_month(args.period)
            _reject_versioned_scope(Path(args.root).expanduser(),
                                    "ozon_final_realization",
                                    args.cabinet, args.period)
            rows = ozon_final_month(sender, target.year, target.month)
            result = ingest_rows(args.root, "ozon_final_realization", args.cabinet, args.period, rows,
                                 ("report_year", "report_month", "row_number"))
            result["status"] = "LOCAL_VERIFIED_NOT_PROVIDER_COMPLETE"
        else:
            now = datetime.now(MOSCOW).date()
            begin = now.replace(day=1)
            period = begin.strftime("%Y-%m")
            for candidate_dataset in (
                "ozon_current_orders_fbo", "ozon_current_orders_fbs",
                "ozon_current_accruals",
            ):
                _reject_versioned_scope(Path(args.root).expanduser(),
                                        candidate_dataset, args.cabinet, period)
            gathered = [
                ("ozon_current_orders_fbo", ozon_current_postings(sender, "fbo", begin, now), ("posting_number",)),
                ("ozon_current_orders_fbs", ozon_current_postings(sender, "fbs", begin, now), ("posting_number",)),
            ]
            accruals = []
            d = begin
            from datetime import timedelta
            while d <= now:
                accruals.extend(ozon_accrual_day(sender, d))
                d += timedelta(days=1)
            gathered.append(("ozon_current_accruals", accruals, ("accrual_id",)))
            # Validate all three datasets BEFORE modifying any canonical snapshots.
            with tempfile.TemporaryDirectory(prefix="msp-current-stage-") as td:
                staged = []
                for dataset, rows, key in gathered:
                    filename = Path(td) / (dataset + ".csv")
                    write_staging_csv(filename, rows, key)
                    staged.append((dataset, filename))
                # Multi-file publish is still non-transactional; no COMPLETE until independent verification.
                result = {"cabinet": args.cabinet, "period": period, "datasets": {}}
                for dataset, filename in staged:
                    result["datasets"][dataset] = import_csv(args.root, dataset, args.cabinet, period, filename)
                result["status"] = "LOCAL_VERIFIED_NOT_PROVIDER_COMPLETE"

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    try:
        run()
    except (ProviderError, OSError, ValueError) as exc:
        # Exceptions from provider/credentials are deliberately content-free.
        raise SystemExit("ERROR: " + str(exc)) from None
