"""Verified local CSV archive for WB weekly finance and Ozon FINAL/CURRENT.

No marketplace API calls, credentials, or Google Drive access in this module.
LOCAL_VERIFIED means bytes and row keys checked; it does not prove provider coverage.
"""
from __future__ import annotations

import csv
import fcntl
import hashlib
import io
import json
import os
import re
import shutil
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_ROOT = Path("/opt/mcp/data/msp-marketplace-reports")
CABINETS = {
    "wb": ("wb_laser_master", "wb_novokshenov", "wb_dmitrieva"),
    "ozon": ("ozon_laser_master", "ozon_novokshenov", "ozon_dmitrieva"),
}
DATASETS = {
    "wb_weekly_finance_main": ("wb", ("reportId", "rrdId")),
    "wb_weekly_finance_buyout": ("wb", ("reportId", "rrdId")),
    "ozon_final_realization": ("ozon", ("report_year", "report_month", "row_number")),
    "ozon_current_orders_fbo": ("ozon", ("posting_number",)),
    "ozon_current_orders_fbs": ("ozon", ("posting_number",)),
    "ozon_current_accruals": ("ozon", ("accrual_id",)),
}
PERIOD_RE = re.compile(r"^20\d{2}(?:-(?:0[1-9]|1[0-2]))?$")


def _utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha(data: bytes):
    return hashlib.sha256(data).hexdigest()


