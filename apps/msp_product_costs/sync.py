#!/usr/bin/env python3
"""MSP five-source cost catalog. No existing catalog/table is changed or deleted.

Supports the same unauthenticated CSV export as the four existing MSP sources,
when authorized by the actual Google Sheets sharing configuration. OAuth remains
an alternative. Credentials, sheet IDs and business costs never enter public Git.
"""
from __future__ import annotations

import argparse
import csv
import io
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
from urllib.parse import quote
import urllib.request

SPECS = {
    "ultra": ("MSP_COST_MAIN_SHEET_ID", "Ultra24", "production", "A:D"),
    "zavoz": ("MSP_COST_MAIN_SHEET_ID", "Zavoz24", "production", "A:D"),
    "more": ("MSP_COST_MAIN_SHEET_ID", "MORE", "production", "A:D"),
    "laser_old": ("MSP_COST_LASER_SHEET_ID", "Лазер-Мастер", "with_profit_legacy", "A:D"),
    "laser_new": ("MSP_COST_LASER_SHEET_ID", "Себес без прибыли", "without_profit_current", "E:F|AL:AL"),
}
CSV_SOURCE_GIDS = {
    "ultra": "523610665",
    "zavoz": "1599109239",
    "more": "1359789938",
    "laser_old": "1275505714",
    "laser_new": "1005435771",
}

SOURCE_HEADERS = {
    "ultra": ("Артикул", "Название товара", "Себестоимость"),
    "zavoz": ("Артикул", "Название товара", "Себестоимость"),
    "more": ("Артикул", "Название товара", "Себестоимость"),
    "laser_old": ("Артикулы", "Название товара", "Себестоимость"),
    "laser_new": ("Артикул", "Наименование", "Себестоимость без прибыли"),
}
SCHEMA = """
CREATE TABLE IF NOT EXISTS product_cost_current(
 production TEXT NOT NULL, variant TEXT NOT NULL, article_key TEXT NOT NULL,
 internal_article TEXT NOT NULL, product_name TEXT, cost_decimal TEXT NOT NULL,
 specification_url TEXT, source_sheet TEXT NOT NULL, source_row INTEGER NOT NULL,
 first_observed_at TEXT NOT NULL, last_changed_at TEXT NOT NULL,
 last_seen_run INTEGER NOT NULL,
 PRIMARY KEY(production,variant,article_key)
);
CREATE TABLE IF NOT EXISTS product_cost_revision(
 revision_id INTEGER PRIMARY KEY AUTOINCREMENT,
 production TEXT NOT NULL, variant TEXT NOT NULL, article_key TEXT NOT NULL,
 prior_cost_decimal TEXT NOT NULL, updated_cost_decimal TEXT NOT NULL,
 changed_at TEXT NOT NULL, source_row INTEGER NOT NULL, run_id INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_product_cost_rev_lookup
 ON product_cost_revision(production,variant,article_key,revision_id);
CREATE TABLE IF NOT EXISTS product_cost_run(
 run_id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL,
 observed_at TEXT NOT NULL, status TEXT NOT NULL, source_rows INTEGER NOT NULL,
 accepted INTEGER NOT NULL DEFAULT 0, inserted INTEGER NOT NULL DEFAULT 0,
 changed INTEGER NOT NULL DEFAULT 0, unchanged INTEGER NOT NULL DEFAULT 0,
 rejected INTEGER NOT NULL DEFAULT 0, error_class TEXT
);
CREATE TABLE IF NOT EXISTS product_cost_run_issue(
 run_id INTEGER NOT NULL, source TEXT NOT NULL, source_row INTEGER,
 reason TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_product_cost_issue_run ON product_cost_run_issue(run_id);
CREATE VIEW IF NOT EXISTS v_product_cost_current AS
 SELECT production,variant,internal_article,article_key,product_name,
 cost_decimal,specification_url,source_sheet,source_row,
 first_observed_at,last_changed_at,last_seen_run FROM product_cost_current;
CREATE VIEW IF NOT EXISTS v_product_cost_listing_matches AS
 SELECT c.production,c.variant,c.internal_article,c.cost_decimal,
 p.marketplace,p.store,p.marketplace_sku,
 CASE WHEN p.marketplace_sku IS NULL THEN 'unmatched' ELSE 'matched' END AS link_status
 FROM product_cost_current c LEFT JOIN product_listing p
 ON c.article_key=lower(trim(p.internal_article_normalized));
"""
def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def key(article):
    return str(article).strip().casefold()

