#!/usr/bin/env python3
"""MSP production source warehouse, separate sewing and metal catalogs.

Read-only Google CSV input; additive MSP SQLite tables. Never replace existing
MSP catalogs, infer absent dates, or merge repeated SKUs/order numbers.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from urllib.request import Request, urlopen

SOURCES = {
    "sewing": {
        "sheet_env": "MSP_PRODUCTION_SEWING_SHEET_ID",
        "gid": "666345199",
        "sheet": "ГЗП МП/ОРК 25",
        "table": "production_sewing_order",
        "width": 11,
        "headers": ("Заказчик", "Артикул", "Название товара", "Кол-во",
                    "Отдали Факт", "Дата размещения заказа", "N заказа",
                    "Желаемый срок", "Подтвержденный срок",
                    "Комментарий для внеплановых договоренностей", "Ответственный"),
        "min_rows": 500,
    },
    "metal": {
        "sheet_env": "MSP_PRODUCTION_METAL_SHEET_ID",
        "gid": "1990590773",
        "sheet": "Загрузка ЛМ/АНТ",
        "table": "production_metal_order",
        "width": 13,
        "headers": ("А", "Производство", "Артикул", "Название товара",
                    "Кол-во", "Приняли Факт", "Осталось",
                    "Дата размещения заказа", "№ накладной", "№ заказа",
                    "Желаемый срок", "Комментарий", "Подтвержденный срок"),
        "min_rows": 500,
    },
}
COMMON = """
 source_row INTEGER PRIMARY KEY,
 requester TEXT, production_site TEXT, internal_article TEXT,
 product_name TEXT, order_number TEXT, invoice_number TEXT,
 requested_qty_raw TEXT, delivered_qty_raw TEXT, remainder_qty_raw TEXT,
 requested_qty_decimal TEXT, delivered_qty_decimal TEXT, remainder_qty_decimal TEXT,
 placed_at_raw TEXT, placed_at_iso TEXT,
 desired_at_raw TEXT, desired_at_iso TEXT,
 confirmed_at_raw TEXT, confirmed_at_iso TEXT,
 comment_text TEXT, responsible TEXT,
 data_quality TEXT NOT NULL, issues_json TEXT NOT NULL,
 raw_cells_json TEXT NOT NULL, row_sha256 TEXT NOT NULL,
 first_observed_at TEXT NOT NULL, last_changed_at TEXT NOT NULL,
 last_seen_run INTEGER NOT NULL,
 is_current INTEGER NOT NULL DEFAULT 1 CHECK(is_current IN (0,1))