def _safe_write(path: Path, data: bytes):
    """Atomic single-file replacement with fsync; no in-place truncation."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(dir=str(path.parent), prefix=".incoming-", delete=False) as f:
            tmp = Path(f.name)
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(str(tmp), str(path))
        fd = os.open(str(path.parent), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if tmp is not None and tmp.exists():
            tmp.unlink()


def _backup(path: Path, root: Path):
    if not path.is_file():
        return
    relative = path.relative_to(root)
    target_dir = root / ".backups" / relative.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    current = path.read_bytes()
    target = target_dir / (path.name + "." + _sha(current)[:16] + ".bak")
    if not target.exists():
        _safe_write(target, current)


def _rows(data: bytes, keys: tuple[str, ...]):
    if not data:
        raise ValueError("empty CSV is not a verified report")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ValueError("CSV must be UTF-8/UTF-8-BOM") from exc
    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    fields = reader.fieldnames or []
    if not fields or len(fields) != len(set(fields)) or not set(keys).issubset(fields):
        raise ValueError("missing/duplicate CSV header or stable-key columns")
    result = {}
    for line, row in enumerate(reader, 2):
        if None in row or any(v is None for v in row.values()):
            raise ValueError("invalid CSV row at line %d" % line)
        k = tuple(row[field].strip() for field in keys)
        if not all(k) or k in result:
            raise ValueError("incomplete/duplicate stable key at line %d" % line)
        result[k] = row
    return list(fields), result


def _encode(fields, mapping):
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=fields, delimiter=";", lineterminator="\n")
    writer.writeheader()
    for key in sorted(mapping):
        writer.writerow({field: mapping[key].get(field, "") for field in fields})
    return ("\ufeff" + out.getvalue()).encode("utf-8")


def _metadata(data: bytes, rows: int, dataset: str, cabinet: str, period: str):
    return {
        "schema": 1, "dataset": dataset, "cabinet": cabinet, "period": period,
        "rows": rows, "bytes": len(data), "sha256": _sha(data),
        "status": "LOCAL_VERIFIED", "provider_coverage_proven": False,
        "updated_at_utc": _utc(),
    }



def _verify_previous(path: Path, dataset: str, cabinet: str, period: str, keys: tuple[str, ...]):
    """Verify old CSV *and* its manifest before using or replacing either.

    An orphan CSV/manifest or a corrupt old file must never be 'repaired' by
    calculating a new checksum over damaged data. Do not mutate on failure.
    """
    meta_path = path.with_name(path.name + ".meta.json")
    if not path.exists() and not meta_path.exists():
        return [], {}
    if not path.is_file() or not meta_path.is_file():
        raise ValueError("existing archive is incomplete: CSV/manifest pair required")
    try:
        raw = path.read_bytes()
        meta = json.loads(meta_path.read_text("utf-8"))
        if not isinstance(meta, dict):
            raise ValueError("manifest must be an object")
        fields, rows = _rows(raw, keys)
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        raise ValueError("existing archive verification failed") from exc
    expected = {"schema": 1, "dataset": dataset, "cabinet": cabinet,
                "period": period, "status": "LOCAL_VERIFIED",
                "bytes": len(raw), "rows": len(rows), "sha256": _sha(raw)}
    # JSON booleans compare equal to Python integers (True == 1). A valid
    # manifest must use actual JSON integer tokens, never true/false, 1.0,
    # strings or null for the schema and numeric integrity fields.
    if any(type(meta.get(field)) is not int for field in ("schema", "rows", "bytes")):
        raise ValueError("existing archive manifest integer type mismatch")
    if any(meta.get(key) != value for key, value in expected.items()):
        raise ValueError("existing archive integrity/identity mismatch; restore before import")
    return fields, rows


def _publish(root: Path, path: Path, data: bytes, count: int, dataset: str, cabinet: str, period: str):
    manifest = path.with_name(path.name + ".meta.json")
    # Independent preflight even for no-op imports and Ozon rebuilds.
    _verify_previous(path, dataset, cabinet, period, DATASETS[dataset][1])
    if path.exists() and path.read_bytes() == data:
        if manifest.is_file():
            try:
                old = json.loads(manifest.read_text("utf-8"))
                if old.get("sha256") == _sha(data) and old.get("rows") == count:
                    return False
            except (ValueError, OSError):
                pass
    _backup(path, root)
    _backup(manifest, root)
    _safe_write(path, data)
    if _sha(path.read_bytes()) != _sha(data):
        raise IOError("post-publication checksum differs")
    meta = _metadata(data, count, dataset, cabinet, period)
    _safe_write(manifest, json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n")
    return True


@contextmanager
def _lock(root: Path, cabinet: str, dataset: str):
    folder = root / ".locks"
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / (cabinet + "__" + dataset + ".lock")).open("a+b") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _validate(dataset: str, cabinet: str, period: str):
    if dataset not in DATASETS:
        raise ValueError("unknown dataset")
    marketplace, keys = DATASETS[dataset]
    if cabinet not in CABINETS[marketplace]:
        raise ValueError("unknown cabinet for dataset")
    if not PERIOD_RE.fullmatch(period):
        raise ValueError("bad period")
    month_expected = not dataset.startswith("wb_weekly_finance_")
    if ("-" in period) != month_expected:
        raise ValueError("dataset requires " + ("YYYY-MM" if month_expected else "YYYY"))
    return marketplace, keys


def _location(root: Path, dataset: str, cabinet: str, period: str):
    year = period[:4]
    if dataset in ("wb_weekly_finance_main", "wb_weekly_finance_buyout"):
        category = "main" if dataset == "wb_weekly_finance_main" else "buyout"
        return root / "База данных" / "WB" / cabinet / year / "finance" / "weekly" / category / (cabinet + "__weekly_" + category + "__" + year + ".csv")
    base = root / "База данных" / "Ozon" / cabinet / year
    if dataset == "ozon_final_realization":
        return base / "FINAL" / "monthly_source" / (cabinet + "__realization__" + period + ".csv")
    token = dataset.replace("ozon_current_", "")
    return base / "CURRENT" / period / (cabinet + "__" + token + "__" + period + ".csv")


def _reject_versioned_scope(root: Path, dataset: str, cabinet: str, period: str):
    """Legacy writer admission: same lock as versioned adapter, no dual truth.

    The versioned scope is claimed as soon as its directory exists, including
    a failed first publication. A migrated/abandoned scope requires an
    explicit reviewed transition; never silently write legacy beside it.
    """
    year_or_period = period[:4] if dataset == "ozon_final_realization" else period
    base = root / ".b7-generations"
    candidate = base
    for component in (dataset, cabinet, year_or_period):
        if candidate.is_symlink():
            raise ValueError("versioned store path is a symbolic link")
        candidate = candidate / component
    if candidate.is_symlink():
        raise ValueError("versioned store path is a symbolic link")
    if candidate.exists():
        raise ValueError("versioned scope exists; legacy import forbidden")


def _import_wb(root, path, dataset, cabinet, period, fields, incoming, keys):
    existing_fields, existing = _verify_previous(path, dataset, cabinet, period, keys)
    merged = dict(existing)
    for k, value in incoming.items():
        if k in merged:
            # Equivalent records may have a different set of columns.
            common = set(merged[k]) & set(value)
            if any(merged[k].get(field, "") != value.get(field, "") for field in common):
                raise ValueError("conflicting WB stable key: %r" % (k,))
            merged[k] = dict(merged[k], **value)
        else:
            merged[k] = value
    columns = list(dict.fromkeys([*existing_fields, *fields]))
    payload = _encode(columns, merged)
    changed = _publish(root, path, payload, len(merged), dataset, cabinet, period)
    return {"changed": changed, "rows": len(merged), "new_rows": len(merged) - len(existing), "path": str(path)}


def _import_snapshot(root, path, dataset, cabinet, period, fields, incoming):
    payload = _encode(fields, incoming)
    changed = _publish(root, path, payload, len(incoming), dataset, cabinet, period)
    return {"changed": changed, "rows": len(incoming), "path": str(path)}


def _ozon_annual_path(root: Path, cabinet: str, year: str):
    return (root / "База данных" / "Ozon" / cabinet / year / "FINAL" / "annual"
            / (cabinet + "__realization__" + year + ".csv"))


def _verified_ozon_months(root: Path, cabinet: str, year: str):
    """Check every existing month and orphaned manifest with EXPECTED identity.

    Called before publication and again during annual reconstruction. This
    protects dependencies not explicitly part of the incoming monthly import.
    Provider coverage/inventory is a separate, still-unsolved concern (B8).
    """
    source = root / "База данных" / "Ozon" / cabinet / year / "FINAL" / "monthly_source"
    prefix = cabinet + "__realization__" + year + "-"
    csv_paths = set(source.glob(prefix + "*.csv"))
    meta_paths = set(source.glob(prefix + "*.csv.meta.json"))
    paths = csv_paths | {
        meta.with_name(meta.name[:-len(".meta.json")]) for meta in meta_paths
    }
    expected_name = re.compile(
        r"^" + re.escape(prefix) + r"(0[1-9]|1[0-2])\.csv$"
    )
    all_rows = {}
    fields = []
    for file in sorted(paths):
        match = expected_name.fullmatch(file.name)
        if not match:
            raise ValueError("unrecognized Ozon monthly source name: " + file.name)
        month = year + "-" + match.group(1)
        names, rows = _verify_previous(
            file, "ozon_final_realization", cabinet, month,
            DATASETS["ozon_final_realization"][1],
        )
        if any(row["report_year"] != year or row["report_month"] != month
               for row in rows.values()):
            raise ValueError("Ozon monthly row period mismatch: " + file.name)
        if any(key in all_rows for key in rows):
            raise ValueError("duplicate Ozon annual stable key")
        all_rows.update(rows)
        fields = list(dict.fromkeys([*fields, *names]))
    return fields, all_rows, len(paths)


def _preflight_ozon_group(root: Path, cabinet: str, year: str):
    """Reject unsafe existing year/month state before the first mutation."""
    annual = _ozon_annual_path(root, cabinet, year)
    annual_present = annual.exists() or annual.with_name(annual.name + ".meta.json").exists()
    _, old_annual = _verify_previous(
        annual, "ozon_final_realization", cabinet, year,
        DATASETS["ozon_final_realization"][1],
    )
    _, month_rows, count = _verified_ozon_months(root, cabinet, year)
    if annual_present != bool(count):
        raise ValueError("Ozon monthly/annual pair incomplete; verified recovery required")
    if annual_present and (
        set(old_annual) != set(month_rows)
        or any(
            any(old_annual[key].get(field, "") != row.get(field, "")
                for field in set(old_annual[key]) | set(row))
            for key, row in month_rows.items()
        )
    ):
        # Different months may have different columns; compare missing fields
        # as empty, exactly as verify() does.
        raise ValueError("Ozon annual differs from verified monthly sources")


def _rebuild_ozon_annual(root, cabinet, year):
    fields, all_rows, count = _verified_ozon_months(root, cabinet, year)
    if not count or not all_rows:
        raise ValueError("no verified Ozon months")
    annual = _ozon_annual_path(root, cabinet, year)
    data = _encode(fields, all_rows)
    changed = _publish(root, annual, data, len(all_rows), "ozon_final_realization", cabinet, year)
    return {"annual_path": str(annual), "annual_rows": len(all_rows), "annual_changed": changed}


def import_csv(root: Path, dataset: str, cabinet: str, period: str, source: Path):
    """Offline import. Caller must establish source provenance separately."""
    root = Path(root).expanduser().resolve()
    _, keys = _validate(dataset, cabinet, period)
    raw = Path(source).read_bytes()
    fields, incoming = _rows(raw, keys)
    if dataset == "ozon_final_realization":
        if any(row["report_year"] != period[:4] or row["report_month"] != period for row in incoming.values()):
            raise ValueError("Ozon FINAL rows must match report year/month")
    if dataset.startswith("wb_weekly_finance_") and any(
        (row.get("dateTo") or row.get("date_to") or "")[:4] not in ("", period)
        for row in incoming.values()
    ):
        raise ValueError("WB finance period outside selected annual partition")
    path = _location(root, dataset, cabinet, period)
    with _lock(root, cabinet, dataset):
        # Shared admission protocol with versioned import. This must run
        # under the same legacy writer lock before any CSV or backup changes.
        _reject_versioned_scope(root, dataset, cabinet, period)
        if dataset == "ozon_final_realization":
            # The old annual and *all* monthly dependencies must be sound
            # before writing the new month's CSV, manifest or backups.
            _preflight_ozon_group(root, cabinet, period[:4])
        if dataset.startswith("wb_weekly_finance_"):
            result = _import_wb(root, path, dataset, cabinet, period, fields, incoming, keys)
        else:
            result = _import_snapshot(root, path, dataset, cabinet, period, fields, incoming)
        if dataset == "ozon_final_realization":
            result.update(_rebuild_ozon_annual(root, cabinet, period[:4]))
    return result


def verify(root: Path):
    """Read-only integrity audit, including Ozon monthly-to-annual parity.

    Source-provider coverage is NOT proven by this local verification.
    """
    root = Path(root).expanduser().resolve()
    reports = []
    failures = []
    ozon_monthly = {}
    ozon_annual = {}
    for file in sorted((root / "База данных").rglob("*.csv")):
        meta_file = file.with_name(file.name + ".meta.json")
        try:
            meta = json.loads(meta_file.read_text("utf-8"))
            dataset, cabinet, period = meta["dataset"], meta["cabinet"], meta["period"]
            is_annual = dataset == "ozon_final_realization" and file.parent.name == "annual"
            _, keys = _validate(dataset, cabinet, period + "-01" if is_annual else period)
            expected_path = (
                _ozon_annual_path(root, cabinet, period) if is_annual
                else _location(root, dataset, cabinet, period)
            )
            if file != expected_path:
                raise ValueError("archive manifest identity/path mismatch")
            _reject_versioned_scope(root, dataset, cabinet, period)
            _, rows = _verify_previous(file, dataset, cabinet, period, keys)
            # Existing manifests were historically checked only for
            # checksum/count: schema/status and identity must also be audited.
            if dataset == "ozon_final_realization":
                if file.parent.name == "monthly_source":
                    if any(row["report_month"] != period or row["report_year"] != period[:4] for row in rows.values()):
                        raise ValueError("Ozon monthly source period mismatch")
                    group = ozon_monthly.setdefault((cabinet, period[:4]), {})
                    if any(k in group for k in rows):
                        raise ValueError("duplicate Ozon key across months")
                    group.update(rows)
                elif is_annual:
                    ozon_annual[(cabinet, period)] = rows
            reports.append({"file": str(file), "rows": len(rows), "dataset": dataset, "period": period})
        except (OSError, ValueError, KeyError, TypeError, UnicodeError) as exc:
            failures.append({"file": str(file), "error": str(exc)})
    for key, monthly in ozon_monthly.items():
        annual = ozon_annual.get(key)
        if annual is None or set(annual) != set(monthly) or any(
            any(annual[k].get(field, "") != row.get(field, "") for field in set(row) | set(annual[k]))
            for k, row in monthly.items()
        ):
            failures.append({"cabinet_year": list(key), "error": "Ozon annual differs from monthly sources"})
    if not reports:
        failures.append({"error": "archive is empty; no files verified"})
    return {"ok": not failures, "files": len(reports), "verified": reports, "failures": failures,
            "provider_coverage_proven": False}
