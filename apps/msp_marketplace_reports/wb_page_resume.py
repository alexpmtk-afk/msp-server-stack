"""OFFLINE pilot adaptation of legacy archive_queue.py WB page/cursor staging.

The existing Marketplace MCP Redis queue remains the sole live scheduler;
this module DOES NOT install a queue, invoke a marketplace, retry in background,
or publish financial CSV. The caller supplies a quota-gated send(Request).
Each call performs <=1 request. Bytes of every accepted provider page are
durably staged BEFORE advancing current_rrd_id. A crash between those steps
is replayed from the staged page without re-fetching.
"""
from __future__ import annotations

import json
from pathlib import Path

from .archive import _lock, _safe_write, _sha, _validate
from .generation_store import GenerationError, _ensure_scope_durable, _require_plain
from .providers import ProviderError, Request, WB_DETAIL, _positive_id

MAX_STAGE_BYTES = 64 * 1024 * 1024


def _canonical(obj):
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":")) + "\n").encode("utf-8")


def _checked(path):
    _require_plain(path)
    if path.is_symlink():
        raise GenerationError("staging symlink is forbidden")
    return path


def _read_json(path, *, required=False):
    _checked(path)
    if not path.exists():
        if required:
            raise GenerationError("staged page missing")
        return None
    if not path.is_file() or path.stat().st_size > MAX_STAGE_BYTES:
        raise GenerationError("staging file is not a bounded regular file")
    try:
        value = json.loads(path.read_bytes())
    except (OSError, UnicodeError, ValueError) as exc:
        raise GenerationError("invalid staged JSON") from exc
    if type(value) is not dict:
        raise GenerationError("invalid staged object")
    return value


def _dir(root, cabinet, year, report_id):
    return Path(root).expanduser() / ".wb-report-stage" / cabinet / str(year) / str(report_id)


def _validate_state(state, cabinet, year, report_id, report_type):
    if (type(state.get("schema")) is not int or state["schema"] != 1 or
            state.get("cabinet") != cabinet or type(state.get("year")) is not int or
            state["year"] != year or type(state.get("report_id")) is not int or
            state["report_id"] != report_id or
            type(state.get("report_type")) is not int or
            state["report_type"] != report_type or
            type(state.get("current_rrd_id")) is not int or
            state["current_rrd_id"] < 0 or
            type(state.get("pages")) is not list or
            state.get("status") not in ("QUEUED", "WAITING_RATE_LIMIT",
                                        "RUNNING", "STAGED_COMPLETE")):
        raise GenerationError("invalid/stale WB resume state")
    last = 0
    for entry in state["pages"]:
        if (type(entry) is not dict or type(entry.get("cursor")) is not int or
                entry["cursor"] != last or type(entry.get("next_rrd_id")) is not int or
                entry["next_rrd_id"] <= last or type(entry.get("sha256")) is not str or
                len(entry["sha256"]) != 64 or any(c not in "0123456789abcdef" for c in entry["sha256"])):
            raise GenerationError("invalid WB staged cursor chain")
        last = entry["next_rrd_id"]
    if last != state["current_rrd_id"]:
        raise GenerationError("WB staged cursor does not match pages")


def _validate_page(page, report_id, report_type, cursor):
    if (type(page.get("schema")) is not int or page["schema"] != 1 or
            type(page.get("report_id")) is not int or page["report_id"] != report_id or
            type(page.get("report_type")) is not int or page["report_type"] != report_type or
            type(page.get("cursor")) is not int or page["cursor"] != cursor or
            type(page.get("rows")) is not list or not page["rows"]):
        raise GenerationError("invalid/orphan WB page identity")
    seen = set()
    previous = cursor
    for row in page["rows"]:
        if type(row) is not dict:
            raise GenerationError("invalid WB staged row")
        if row.get("reportId") is not None and _positive_id(row["reportId"], "reportId") != report_id:
            raise GenerationError("foreign WB reportId in staged page")
        if row.get("reportType") is not None and int(row["reportType"]) != report_type:
            raise GenerationError("WB detail report type mismatch")
        item_id = _positive_id(row.get("rrdId"), "rrdId")
        if item_id <= previous or item_id in seen:
            raise GenerationError("non-increasing or duplicated WB rrdId")
        previous = item_id
        seen.add(item_id)
    if type(page.get("next_rrd_id")) is not int or page["next_rrd_id"] != previous:
        raise GenerationError("WB next rrdId mismatch")
    return previous


def _replay_or_advance(folder, state, report_id, report_type):
    cursor = state["current_rrd_id"]
    page_path = _checked(folder / ("page-" + str(cursor) + ".json"))
    payload = _read_json(page_path)
    if payload is None:
        return None
    next_id = _validate_page(payload, report_id, report_type, cursor)
    data = _canonical(payload)
    state["pages"].append({"cursor": cursor, "next_rrd_id": next_id,
                           "sha256": _sha(data)})
    state["current_rrd_id"] = next_id
    state["status"] = "RUNNING"
    _safe_write(folder / "state.json", _canonical(state))
    return {"status": "PAGE_STAGED", "cursor": next_id,
            "rows_this_page": len(payload["rows"]),
            "replayed_after_interruption": True}


