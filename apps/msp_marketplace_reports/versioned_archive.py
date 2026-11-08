"""Offline opt-in bridge from local CSV imports to B7 immutable generations.

DO NOT silently redirect the legacy import_csv, provider ingest, or legacy CSV
readers. An operator must explicitly select the versioned interface and all
readers must use the matching pinned snapshot contract.

The adapter refuses a scope containing legacy CSV/manifest files; migration
requires a separately reviewed, verified, no-write-to-legacy procedure.
"""
from __future__ import annotations

import json,csv,io
from pathlib import Path

from .archive import (
    DATASETS, _encode, _location, _metadata, _ozon_annual_path,
    _rows, _validate, _sha, _lock, _scan_rows,
)
from .generation_store import (
    GenerationError, publish_batch, read_active, read_generation,
    _require_plain,
)


def _period_scope(dataset: str, period: str) -> str:
    return period[:4] if dataset == "ozon_final_realization" else period


def _legacy_scope_occupied(root: Path, dataset: str, cabinet: str,
                           period: str) -> bool:
    """Shared read-only inventory for admission AND offline planner.

    Existing empty monthly_source directory is NOT a financial archive.
    Any annual CSV/manifest or monthly entry, including a dangling symlink,
    IS a legacy artifact. Unsafe parent links fail closed.
    """
    if dataset == "ozon_final_realization":
        year = period[:4]
        annual = _ozon_annual_path(root, cabinet, year)
        month_dir = _location(root, dataset, cabinet, period).parent
        _require_plain(annual)
        _require_plain(annual.with_name(annual.name + ".meta.json"))
        _require_plain(month_dir)
        candidates = [annual, annual.with_name(annual.name + ".meta.json")]
        if month_dir.exists():
            candidates.extend(month_dir.iterdir())
    else:
        file = _location(root, dataset, cabinet, period)
        manifest = file.with_name(file.name + ".meta.json")
        _require_plain(file)
        _require_plain(manifest)
        candidates = [file, manifest]
    return any(path.exists() or path.is_symlink() for path in candidates)


def _assert_no_legacy(root: Path, dataset: str, cabinet: str, period: str):
    """Fail closed when shared inventory sees a legacy financial artifact."""
    if _legacy_scope_occupied(root, dataset, cabinet, period):
        raise GenerationError("legacy CSV scope exists; migration required")


def _merge_wb_csv(old_data, incoming_fields, incoming, keys):
    """Stream annual rows; hold only the current report and stable-key set.

    Existing CSV row order is retained (not assumed sorted). New keys append
    deterministically; order is not part of WB financial row identity.
    """
    old_fields, records = _scan_rows(old_data, keys) if old_data else ([], ())
    fields = list(dict.fromkeys([*old_fields, *incoming_fields]))
    output = io.StringIO(newline='')
    writer = csv.writer(output, delimiter=';', lineterminator='\n')
    writer.writerow(fields)
    remaining = dict(incoming)
    indices = [old_fields.index(f) if f in old_fields else None for f in fields]
    count = 0
    for key, values in records:
        update = remaining.pop(key, None)
        if update is None:
            writer.writerow([values[i] if i is not None else '' for i in indices])
        else:
            row = dict(zip(old_fields, values))
            if any(row[f] != update[f] for f in set(row) & set(update)):
                raise ValueError('conflicting WB stable key: '+repr(key))
            row.update(update)
            writer.writerow([row.get(f, '') for f in fields])
        count += 1
    for key in sorted(remaining):
        writer.writerow([remaining[key].get(f, '') for f in fields])
    return ('\ufeff'+output.getvalue()).encode('utf-8'), count+len(remaining), len(remaining)


