"""Opt-in OFFLINE WB durable-page -> CSV -> B7 verified publication bridge.

This is NOT a scheduler, an installed VPS worker or a permission to use APIs.
The existing Marketplace MCP scheduler must call run_one_step from exactly
one approved host and persist WAITING_RATE_LIMIT/not_before_utc in its job.
Never reserve quota in the scheduler AND in a ReadOnlyHTTP sender.
"""
from __future__ import annotations

import csv
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from .archive import _rows, _sha, _validate, DATASETS
from .generation_store import GenerationError
from .ingest import _cell
from .versioned_archive import import_csv_versioned, read_csv_versioned, _assert_no_legacy
from .wb_page_resume import (
    step_wb_detail, read_completed_wb_pages, _dir, _checked,
    _read_json, _validate_state, _verify_pages,
)


def _dataset(report_type):
    if type(report_type) is not int or report_type not in (1, 2):
        raise ValueError("WB report type must be 1 or 2")
    return ("wb_weekly_finance_main" if report_type == 1
            else "wb_weekly_finance_buyout")


def _stage_record(root, cabinet, year, report_id, report_type):
    folder = _dir(root, cabinet, year, report_id, report_type)
    state = _read_json(folder / "state.json", required=True)
    _validate_state(state, cabinet, year, report_id, report_type)
    if state["status"] != "STAGED_COMPLETE":
        raise GenerationError("WB report pages not terminal")
    _verify_pages(folder, state, report_id, report_type)
    return folder, state