def decimal_cost(raw):
    s = str(raw if raw is not None else "").replace("\u00a0", "").replace("\u202f", "").replace(" ", "").strip().replace(",", ".")
    if not re.fullmatch(r"\d+(?:\.\d+)?", s):
        raise ValueError("non-numeric or missing cost")
    try:
        d = Decimal(s)
    except InvalidOperation as e:
        raise ValueError("invalid decimal cost") from e
    if not d.is_finite() or d <= 0:
        raise ValueError("cost must be positive")
    return format(d, "f")

def _cell(row, index):
    return row[index] if len(row) > index else ""

def parse_rows(source, rows):
    """Return valid source records plus source-row issue list; only designated columns."""
    if source not in SPECS:
        raise ValueError("unknown cost source")
    header = rows[0] if rows else []
    expected = SOURCE_HEADERS[source]
    if source == "laser_new":
        actual = (_cell(header, 0), _cell(header, 1), _cell(header, 2))
    else:
        actual = tuple(_cell(header, j) for j in (0, 1, 2))
    if tuple(str(x).strip().replace("\n", " ") for x in actual) != expected:
        raise ValueError("unexpected source headers")
    records, issues = [], []
    counts = Counter(key(_cell(r, 0)) for r in rows[1:] if str(_cell(r, 0)).strip())
    for pos, r in enumerate(rows[1:], start=2):
        article = str(_cell(r, 0)).strip()
        if not article:
            continue
        article_key = key(article)
        if counts[article_key] > 1:
            issues.append((pos, "duplicate internal article in same source"))
            continue
        try:
            cost = decimal_cost(_cell(r, 2))
        except ValueError:
            issues.append((pos, "cost absent, nonnumeric or nonpositive"))
            continue
        records.append({
            "production": "laser" if source.startswith("laser_") else source,
            "variant": SPECS[source][2],
            "article_key": article_key,
            "internal_article": article,
            "product_name": str(_cell(r, 1)).strip() or None,
            "cost_decimal": cost,
            "specification_url": (str(_cell(r, 3)).strip() if str(_cell(r, 3)).strip().startswith(("https://", "http://")) else None) if source != "laser_new" else None,
            "source_sheet": SPECS[source][1], "source_row": pos,
        })
    return records, issues

def store_source(con, source, records, issues, observed_at, source_rows):
    con.executescript(SCHEMA)
    with con:
        cur = con.execute("INSERT INTO product_cost_run(source,observed_at,status,source_rows) VALUES(?,?,'running',?)",
                          (source, observed_at, source_rows))
        run_id = cur.lastrowid
        inserted = changed = unchanged = 0
        for item in records:
            identity = (item["production"], item["variant"], item["article_key"])
            current = con.execute(
                "SELECT internal_article,product_name,cost_decimal,specification_url "
                "FROM product_cost_current WHERE production=? AND variant=? AND article_key=?",
                identity).fetchone()
            nextvalue = (item["internal_article"], item["product_name"],
                         item["cost_decimal"], item["specification_url"])
            if current is None:
                con.execute("INSERT INTO product_cost_current("
                            "production,variant,article_key,internal_article,product_name,"
                            "cost_decimal,specification_url,source_sheet,source_row,"
                            "first_observed_at,last_changed_at,last_seen_run)"
                            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                            (*identity,*nextvalue,item["source_sheet"],item["source_row"],
                             observed_at,observed_at,run_id))
                inserted += 1
            elif current != nextvalue:
                if current[2] != item["cost_decimal"]:
                    con.execute("INSERT INTO product_cost_revision("
                                "production,variant,article_key,prior_cost_decimal,updated_cost_decimal,"
                                "changed_at,source_row,run_id) VALUES(?,?,?,?,?,?,?,?)",
                                (*identity,current[2],item["cost_decimal"],observed_at,item["source_row"],run_id))
                con.execute("UPDATE product_cost_current SET internal_article=?,product_name=?,"
                            "cost_decimal=?,specification_url=?,source_sheet=?,source_row=?,"
                            "last_changed_at=?,last_seen_run=? WHERE production=? AND variant=? AND article_key=?",
                            (*nextvalue,item["source_sheet"],item["source_row"],observed_at,run_id,*identity))
                changed += 1
            else:
                con.execute("UPDATE product_cost_current SET last_seen_run=? "
                            "WHERE production=? AND variant=? AND article_key=?", (run_id,*identity))
                unchanged += 1
        for pos,reason in issues:
            con.execute("INSERT INTO product_cost_run_issue(run_id,source,source_row,reason) VALUES(?,?,?,?)",
                        (run_id,source,pos,reason))
        status = "partial" if issues else "success"
        con.execute("UPDATE product_cost_run SET status=?,accepted=?,inserted=?,changed=?,"
                    "unchanged=?,rejected=? WHERE run_id=?",
                    (status,len(records),inserted,changed,unchanged,len(issues),run_id))
    return dict(source=source, status=status, accepted=len(records),
                inserted=inserted, changed=changed, unchanged=unchanged, rejected=len(issues))

