#!/usr/bin/env python3
"""MSP-SELF-01: read-only, aggregate-only inventory of existing local MSP SQLite.

No SKU, product title, review body, URL, customer or PII values are emitted.
The output is a technical readiness snapshot, NOT a proof of organic sales.
"""
import argparse
import json
import sqlite3
from pathlib import Path

REQUIRED = ("product_listing", "self_purchase", "self_purchase_plan",
            "self_purchase_revision", "price_event", "sync_run", "sync_error")
REQUIRED_FIELDS = {
    "product_listing": ("marketplace", "store", "marketplace_sku", "first_seen_at"),
    "self_purchase": ("marketplace", "store", "marketplace_sku", "quantity", "purchase_date",
                      "review_date", "review_url"),
    "self_purchase_plan": ("marketplace", "store", "marketplace_sku", "is_current"),
    "self_purchase_revision": ("revision_id",),
    "price_event": ("source_segment", "event_date", "marketplace_sku"),
    "sync_run": ("source", "status", "finished_at", "run_id"),
    "sync_error": ("error_id",),
}


def count(con, sql):
    return int(con.execute(sql).fetchone()[0])


def audit(db):
    db = Path(db)
    if not db.is_file():
        raise FileNotFoundError("MSP database path is absent")
    # SQLite mode=ro and query_only stop writes even when called from an elevated runner.
    uri = db.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=5)
    try:
        con.execute("PRAGMA query_only=ON")
        con.execute("PRAGMA busy_timeout=5000")
        tables = {row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        missing = sorted(set(REQUIRED) - tables)
        columns = {}
        for table in REQUIRED:
            if table in tables:
                columns[table] = {row[1] for row in con.execute("PRAGMA table_info(" + table + ")")}
        missing_fields = {table: sorted(set(fields) - columns[table])
                          for table, fields in REQUIRED_FIELDS.items()
                          if table in columns and not set(fields).issubset(columns[table])}
        if missing or missing_fields:
            return {"result": "SCHEMA_GAP", "missing_tables": missing,
                    "missing_fields": missing_fields,
                    "notes": ["Missing tables or required fields; no business conclusions drawn"]}
        r = {
            "result": "PASS_READONLY",
            "read_only": True,
            "privacy": "aggregates_only_no_sku_or_product_values",
            "tables": {table: count(con, "SELECT count(*) FROM " + table) for table in REQUIRED},
        }
        r["catalog"] = {
            "listing_rows": r["tables"]["product_listing"],
            "distinct_listings": count(con, """SELECT count(*) FROM
              (SELECT marketplace,store,marketplace_sku FROM product_listing GROUP BY 1,2,3)"""),
            "missing_first_seen_at": count(con, """SELECT count(*) FROM product_listing
              WHERE first_seen_at IS NULL OR trim(first_seen_at)=''"""),
        }
        rec = con.execute("""SELECT count(*), coalesce(sum(quantity),0),
          coalesce(sum(CASE WHEN review_date IS NOT NULL AND trim(review_date)<>'' THEN 1 ELSE 0 END),0),
          coalesce(sum(CASE WHEN review_url IS NOT NULL AND trim(review_url)<>'' THEN 1 ELSE 0 END),0),
          min(purchase_date), max(purchase_date)
          FROM self_purchase""").fetchone()
        r["completed"] = {
            "events": int(rec[0]), "units": int(rec[1]),
            "rows_with_review_date": int(rec[2]),
            "rows_with_review_url": int(rec[3]),
            "first_purchase_date": rec[4], "last_purchase_date": rec[5],
            "distinct_listings": count(con, """SELECT count(*) FROM
                (SELECT marketplace,store,marketplace_sku FROM self_purchase GROUP BY 1,2,3)"""),
            "not_proven_organic": True,
        }
        r["planned"] = {
            "current_rows": count(con, "SELECT count(*) FROM self_purchase_plan WHERE is_current=1"),
            "do_not_include_in_completed_sales": True,
        }
        r["prices"] = {
            "rows": r["tables"]["price_event"],
            "first_event_date": con.execute("SELECT min(event_date) FROM price_event").fetchone()[0],
            "last_event_date": con.execute("SELECT max(event_date) FROM price_event").fetchone()[0],
        }
        r["catalog_mapping"] = {
            "completed_without_listing": count(con, """SELECT count(*) FROM self_purchase s
              LEFT JOIN product_listing p ON p.marketplace=s.marketplace AND p.store=s.store
              AND p.marketplace_sku=s.marketplace_sku WHERE p.marketplace_sku IS NULL"""),
        }
        # Only the last status per source, without source payloads or errors.
        latest = con.execute("""SELECT a.source,a.status,a.finished_at FROM sync_run a
          JOIN (SELECT source,max(run_id) rid FROM sync_run GROUP BY source) b
          ON a.source=b.source AND a.run_id=b.rid ORDER BY a.source""").fetchall()
        r["latest_syncs"] = [
            {"source": source, "status": status, "finished_at": finished_at}
            for source, status, finished_at in latest
        ]
        r["data_gaps"] = {
            "organic_sales_series": "not_proven_in_this_database",
            "competitor_series": "not_in_this_database",
            "rating_history_series": "not_proven_in_this_database",
            "marketplace_ads_series": "not_proven_in_this_database",
            "self_purchase_reason": "not_in_canonical_self_purchase_fields",
            "causal_effectiveness": "requires_comparison_groups_and_independent_sales",
        }
        r["not_business_conclusions"] = [
            "A review_date or review_url field does not establish that a genuine review was posted",
            "First_seen_at is a catalog registration timestamp, not necessarily launch date",
            "External MPSTATS and marketplace datasets require their own audit",
            "Meeting percentages 90/5/5 and 80/20 cannot be verified from event rows alone",
        ]
        return r
    finally:
        con.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    args = parser.parse_args()
    report = audit(args.db)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if report["result"] != "PASS_READONLY":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
