#!/usr/bin/env python3
"""MSP-SELF-01B: deterministic, read-only QA of OWN sales, orders, stocks CSV extracts.

All inputs must be supplied as already-authorized local CSV snapshots; no network,
Google API, WB API or Ozon API access is performed. Business key: MP/store/market_article.
No SKU, product title, monetary value, or credentials are emitted by the report.
This is a source-quality check, NOT an organic-sales estimate or a forecast.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

MARKETS = ("wb", "oz")
KEY_COLUMNS = ("мп", "магазин", "market_article")


def read_csv(path: Path, delimiter: str = ",") -> tuple[list[dict], list[str]]:
    if not path.is_file():
        raise ValueError("SOURCE_FILE_UNAVAILABLE")
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file, delimiter=delimiter)
        if reader.fieldnames is None:
            raise ValueError("SOURCE_HEADER_MISSING")
        headers = [name.strip() for name in reader.fieldnames]
        if len(headers) != len(set(headers)):
            raise ValueError("DUPLICATED_SOURCE_HEADERS")
        rows = [{(key or "").strip(): value for key, value in row.items()}
                for row in reader]
    return rows, headers


def key(row: dict) -> tuple[str, str, str] | None:
    mp = str(row.get("мп") or "").strip().lower()
    store = str(row.get("магазин") or "").strip().lower()
    article = str(row.get("market_article") or "").strip()
    if mp not in MARKETS or not store or not article or not article.isascii() or not article.isdecimal():
        return None
    return mp, store, article


def amount(value: object) -> Decimal | None:
    s = str(value if value is not None else "").replace("\u00a0", "").replace(" ", "").replace(",", ".").strip()
    if not s or s.lower() in {"null", "none", "nan", "-", "—"}:
        return None
    try:
        number = Decimal(s)
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def valid_headers(headers: list[str], required: tuple[str, ...]) -> None:
    if any(name not in headers for name in required):
        raise ValueError("REQUIRED_SOURCE_HEADER_NOT_FOUND")


def index(records: list[dict]) -> tuple[dict[tuple[str, str, str], dict], dict]:
    rows = {}
    seen = Counter()
    missing = 0
    for record in records:
        # Empty trailing spreadsheet lines are not product rows.
        if not any(str(v or "").strip() for v in record.values()):
            continue
        k = key(record)
        if k is None:
            missing += 1
            continue
        seen[k] += 1
        rows.setdefault(k, record)
    duplicates = sum(c - 1 for c in seen.values() if c > 1)
    return rows, {"invalid_key_rows": missing, "duplicate_key_rows": duplicates}


def audit(catalog_path: Path, sales_path: Path, orders_path: Path, period: str,
          previous_period: str | None = None, delimiter: str = ",") -> dict:
    catalog, cat_columns = read_csv(catalog_path, delimiter)
    sales, sales_columns = read_csv(sales_path, delimiter)
    orders, order_columns = read_csv(orders_path, delimiter)
    if not period.strip():
        raise ValueError("PERIOD_REQUIRED")
    sale_current = f"Продажи (шт) {period}"
    sale_previous = f"Продажи (шт) {previous_period}" if previous_period else None
    orders_current = f"Заказы (шт) {period}"
    required_sales = KEY_COLUMNS + ("остаток ФБС", "остаток ФБО", sale_current)
    if sale_previous:
        required_sales += (sale_previous,)
    valid_headers(cat_columns, KEY_COLUMNS)
    valid_headers(sales_columns, required_sales)
    valid_headers(order_columns, KEY_COLUMNS + (orders_current,))

    cat, cat_issues = index(catalog)
    sal, sal_issues = index(sales)
    ords, ord_issues = index(orders)
    issues = {"catalog": cat_issues, "sales": sal_issues, "orders": ord_issues}
    duplicate_or_bad_key = any(any(value > 0 for value in group.values()) for group in issues.values())
    result = {
        "stage": "MSP_SELF_01B",
        "source_kind": "USER_GOOGLE_SHEET_CSV_SECONDARY_NOT_MARKETPLACE_API",
        "period": period,
        "previous_period": previous_period,
        "metric_status": "SOURCE_READ_AND_JOIN_ONLY_NO_ORGANIC_SALES_INFERENCE",
        "row_issues": issues,
        "per_marketplace": {},
        "privacy": "NO_SKU_NAMES_ORDER_IDS_OR_SALES_AMOUNTS_EXPORTED",
    }
    for mp in MARKETS:
        catkeys = {k for k in cat if k[0] == mp}
        salekeys = {k for k in sal if k[0] == mp}
        orderkeys = {k for k in ords if k[0] == mp}
        matched = catkeys & salekeys
        stats = {
            "catalog_listings": len(catkeys),
            "sales_table_listings": len(salekeys),
            "orders_table_listings": len(orderkeys),
            "sales_matched_catalog": len(matched),
            "catalog_missing_sales": len(catkeys - salekeys),
            "sales_missing_catalog": len(salekeys - catkeys),
            "orders_joined_to_sales": len(orderkeys & salekeys),
            "numeric_current_sales": 0,
            "positive_current_sales": 0,
            "numeric_previous_sales": 0,
            "positive_previous_sales": 0,
            "numeric_fbs_stock": 0,
            "numeric_fbo_stock": 0,
            "positive_fbs_stock": 0,
            "positive_fbo_stock": 0,
            "current_sales_and_positive_stock": 0,
            "current_sales_and_positive_orders_and_stock": 0,
            "invalid_current_sales_cells": 0,
            "invalid_stock_cells": 0,
        }
        for k in salekeys:
            row = sal[k]
            sold = amount(row.get(sale_current))
            fbs = amount(row.get("остаток ФБС"))
            fbo = amount(row.get("остаток ФБО"))
            prev = amount(row.get(sale_previous)) if sale_previous else None
            order = amount(ords.get(k, {}).get(orders_current))
            if sold is not None:
                stats["numeric_current_sales"] += 1
                if sold > 0:
                    stats["positive_current_sales"] += 1
            elif str(row.get(sale_current) or "").strip() not in ("", "null"):
                stats["invalid_current_sales_cells"] += 1
            if sale_previous and prev is not None:
                stats["numeric_previous_sales"] += 1
                if prev > 0:
                    stats["positive_previous_sales"] += 1
            if fbs is not None:
                stats["numeric_fbs_stock"] += 1
                if fbs > 0:
                    stats["positive_fbs_stock"] += 1
            if fbo is not None:
                stats["numeric_fbo_stock"] += 1
                if fbo > 0:
                    stats["positive_fbo_stock"] += 1
            stats["invalid_stock_cells"] += sum(
                1 for text_value, number in ((row.get("остаток ФБС"), fbs), (row.get("остаток ФБО"), fbo))
                if number is None and str(text_value or "").strip() not in ("", "null")
            )
            stock_present = any(x is not None and x > 0 for x in (fbs, fbo))
            if sold is not None and sold > 0 and stock_present:
                stats["current_sales_and_positive_stock"] += 1
                if order is not None and order > 0:
                    stats["current_sales_and_positive_orders_and_stock"] += 1
        result["per_marketplace"][mp.upper() if mp == "wb" else "OZ"] = stats
    result["result"] = "KEY_QUALITY_GAP" if duplicate_or_bad_key else "PASS_SOURCE_JOIN"
    result["limits"] = [
        "A monthly sales sheet is a secondary metric, not independently verified Marketplace API truth",
        "Current reported stock is not a historical daily availability time series",
        "Orders are not completed sales; sales data must not be assumed organic",
        "Zero sales and missing metric values have different meanings",
        "Do not infer causal self-purchase impact from these joins",
    ]
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--sales", type=Path, required=True)
    parser.add_argument("--orders", type=Path, required=True)
    parser.add_argument("--period", required=True)
    parser.add_argument("--previous-period")
    parser.add_argument("--delimiter", choices=[",", ";", "\t"], default=",")
    args = parser.parse_args()
    try:
        report = audit(args.catalog, args.sales, args.orders, args.period,
                       args.previous_period, args.delimiter)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if report["result"] == "PASS_SOURCE_JOIN" else 2
    except (ValueError, OSError) as exc:
        code = str(exc)
        if code not in {"SOURCE_FILE_UNAVAILABLE", "SOURCE_HEADER_MISSING",
                        "DUPLICATED_SOURCE_HEADERS", "REQUIRED_SOURCE_HEADER_NOT_FOUND",
                        "PERIOD_REQUIRED"}:
            code = "SOURCE_AUDIT_ERROR"
        print(json.dumps({"result": "FAIL", "error_code": code}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