def _pair(files, name, raw, dataset, cabinet, period, keys):
    """Keep byte-identical existing CSV+metadata to make no-op stable."""
    if files.get(name) == raw and name + ".meta.json" in files:
        return
    if dataset.startswith("wb_weekly_finance_"):
        _, records = _scan_rows(raw, keys)
        count = sum(1 for _ in records)
    else:
        count = len(_rows(raw, keys)[1])
    files[name] = raw
    files[name + ".meta.json"] = json.dumps(
        _metadata(raw, count, dataset, cabinet, period),
        ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8") + b"\n"


def _ozon_annual(files, cabinet, year):
    """Derive an annual snapshot exclusively from the candidate monthly files."""
    months = sorted(name for name in files if name.startswith("monthly/")
                    and name.endswith(".csv"))
    fields = []
    combined = {}
    for name in months:
        month = name[len("monthly/"):-len(".csv")]
        month_fields, rows = _rows(files[name], DATASETS["ozon_final_realization"][1])
        if not month.startswith(year + "-") or any(
            row["report_year"] != year or row["report_month"] != month
            for row in rows.values()
        ):
            raise GenerationError("Ozon monthly scope/period mismatch")
        if any(key in combined for key in rows):
            raise GenerationError("duplicate Ozon stable key across months")
        combined.update(rows)
        fields = list(dict.fromkeys([*fields, *month_fields]))
    if not months:
        raise GenerationError("Ozon annual requires at least one source month")
    annual = _encode(fields, combined)
    _pair(files, "annual.csv", annual, "ozon_final_realization", cabinet,
          year, DATASETS["ozon_final_realization"][1])


def import_csv_versioned(root: Path, dataset: str, cabinet: str,
                         period: str, source: Path):
    """Opt-in one-scope import with optimistic CAS and no legacy writes.

    Builds the candidate from a pinned active generation, then publish_batch
    rechecks its parent under flock. A concurrent commit rejects this attempt
    as stale; caller must explicitly re-read and retry. No silent rebase.
    """
    root = Path(root).expanduser()
    _, keys = _validate(dataset, cabinet, period)
    raw = Path(source).read_bytes()
    fields, incoming = _rows(raw, keys)
    if dataset == "ozon_final_realization":
        if any(row["report_year"] != period[:4] or row["report_month"] != period
               for row in incoming.values()):
            raise ValueError("Ozon FINAL rows must match selected month")
    elif dataset.startswith("wb_weekly_finance_"):
        expected_type = "1" if dataset.endswith("_main") else "2"
        if "reportType" not in fields or any(
            row["reportType"] != expected_type for row in incoming.values()
        ):
            raise ValueError("WB reportType mismatch")
        if any((row.get("dateTo") or row.get("date_to") or "")[:4]
               not in ("", period) for row in incoming.values()):
            raise ValueError("WB financial period mismatch")
    scope_period = _period_scope(dataset, period)
    # Shared admission lock with archive.import_csv: legacy vs versioned
    # writers cannot race across preflight and CURRENT commit.
    # Lock ordering: legacy admission lock, then generation scope flock.
    with _lock(root, cabinet, dataset):
        # Refuse legacy before and after candidate building, before the CAS commit.
        _assert_no_legacy(root, dataset, cabinet, period)
        active = read_active(root, dataset, cabinet, scope_period)
        parent = active["generation"] if active else None
        candidate = dict(active["files"]) if active else {}
        if dataset.startswith("wb_weekly_finance_"):
            payload, row_count, additions = _merge_wb_csv(
                candidate.get('data.csv'), fields, incoming, keys)
            _pair(candidate, "data.csv", payload, dataset, cabinet, period, keys)
        elif dataset == "ozon_final_realization":
            payload = _encode(fields, incoming)
            _pair(candidate, "monthly/" + period + ".csv", payload,
                  dataset, cabinet, period, keys)
            _ozon_annual(candidate, cabinet, period[:4])
            row_count = len(incoming)
            additions = None
        else:
            payload = _encode(fields, incoming)
            _pair(candidate, "data.csv", payload, dataset, cabinet, period, keys)
            row_count = len(incoming)
            additions = None
        _assert_no_legacy(root, dataset, cabinet, period)
        receipt = publish_batch(root, dataset, cabinet, scope_period, candidate,
                                expected_generation=parent)
        result = {**receipt, "rows": row_count, "dataset": dataset,
                  "cabinet": cabinet, "period": period,
                  "provider_coverage_proven": False}
        if additions is not None:
            result["new_rows"] = additions
        return result

def read_csv_versioned(root: Path, dataset: str, cabinet: str, period: str,
                       *, pinned_generation=None, expected_digest=None):
    """Return (CSV bytes, immutable receipt), never legacy path contents."""
    _validate(dataset, cabinet, period)
    _assert_no_legacy(Path(root).expanduser(), dataset, cabinet, period)
    scope_period = _period_scope(dataset, period)
    if pinned_generation is None:
        if expected_digest is not None:
            raise GenerationError("digest requires pinned generation")
        snapshot = read_active(root, dataset, cabinet, scope_period)
    else:
        snapshot = read_generation(root, dataset, cabinet, scope_period,
                                   pinned_generation, expected_digest=expected_digest)
    if snapshot is None:
        raise GenerationError("no committed generation for selected scope")
    name = ("monthly/" + period + ".csv"
            if dataset == "ozon_final_realization" else "data.csv")
    if name not in snapshot["files"]:
        raise GenerationError("requested month not in committed snapshot")
    return snapshot["files"][name], {
        "generation": snapshot["generation"],
        "manifest_sha256": snapshot["manifest_sha256"],
        "bytes": len(snapshot["files"][name]),
        "sha256": _sha(snapshot["files"][name]),
        "dataset": dataset, "cabinet": cabinet, "period": period,
        "provider_coverage_proven": False,
    }


def verify_versioned_scope(root: Path, dataset: str, cabinet: str, period: str):
    """Read-only one-scope verification; no hidden recovery or legacy fallback."""
    _validate(dataset, cabinet, period)
    try:
        _assert_no_legacy(Path(root).expanduser(), dataset, cabinet, period)
        snapshot = read_active(root, dataset, cabinet, _period_scope(dataset, period))
        if snapshot is None:
            raise GenerationError("no committed generation")
        name = ("monthly/" + period + ".csv"
                if dataset == "ozon_final_realization" else "data.csv")
        if name not in snapshot["files"]:
            raise GenerationError("requested report is not present")
        raw = snapshot["files"][name]
        return {"ok": True, "generation": snapshot["generation"],
                "manifest_sha256": snapshot["manifest_sha256"],
                "bytes": len(raw), "sha256": _sha(raw),
                "provider_coverage_proven": False}
    except (OSError, ValueError) as exc:
        return {"ok": False, "error": str(exc),
                "provider_coverage_proven": False}