"""
SCHEMA = """
CREATE TABLE IF NOT EXISTS production_sewing_order (""" + COMMON + """);
CREATE TABLE IF NOT EXISTS production_metal_order (""" + COMMON + """);
CREATE TABLE IF NOT EXISTS production_import_run(
 run_id INTEGER PRIMARY KEY AUTOINCREMENT,
 source TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT,
 status TEXT NOT NULL, source_rows INTEGER NOT NULL DEFAULT 0,
 present_rows INTEGER NOT NULL DEFAULT 0,
 missing_article_rows INTEGER NOT NULL DEFAULT 0,
 issue_rows INTEGER NOT NULL DEFAULT 0,
 inserted INTEGER NOT NULL DEFAULT 0, changed INTEGER NOT NULL DEFAULT 0,
 unchanged INTEGER NOT NULL DEFAULT 0, retired INTEGER NOT NULL DEFAULT 0,
 error_class TEXT
);
CREATE TABLE IF NOT EXISTS production_row_revision(
 id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL,
 source_row INTEGER NOT NULL, previous_sha256 TEXT,
 next_sha256 TEXT NOT NULL, old_values_json TEXT,
 new_values_json TEXT NOT NULL,
 changed_at TEXT NOT NULL, run_id INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_production_revision
 ON production_row_revision(source,source_row,run_id);
CREATE TABLE IF NOT EXISTS production_data_issue(
 run_id INTEGER NOT NULL, source TEXT NOT NULL,
 source_row INTEGER NOT NULL, issue_code TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_production_issues_run
 ON production_data_issue(run_id,source);
CREATE VIEW IF NOT EXISTS v_production_sewing AS
 SELECT * FROM production_sewing_order WHERE is_current=1;
CREATE VIEW IF NOT EXISTS v_production_metal AS
 SELECT * FROM production_metal_order WHERE is_current=1;
"""
COLUMNS = (
    "source_row", "requester", "production_site", "internal_article",
    "product_name", "order_number", "invoice_number",
    "requested_qty_raw", "delivered_qty_raw", "remainder_qty_raw",
    "requested_qty_decimal", "delivered_qty_decimal", "remainder_qty_decimal",
    "placed_at_raw", "placed_at_iso", "desired_at_raw", "desired_at_iso",
    "confirmed_at_raw", "confirmed_at_iso", "comment_text", "responsible",
    "data_quality", "issues_json", "raw_cells_json", "row_sha256",
    "first_observed_at", "last_changed_at", "last_seen_run", "is_current"
)
def now_utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def txt(value):
    s = str(value if value is not None else "").strip()
    return s or None

def number(value):
    if not txt(value):
        return None, None
    s = re.sub(r"[\s\u00a0\u202f]", "", str(value)).replace(",", ".")
    if not re.fullmatch(r"\d+(?:\.\d+)?", s):
        return None, "invalid_quantity"
    try:
        n = Decimal(s)
    except InvalidOperation:
        return None, "invalid_quantity"
    if n < 0 or not n.is_finite():
        return None, "invalid_quantity"
    return format(n, "f"), None

def date(value):
    s = txt(value)
    if not s:
        return None, None
    # Never guess the year from a day.month or two-digit year.
    m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{4})",s)
    if not m:
        return None, "date_not_unambiguously_parseable"
    try:
        return datetime(int(m[3]),int(m[2]),int(m[1])).date().isoformat(),None
    except ValueError:
        return None,"invalid_date"

def normheader(value):
    return " ".join(str(value if value is not None else "").split()).strip().casefold()

def header_check(source, rows):
    expected = SOURCES[source]["headers"]
    head = rows[0] if rows else []
    actual = tuple(normheader(head[j] if j<len(head) else "") for j in range(len(expected)))
    if actual != tuple(normheader(h) for h in expected):
        raise ValueError("source headers differ from approved column contract")

def meaningful(source, row):
    # The metal table has many formula-only zeroes in G: do not import them as orders.
    if source == "sewing":
        return any(txt(row[i] if i<len(row) else None) for i in (0,1,2,3,4,5,6,7,8,9,10))
    return any(txt(row[i] if i<len(row) else None) for i in (0,1,2,3,4,7,8,9,10,11,12))

def parse_source(source, rows):
    if source not in SOURCES:
        raise ValueError("unknown production source")
    header_check(source, rows)
    records=[]
    for rownum,row in enumerate(rows[1:],start=2):
        if not meaningful(source,row):
            continue
        width=SOURCES[source]["width"]
        raw=[txt(row[i] if i<len(row) else None) for i in range(width)]
        if source=="sewing":
            base=dict(requester=raw[0],production_site=None,internal_article=raw[1],
                product_name=raw[2],requested_qty_raw=raw[3],delivered_qty_raw=raw[4],
                remainder_qty_raw=None,placed_at_raw=raw[5],order_number=raw[6],
                invoice_number=None,desired_at_raw=raw[7],confirmed_at_raw=raw[8],
                comment_text=raw[9],responsible=raw[10])
        else:
            base=dict(requester=raw[0],production_site=raw[1],internal_article=raw[2],
                product_name=raw[3],requested_qty_raw=raw[4],delivered_qty_raw=raw[5],
                remainder_qty_raw=raw[6],placed_at_raw=raw[7],invoice_number=raw[8],
                order_number=raw[9],desired_at_raw=raw[10],comment_text=raw[11],
                confirmed_at_raw=raw[12],responsible=None)
        issues=[]
        if not base["internal_article"]:
            issues.append("missing_article")
        if not base["product_name"]:
            issues.append("missing_product_name")
        if not base["order_number"]:
            issues.append("missing_order_number")
        for stem,field in (("requested","requested_qty_raw"),
                           ("delivered","delivered_qty_raw"),
                           ("remainder","remainder_qty_raw")):
            n,issue=number(base[field])
            base[stem+"_qty_decimal"]=n
            if issue:
                issues.append(stem+"_"+issue)
        for stem,field in (("placed","placed_at_raw"),("desired","desired_at_raw"),
                           ("confirmed","confirmed_at_raw")):
            value,issue=date(base[field])
            base[stem+"_at_iso"]=value
            if issue:
                issues.append(stem+"_"+issue)
        if not base["requested_qty_raw"]:
            issues.append("missing_requested_quantity")
        data_json=json.dumps(raw,ensure_ascii=False,separators=(",",":"))
        base.update(source_row=rownum, data_quality="review" if issues else "ok",
                    issues_json=json.dumps(issues,ensure_ascii=False,separators=(",",":")),
                    raw_cells_json=data_json,row_sha256=sha256(data_json.encode("utf-8")).hexdigest())
        records.append(base)
    return records

def fetch_csv(source):
    source_def=SOURCES[source]
    sid=os.environ.get(source_def["sheet_env"],"").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,120}",sid):
        raise ValueError("invalid source spreadsheet configuration")
    url="https://docs.google.com/spreadsheets/d/"+sid+"/export?format=csv&gid="+source_def["gid"]
    req=Request(url,headers={"User-Agent":"msp-production-catalog/1.0"})
    with urlopen(req,timeout=40) as response:
        content_type=response.headers.get("Content-Type","").lower()
        if not ("csv" in content_type or "application/octet-stream" in content_type):
            raise ValueError("source did not serve CSV")
        raw=response.read(25_000_001)
    if len(raw)>25_000_000:
        raise ValueError("CSV exceeds bounded read limit")
    text=raw.decode("utf-8-sig")
    if text[:150].lstrip().lower().startswith(("<!doctype html","<html")):
        raise ValueError("source returned login/HTML instead of CSV")
    return list(csv.reader(io.StringIO(text,newline="")))

def insert_run(con,source,start,status,**kw):
    keys=["source","started_at","status"]+list(kw)
    values=[source,start,status]+list(kw.values())
    sql="INSERT INTO production_import_run ("+",".join(keys)+") VALUES("+",".join("?" for _ in values)+")"
    return con.execute(sql,values).lastrowid

def save(con,source,records,started):
    table=SOURCES[source]["table"]
    con.executescript(SCHEMA)
    with con:
        run=insert_run(con,source,started,"running",source_rows=len(records))
        inserted=changed=unchanged=0
        rows_in_snapshot=[]
        for record in records:
            rownum=record["source_row"]
            current=con.execute(
                "SELECT row_sha256,raw_cells_json,first_observed_at,is_current "
                "FROM "+table+" WHERE source_row=?",(rownum,)).fetchone()
            if current is not None and current[0]==record["row_sha256"] and current[3]==1:
                con.execute("UPDATE "+table+" SET last_seen_run=? WHERE source_row=?",(run,rownum))
                unchanged+=1
                rows_in_snapshot.append(rownum)
                continue
            if current:
                first=current[2]
                changed+=1
            else:
                first=started
                inserted+=1
            con.execute("INSERT INTO production_row_revision "
                        "(source,source_row,previous_sha256,next_sha256,old_values_json,"
                        "new_values_json,changed_at,run_id) VALUES(?,?,?,?,?,?,?,?)",
                        (source,rownum,current[0] if current else None,record["row_sha256"],
                         current[1] if current else None,record["raw_cells_json"],started,run))
            values={**record,"first_observed_at":first,
                    "last_changed_at":started,"last_seen_run":run,"is_current":1}
            sql="INSERT INTO "+table+" ("+",".join(COLUMNS)+") VALUES("+",".join("?" for _ in COLUMNS)+") "
            sql+="ON CONFLICT(source_row) DO UPDATE SET "+",".join(c+"=excluded."+c for c in COLUMNS if c!="source_row")
            con.execute(sql,tuple(values.get(c) for c in COLUMNS))
            rows_in_snapshot.append(rownum)
        retired=con.execute("UPDATE "+table+" SET is_current=0 WHERE is_current=1 AND last_seen_run<>?",(run,)).rowcount
        issue_rows=missing_article=0
        for record in records:
            issues=json.loads(record["issues_json"])
            if issues:
                issue_rows+=1
            if "missing_article" in issues:
                missing_article+=1
            for issue in issues:
                con.execute("INSERT INTO production_data_issue (run_id,source,source_row,issue_code) "
                            "VALUES(?,?,?,?)",(run,source,record["source_row"],issue))
        con.execute("UPDATE production_import_run SET finished_at=?,status=?,present_rows=?,"
                    "missing_article_rows=?,issue_rows=?,inserted=?,changed=?,unchanged=?,retired=? "
                    "WHERE run_id=?",(now_utc(),"partial" if issue_rows else "success",
                    len(records),missing_article,issue_rows,inserted,changed,unchanged,retired,run))
    return dict(source=source,status="partial" if issue_rows else "success",
                current_rows=len(records),missing_article=missing_article,
                issue_rows=issue_rows,inserted=inserted,changed=changed,
                unchanged=unchanged,retired=retired)

def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument("--source",choices=tuple(SOURCES),required=True)
    ap.add_argument("--db",help="Existing MSP SQLite DB; never implicitly created")
    ap.add_argument("--preflight",action="store_true",help="Only fetch and validate source; SQLite untouched")
    args=ap.parse_args(argv)
    if not args.preflight and not args.db:
        ap.error("--db required except for --preflight")
    started=now_utc()
    try:
        rows=fetch_csv(args.source)
        records=parse_source(args.source,rows)
        if len(records)<SOURCES[args.source]["min_rows"]:
            raise ValueError("source unusually short; refusing incomplete snapshot")
        if args.preflight:
            issues=sum(bool(json.loads(x["issues_json"])) for x in records)
            print(json.dumps(dict(source=args.source,preflight="pass",current_rows=len(records),
                                  issue_rows=issues,missing_article=sum(not x["internal_article"] for x in records)),
                             ensure_ascii=False))
            return 0
        path=Path(args.db)
        if not path.is_file() or path.is_symlink():
            raise RuntimeError("existing protected database not found")
        con=sqlite3.connect("file:"+str(path.resolve())+"?mode=rw",uri=True,timeout=30)
        try:
            if con.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
                raise RuntimeError("SQLite integrity failed")
            expected={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"product_listing","sync_run","product_cost_current"}.issubset(expected):
                raise RuntimeError("existing MSP schema missing")
            output=save(con,args.source,records,started)
            if con.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
                raise RuntimeError("SQLite post-write integrity failed")
            print(json.dumps(output,ensure_ascii=False))
        finally:
            con.close()
        return 0
    except Exception as e:
        # Do not include source cells, sheet IDs, or transport exception strings in logs.
        print(json.dumps(dict(source=args.source,result="failed",error_class=type(e).__name__)))
        return 2

if __name__=="__main__":
    sys.exit(main())