def mark_fetch_failure(con, source, observed_at, error_class):
    con.executescript(SCHEMA)
    with con:
        con.execute("INSERT INTO product_cost_run(source,observed_at,status,source_rows,error_class) "
                    "VALUES(?,?,'failed',0,?)", (source, observed_at, error_class))
    return dict(source=source, status="failed", error_class=error_class)

def google_auth_mode(metadata):
    """Allow exactly trusted Google OAuth user or service account credential types."""
    if not isinstance(metadata, dict):
        raise ValueError("invalid Google credential envelope")
    mode = metadata.get("type")
    if mode not in ("authorized_user", "service_account"):
        raise ValueError("unsupported Google credential type")
    return mode


def _google_session():
    from google.oauth2 import credentials as user_credentials, service_account
    from google.auth.transport.requests import AuthorizedSession
    env_name = ("MSP_COST_GOOGLE_CREDENTIALS_FILE"
                if "MSP_COST_GOOGLE_CREDENTIALS_FILE" in os.environ
                else "MSP_COST_GOOGLE_SERVICE_ACCOUNT_FILE")
    loc = Path(os.environ[env_name])
    if loc.is_symlink():
        raise RuntimeError("Google credential path must not be a symlink")
    meta = loc.stat()
    if meta.st_uid != os.getuid() or stat.S_IMODE(meta.st_mode) != 0o600 or not loc.is_file():
        raise RuntimeError("protected Google credential must be regular user-owned 0600 file")
    # Select only known Google credential types, not generic untrusted credential
    # loaders that can accept external-account URLs.
    with loc.open(encoding="utf-8") as stream:
        mode = google_auth_mode(json.load(stream))
    scope = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    if mode == "authorized_user":
        creds = user_credentials.Credentials.from_authorized_user_file(str(loc), scopes=scope)
    else:
        creds = service_account.Credentials.from_service_account_file(str(loc), scopes=scope)
    return AuthorizedSession(creds)

def _get_values(session, sheet_id, sheet, range_cols):
    a1 = "'" + sheet.replace("'", "''") + "'!" + range_cols
    url = "https://sheets.googleapis.com/v4/spreadsheets/" + quote(sheet_id,safe="") + "/values/" + quote(a1,safe="")
    response = session.get(url,params={"majorDimension":"ROWS"},timeout=45)
    response.raise_for_status()
    return response.json().get("values", [])

def fetch_sheet(session, source):
    envname, sheet, variant, cols = SPECS[source]
    sheet_id = os.environ[envname]
    if not sheet_id.strip():
        raise ValueError("missing source spreadsheet configuration")
    if source != "laser_new":
        return _get_values(session,sheet_id,sheet,cols)
    # Two disjoint ranges. Join by absolute sheet row index, not by nonempty-row ordinal.
    articles = _get_values(session,sheet_id,sheet,"E:F")
    costs = _get_values(session,sheet_id,sheet,"AL:AL")
    length = max(len(articles),len(costs))
    return [[_cell(articles[i] if i<len(articles) else [],0),
             _cell(articles[i] if i<len(articles) else [],1),
             _cell(costs[i] if i<len(costs) else [],0)] for i in range(length)]