def _stream_csv(root, cabinet, year, report_id, report_type, target):
    """Two bounded passes; consume and release page lock before publisher lock."""
    required = DATASETS[_dataset(report_type)][1]
    fields = set(required)
    fields.add("reportType")
    for page in read_completed_wb_pages(root, cabinet, year, report_id, report_type):
        for row in page:
            fields.update(row)
    fieldnames = list(required) + ["reportType"] + sorted(
        fields - set(required) - {"reportType", "_raw_json"}) + ["_raw_json"]
    count = 0
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(str(target), flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=fieldnames, delimiter=";", lineterminator="\n")
            writer.writeheader()
            for page in read_completed_wb_pages(
                    root, cabinet, year, report_id, report_type):
                for row in page:
                    values = {field: _cell(row.get(field)) for field in fieldnames}
                    values["_raw_json"] = json.dumps(
                        row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                    writer.writerow(values)
                    count += 1
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    if count == 0:
        raise GenerationError("WB report has no staged rows")
    return count


def _verify_receipt(root, dataset, cabinet, period, report_id, report_type,
                    receipt, source):
    """Verify exactly our stable keys/columns inside a CURRENT-anchored pin."""
    raw, pinned = read_csv_versioned(
        root, dataset, cabinet, period,
        pinned_generation=receipt["generation"],
        expected_digest=receipt["manifest_sha256"])
    _, expected = _rows(source.read_bytes(), DATASETS[dataset][1])
    _, actual = _rows(raw, DATASETS[dataset][1])
    if any(key not in actual or any(
            actual[key].get(column, "") != value
            for column, value in row.items())
            for key, row in expected.items()):
        raise GenerationError("WB published generation does not contain verified staged rows")
    if not expected or any(
            row["reportId"] != str(report_id) or
            row["reportType"] != str(report_type)
            for row in expected.values()):
        raise GenerationError("WB staged report identity mismatch")
    return pinned, len(expected)


def _read_coverage(folder):
    return _read_json(_checked(folder / "coverage.json"))


def _validate_coverage(root, cabinet, year, report_id, report_type, doc):
    dataset = _dataset(report_type)
    if (type(doc) is not dict or type(doc.get("schema")) is not int or
            doc["schema"] != 1 or doc.get("status") != "LOCAL_VERIFIED_NOT_PROVIDER_COMPLETE" or
            doc.get("cabinet") != cabinet or doc.get("dataset") != dataset or
            type(doc.get("year")) is not int or doc["year"] != year or
            type(doc.get("report_id")) is not int or doc["report_id"] != report_id or
            type(doc.get("report_type")) is not int or doc["report_type"] != report_type or
            type(doc.get("terminal_cursor")) is not int or
            type(doc.get("rows")) is not int or doc["rows"] < 1 or
            type(doc.get("page_hashes")) is not list or
            type(doc.get("generation")) is not str or
            type(doc.get("manifest_sha256")) is not str or
            doc.get("provider_coverage_proven") is not False):
        raise GenerationError("invalid WB local coverage record")
    folder, state = _stage_record(root, cabinet, year, report_id, report_type)
    if doc["terminal_cursor"] != state["current_rrd_id"] or doc["page_hashes"] != [
            e["sha256"] for e in state["pages"]]:
        raise GenerationError("WB coverage conflicts with durable staged pages")
    # Pinned read verifies CURRENT ancestry and descriptor/CSV identity. This
    # record NEVER proves the source contains every WB report for the year.
    raw, pinned = read_csv_versioned(
        root, dataset, cabinet, str(year),
        pinned_generation=doc["generation"],
        expected_digest=doc["manifest_sha256"])
    _, actual = _rows(raw, DATASETS[dataset][1])
    if len([key for key in actual if key[0] == str(report_id)]) != doc["rows"]:
        raise GenerationError("WB coverage rows missing from committed publication")
    return pinned


def finalize_staged_report(root, cabinet, year, report_id, report_type, *, fault=None):
    """No provider call. Idempotent for lost publication/coverage responses."""
    dataset = _dataset(report_type)
    _validate(dataset, cabinet, str(year))
    root = Path(root).expanduser()
    _assert_no_legacy(root, dataset, cabinet, str(year))
    folder, state = _stage_record(root, cabinet, year, report_id, report_type)
    coverage_path = _checked(folder / "coverage.json")
    prior = _read_coverage(folder)
    if prior is not None:
        _validate_coverage(root, cabinet, year, report_id, report_type, prior)
        return {**prior, "changed": False, "provider_calls": 0}
    # TemporaryDirectory has private mode 0700. CSV is 0600, and its
    # iterator closes BEFORE the writer takes the same admission lock.
    with tempfile.TemporaryDirectory(prefix=".wb-csv-", dir=folder) as temp:
        source = Path(temp) / "payload.csv"
        count = _stream_csv(root, cabinet, year, report_id, report_type, source)
        receipt = import_csv_versioned(root, dataset, cabinet, str(year), source)
        _verify_receipt(root, dataset, cabinet, str(year),
                        report_id, report_type, receipt, source)
        if fault:
            fault("after_publication_before_coverage")
        coverage = {
            "schema": 1, "status": "LOCAL_VERIFIED_NOT_PROVIDER_COMPLETE",
            "provider_coverage_proven": False,
            "cabinet": cabinet, "dataset": dataset, "year": year,
            "report_id": report_id, "report_type": report_type,
            "terminal_cursor": state["current_rrd_id"],
            "page_hashes": [entry["sha256"] for entry in state["pages"]],
            "rows": count, "generation": receipt["generation"],
            "manifest_sha256": receipt["manifest_sha256"],
        }
        # Coverage is a local receipt only. Never write it before pinned
        # publication verification, and never claim provider completeness.
        from .archive import _safe_write
        _safe_write(coverage_path, (
            json.dumps(coverage, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8"))
        _validate_coverage(root, cabinet, year, report_id, report_type, coverage)
        return {**coverage, "changed": receipt["changed"], "provider_calls": 0}


def run_one_step(root, cabinet, year, report_id, report_type, send, *, fault=None):
    """At most one provider HTTP attempt, and never any after staged complete.

    To integrate with an async existing scheduler, call through asyncio.to_thread
    on the approved host. Caller owns scheduler job persistence and not_before.
    """
    dataset = _dataset(report_type)
    _validate(dataset, cabinet, str(year))
    _assert_no_legacy(Path(root).expanduser(), dataset, cabinet, str(year))
    folder = _dir(root, cabinet, year, report_id, report_type)
    if _read_coverage(folder) is not None:
        return finalize_staged_report(root, cabinet, year, report_id, report_type)
    result = step_wb_detail(root, cabinet, year, report_id, report_type, send,
                            fault=fault)
    if result["status"] != "STAGED_COMPLETE":
        return result
    return finalize_staged_report(root, cabinet, year, report_id, report_type,
                                  fault=fault)