def step_wb_detail(root, cabinet: str, year: int, report_id: int,
                   report_type: int, send, *, fault=None):
    """One durable step per invocation; never mark COMPLETE without HTTP 204."""
    if type(year) is not int or not 2024 <= year <= 2100:
        raise ValueError("invalid report year")
    if type(report_id) is not int or report_id <= 0 or type(report_type) is not int or report_type not in (1, 2):
        raise ValueError("invalid WB report identifier/type")
    dataset = "wb_weekly_finance_main" if report_type == 1 else "wb_weekly_finance_buyout"
    _validate(dataset, cabinet, str(year))
    folder = _dir(root, cabinet, year, report_id)
    with _lock(root, cabinet, dataset):
        _checked(folder)
        _ensure_scope_durable(folder)
        path = folder / "state.json"
        state = _read_json(path)
        if state is None:
            state = {"schema": 1, "cabinet": cabinet, "year": year,
                     "report_id": report_id, "report_type": report_type,
                     "current_rrd_id": 0, "pages": [], "status": "QUEUED"}
            _safe_write(path, _canonical(state))
        _validate_state(state, cabinet, year, report_id, report_type)
        if state["status"] == "STAGED_COMPLETE":
            # Check prior pages before returning an already-complete state.
            _verify_pages(folder, state, report_id, report_type)
            return {"status": "STAGED_COMPLETE", "current_rrd_id": state["current_rrd_id"],
                    "pages": len(state["pages"]), "provider_coverage_proven": False}
        # Replay a page written before the cursor's state update, no provider call.
        _verify_pages(folder, state, report_id, report_type)
        replay = _replay_or_advance(folder, state, report_id, report_type)
        if replay is not None:
            return {**replay, "pages": len(state["pages"]), "provider_calls": 0}
        request = Request("wb", WB_DETAIL + str(report_id),
                          {"limit": 10000, "rrdId": state["current_rrd_id"]})
        try:
            status, rows = send(request)
        except ProviderError as exc:
            if "quota busy" not in str(exc) and "rate limit" not in str(exc):
                raise
            state["status"] = "WAITING_RATE_LIMIT"
            _safe_write(path, _canonical(state))
            return {"status": "WAITING_RATE_LIMIT",
                    "current_rrd_id": state["current_rrd_id"],
                    "pages": len(state["pages"]), "provider_calls": 0,
                    "reason": "shared quota busy"}
        if status == 429:
            state["status"] = "WAITING_RATE_LIMIT"
            _safe_write(path, _canonical(state))
            return {"status": "WAITING_RATE_LIMIT",
                    "current_rrd_id": state["current_rrd_id"],
                    "pages": len(state["pages"]), "provider_calls": 1,
                    "reason": "provider rate limited"}
        if status == 204:
            _verify_pages(folder, state, report_id, report_type)
            if not state["pages"]:
                # The legacy source cannot silently treat an empty report as
                # complete; require separate empty-coverage reconciliation.
                raise ProviderError("empty WB report requires explicit source verification")
            state["status"] = "STAGED_COMPLETE"
            _safe_write(path, _canonical(state))
            return {"status": "STAGED_COMPLETE",
                    "current_rrd_id": state["current_rrd_id"],
                    "pages": len(state["pages"]), "provider_calls": 1,
                    "provider_coverage_proven": False}
        if status != 200 or not isinstance(rows, list) or not rows:
            raise ProviderError("invalid WB detail response; stage retained")
        page = {"schema": 1, "report_id": report_id,
                "report_type": report_type,
                "cursor": state["current_rrd_id"],
                "next_rrd_id": 0, "rows": rows}
        page["next_rrd_id"] = _positive_id(rows[-1].get("rrdId") if isinstance(rows[-1], dict) else None,
                                            "rrdId")
        _validate_page(page, report_id, report_type, state["current_rrd_id"])
        stage_path = folder / ("page-" + str(state["current_rrd_id"]) + ".json")
        _checked(stage_path)
        if stage_path.exists():
            raise GenerationError("staged cursor file already exists")
        _safe_write(stage_path, _canonical(page))
        if fault is not None:
            fault("after_page_fsync_before_state")
        result = _replay_or_advance(folder, state, report_id, report_type)
        return {**result, "replayed_after_interruption": False,
                "pages": len(state["pages"]), "provider_calls": 1}


def _verify_pages(folder, state, report_id, report_type):
    for entry in state["pages"]:
        file = _checked(folder / ("page-" + str(entry["cursor"]) + ".json"))
        data = file.read_bytes() if file.exists() else None
        if data is None or _sha(data) != entry["sha256"]:
            raise GenerationError("WB staged page missing or checksum mismatch")
        page = _read_json(file, required=True)
        if _validate_page(page, report_id, report_type, entry["cursor"]) != entry["next_rrd_id"]:
            raise GenerationError("WB staged page cursor mismatch")
    # Every uncommitted page must equal the current cursor, never skip orphan
    # chunks or silently include out-of-order page files.
    expected = {"page-" + str(x["cursor"]) + ".json" for x in state["pages"]}
    expected.add("page-" + str(state["current_rrd_id"]) + ".json")
    for item in folder.glob("page-*.json"):
        if item.name not in expected:
            raise GenerationError("unaccounted WB page file: manual review required")


def read_completed_wb_pages(root, cabinet: str, year: int, report_id: int,
                            report_type: int):
    """Return verified page iterator data after provider 204; no archive write."""
    dataset = "wb_weekly_finance_main" if report_type == 1 else "wb_weekly_finance_buyout"
    _validate(dataset, cabinet, str(year))
    folder = _dir(root, cabinet, year, report_id)
    with _lock(root, cabinet, dataset):
        state = _read_json(folder / "state.json", required=True)
        _validate_state(state, cabinet, year, report_id, report_type)
        if state["status"] != "STAGED_COMPLETE":
            raise GenerationError("WB detail still incomplete")
        _verify_pages(folder, state, report_id, report_type)
        # Returns JSON per staged page rather than copying a full report into
        # the in-memory wb_detail.all_rows aggregate.
        return [(_read_json(folder / ("page-" + str(entry["cursor"]) + ".json"),
                            required=True)["rows"]) for entry in state["pages"]]