def transform_csv(source, csv_bytes):
    """Parse existing-style CSV; do not emit or persist source payload."""
    if len(csv_bytes) > 20_000_000:
        raise ValueError("CSV exceeds 20MB safety limit")
    decoded = csv_bytes.decode("utf-8-sig")
    if "<html" in decoded[:300].lower() or "<!doctype html" in decoded[:300].lower():
        raise ValueError("Google returned HTML/login instead of CSV")
    rows = list(csv.reader(io.StringIO(decoded, newline="")))
    if source == "laser_new":
        # The source carries product article at E, name at F, cost at AL (38th).
        # Use absolute row positions; never align after dropping empty cells.
        return [[_cell(r, 4), _cell(r, 5), _cell(r, 37)] for r in rows]
    return [[_cell(r, i) for i in range(4)] for r in rows]


def fetch_sheet_csv(source):
    """Unauthenticated legacy CSV export: succeeds only when Google already permits it."""
    if source not in SPECS:
        raise ValueError("unknown cost source")
    env_name = SPECS[source][0]
    sheet_id = os.environ[env_name].strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,120}", sheet_id):
        raise ValueError("invalid configured spreadsheet ID")
    gid = CSV_SOURCE_GIDS[source]
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
    req = urllib.request.Request(url, headers={"User-Agent": "msp-data-sync/1.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        content_type = response.headers.get("Content-Type", "").lower()
        if "csv" not in content_type and "application/octet-stream" not in content_type:
            raise ValueError("Google did not return a CSV response")
        body = response.read(20_000_001)
    return transform_csv(source, body)


def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument("--db",help="Existing protected MSP SQLite database path")
    ap.add_argument("--fixture", help="Offline JSON map of source to cell rows; no Google auth")
    ap.add_argument("--preflight",action="store_true",help="Read-only fetch and source validation, no SQLite opened")
    a=ap.parse_args(argv)
    if not a.preflight and not a.db:
        ap.error("--db is required unless --preflight")
    transport = os.environ.get("MSP_COST_TRANSPORT", "oauth").strip().lower()
    if transport not in ("oauth", "csv"):
        ap.error("MSP_COST_TRANSPORT must be oauth or csv")
    when=utcnow()
    rows_by_source = json.loads(Path(a.fixture).read_text(encoding="utf-8")) if a.fixture else None
    # Import lazily so offline tests need no Google dependencies.
    session = _google_session() if rows_by_source is None and transport=="oauth" else None
    if not a.preflight and not Path(a.db).is_file():
        raise RuntimeError("existing protected MSP SQLite database not found; refusing to create a replacement")
    con = None if a.preflight else sqlite3.connect("file:" + str(Path(a.db).resolve()) + "?mode=rw", uri=True, timeout=30)
    try:
        if con is not None:
            if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("existing MSP SQLite integrity check failed")
            for table in ("product_listing", "sync_run"):
                if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is None:
                    raise RuntimeError("expected existing MSP table missing: " + table)
        results=[]
        for source in SPECS:
            try:
                rows = (rows_by_source[source] if rows_by_source is not None else
                        fetch_sheet_csv(source) if transport=="csv" else
                        fetch_sheet(session,source))
                if len(rows)<2:
                    raise ValueError("empty source or missing header/data")
                records, issues = parse_rows(source,rows)
                if a.preflight:
                    results.append(dict(source=source,status="partial" if issues else "success",accepted=len(records),rejected=len(issues),read_only=True))
                else:
                    results.append(store_source(con,source,records,issues,when,len(rows)-1))
            except Exception as e:
                # Exceptions are deliberately NOT printed: URL/credential data might occur in a transport error.
                if a.preflight:
                    results.append(dict(source=source,status="failed",error_class=type(e).__name__,read_only=True))
                else:
                    results.append(mark_fetch_failure(con,source,when,type(e).__name__))
        print(json.dumps({"product_cost_sync":results},ensure_ascii=False))
        return 1 if any(x["status"]!="success" for x in results) else 0
    finally:
        if con is not None:
            con.close()
        if session is not None:
            session.close()

if __name__=="__main__":
    sys.exit(main())
