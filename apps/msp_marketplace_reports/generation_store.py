"""Experimental B7 immutable-generation storage, OFFLINE ONLY.

This is a separately opt-in core for B7. The existing archive.import_csv,
archive.verify, CLI and external CSV readers are NOT switched to it yet.
Only readers using read_active/read_generation receive a consistent snapshot.
No provider calls, network, credentials, automatic migration or recovery writes.
"""
from __future__ import annotations

import fcntl
import json
import os
import re
import uuid
from contextlib import contextmanager
from pathlib import Path

from .archive import DATASETS, _rows, _safe_write, _sha, _validate

_VERSION = 1
_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_MONTH_RE = re.compile(r"^monthly/(20\d{2}-(?:0[1-9]|1[0-2]))\.csv$")


class GenerationError(ValueError):
    pass


class CommitUncertainError(GenerationError):
    """The CURRENT switch may have occurred; inspect before retrying."""


def _unique_pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise GenerationError("duplicate JSON key")
        result[key] = value
    return result


def _constant_bad(value):
    raise GenerationError("nonstandard JSON constant")


def _strict_json(data: bytes):
    try:
        doc = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_pairs,
                         parse_constant=_constant_bad)
    except (UnicodeError, ValueError) as exc:
        raise GenerationError("invalid JSON control document") from exc
    if not isinstance(doc, dict):
        raise GenerationError("JSON control document must be object")
    return doc


def _integer(doc, key, actual):
    if type(doc.get(key)) is not int or doc[key] != actual:
        raise GenerationError("invalid integer field: " + key)


def _identifier(value):
    if type(value) is not str or not _ID_RE.fullmatch(value):
        raise GenerationError("invalid generation ID")
    return value


def _scope(root, dataset, cabinet, period):
    if dataset == "ozon_final_realization":
        if type(period) is not str or not re.fullmatch(r"20\d{2}", period):
            raise GenerationError("Ozon FINAL generation period must be a year")
        _validate(dataset, cabinet, period + "-01")
    else:
        _validate(dataset, cabinet, period)
    return Path(root).expanduser().resolve() / ".b7-generations" / dataset / cabinet / period


def _require_plain(path):
    """Never trust a symlink in the immutable store or its ancestors."""
    for element in (path, *path.parents):
        if element.is_symlink():
            raise GenerationError("symbolic link forbidden in generation store")


def _payload_pairs(dataset, cabinet, period, files):
    if not isinstance(files, dict) or not files:
        raise GenerationError("generation files required")
    if any(type(k) is not str or type(v) is not bytes for k, v in files.items()):
        raise GenerationError("generation files must be named bytes")
    csv_names = set()
    for name in files:
        if dataset == "ozon_final_realization":
            if name not in ("annual.csv", "annual.csv.meta.json"):
                match = _MONTH_RE.fullmatch(name[:-10] if name.endswith(".meta.json") else name)
                if not match or match.group(1)[:4] != period:
                    raise GenerationError("out-of-scope Ozon file")
        elif name not in ("data.csv", "data.csv.meta.json"):
            raise GenerationError("out-of-scope dataset file")
        if name.endswith(".csv"):
            csv_names.add(name)
        elif not name.endswith(".csv.meta.json"):
            raise GenerationError("unrecognized generation file name")
    if set(files) != csv_names | {name + ".meta.json" for name in csv_names}:
        raise GenerationError("CSV/manifest pairs required")
    if dataset == "ozon_final_realization":
        if "annual.csv" not in csv_names or len(csv_names) < 2:
            raise GenerationError("Ozon FINAL needs annual and at least one month")
    elif csv_names != {"data.csv"}:
        raise GenerationError("single CSV/manifest pair required")

    verified = {}
    monthly = {}
    annual = None
    for name in sorted(csv_names):
        if name == "annual.csv":
            expected_period = period
        elif name == "data.csv":
            expected_period = period
        else:
            expected_period = _MONTH_RE.fullmatch(name).group(1)
        raw = files[name]
        fields, rows = _rows(raw, DATASETS[dataset][1])
        manifest = _strict_json(files[name + ".meta.json"])
        if set(("schema", "rows", "bytes")) - set(manifest):
            raise GenerationError("missing integer fields")
        _integer(manifest, "schema", 1)
        _integer(manifest, "rows", len(rows))
        _integer(manifest, "bytes", len(raw))
        expectations = {"dataset": dataset, "cabinet": cabinet, "period": expected_period,
                        "status": "LOCAL_VERIFIED", "sha256": _sha(raw)}
        if any(type(manifest.get(k)) is not str or manifest[k] != v
               for k, v in expectations.items()):
            raise GenerationError("manifest identity/hash mismatch")
        if dataset.startswith("wb_weekly_finance_"):
            expected_type = "1" if dataset.endswith("_main") else "2"
            if "reportType" not in fields or any(row["reportType"] != expected_type
                                                 for row in rows.values()):
                raise GenerationError("WB reportType mismatch/missing")
        if dataset == "ozon_final_realization":
            if name != "annual.csv":
                if any(row["report_month"] != expected_period
                       or row["report_year"] != period for row in rows.values()):
                    raise GenerationError("Ozon monthly row period mismatch")
                if set(monthly) & set(rows):
                    raise GenerationError("duplicate key in Ozon months")
                monthly.update(rows)
            else:
                annual = rows
        verified[name] = len(rows)
    if dataset == "ozon_final_realization" and (
        set(monthly) != set(annual) or any(
            any(row.get(field, "") != annual[key].get(field, "")
                for field in set(row) | set(annual[key]))
            for key, row in monthly.items()
        )
    ):
        raise GenerationError("Ozon annual differs from monthly sources")
    return verified


def _descriptor(scope_name, generation, parent, files):
    return {"schema": _VERSION, "scope": scope_name, "generation": generation,
            "parent": parent,
            "files": [{"path": k, "sha256": _sha(files[k]), "bytes": len(files[k])}
                      for k in sorted(files)]}


def _read_generation(scope, generation, expected_digest=None):
    _identifier(generation)
    genpath = scope / "generations" / generation
    _require_plain(genpath)
    manifest_path = genpath / "generation.json"
    _require_plain(manifest_path)
    descriptor_raw = manifest_path.read_bytes()
    if expected_digest is not None and _sha(descriptor_raw) != expected_digest:
        raise GenerationError("generation descriptor hash mismatch")
    descriptor = _strict_json(descriptor_raw)
    _integer(descriptor, "schema", _VERSION)
    if descriptor.get("generation") != generation or descriptor.get("scope") != scope.name:
        raise GenerationError("generation scope/identity mismatch")
    parent = descriptor.get("parent")
    if parent is not None:
        _identifier(parent)
    entries = descriptor.get("files")
    if not isinstance(entries, list) or not entries:
        raise GenerationError("invalid generation file index")
    files = {}
    for item in entries:
        if not isinstance(item, dict) or set(item) != {"path", "sha256", "bytes"}:
            raise GenerationError("invalid generation entry")
        name = item["path"]
        if type(name) is not str or name in files:
            raise GenerationError("duplicate/invalid file name")
        # Validate paths before touching a file: exact relative allowlist below.
        if not (name in ("data.csv", "data.csv.meta.json",
                         "annual.csv", "annual.csv.meta.json")
                or _MONTH_RE.fullmatch(name[:-10] if name.endswith(".meta.json") else name)):
            raise GenerationError("untrusted generation path")
        target = genpath / name
        _require_plain(target)
        if not target.is_file():
            raise GenerationError("missing immutable generation file")
        raw = target.read_bytes()
        _integer(item, "bytes", len(raw))
        if type(item.get("sha256")) is not str or item["sha256"] != _sha(raw):
            raise GenerationError("immutable generation file checksum mismatch")
        files[name] = raw
    dataset, cabinet, period = scope.parts[-3:]
    _payload_pairs(dataset, cabinet, period, files)
    return {"generation": generation, "parent": parent, "files": files,
            "manifest_sha256": _sha(descriptor_raw)}


def _read_active_at(scope):
    current = scope / "CURRENT.json"
    _require_plain(current)
    if not current.exists():
        return None
    pointer = _strict_json(current.read_bytes())
    _integer(pointer, "schema", _VERSION)
    if set(pointer) != {"schema", "generation", "sha256"}:
        raise GenerationError("invalid CURRENT pointer")
    generation = _identifier(pointer["generation"])
    if type(pointer.get("sha256")) is not str:
        raise GenerationError("CURRENT digest must be string")
    return _read_generation(scope, generation, pointer["sha256"])


def read_active(root, dataset, cabinet, period):
    """Reader pins one immutable generation by reading CURRENT exactly once."""
    scope = _scope(root, dataset, cabinet, period)
    return _read_active_at(scope)


def read_generation(root, dataset, cabinet, period, generation):
    """Read an older pinned generation without consulting CURRENT."""
    scope = _scope(root, dataset, cabinet, period)
    return _read_generation(scope, generation)


@contextmanager
def _write_lock(scope):
    # Check *before* mkdir: an attacker-controlled symlink in an ancestor
    # must not cause our mkdir to create subdirectories outside archive root.
    _require_plain(scope)
    scope.mkdir(parents=True, exist_ok=True)
    _require_plain(scope)
    lock = scope / ".writer.lock"
    _require_plain(lock)
    fd = os.open(str(lock), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def _sync_dir(path):
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _orphans(scope, active_id):
    folder = scope / "generations"
    if not folder.exists():
        return []
    _require_plain(folder)
    ids = []
    for child in folder.iterdir():
        _require_plain(child)
        if not child.is_dir() or not _ID_RE.fullmatch(child.name):
            raise GenerationError("unknown entry in generation store")
        if child.name != active_id:
            # Old committed generations remain retained for pinned readers.
            # The distinction between old and orphan requires parent-chain walk.
            ids.append(child.name)
    return sorted(ids)


def publish_batch(root, dataset, cabinet, period, files, *,
                  expected_generation=None, fault=None):
    """Stage full scope, validate and switch CURRENT as one commit point.

    REQUIRED: expected_generation is the exact active generation when updating.
    No existing CSV paths are modified. Fault hook is for isolated tests only.
    """
    scope = _scope(root, dataset, cabinet, period)
    _payload_pairs(dataset, cabinet, period, files)
    def checkpoint(name):
        if fault is not None:
            fault(name)
    with _write_lock(scope):
        active = _read_active_at(scope)
        old_id = active["generation"] if active else None
        if active and active["files"] == files:
            return {"changed": False, "generation": old_id, "status": "COMMITTED"}
        if old_id != expected_generation:
            raise GenerationError("stale expected generation; re-read current")
        generation = uuid.uuid4().hex
        stage = scope / "generations" / generation
        _require_plain(stage)
        stage.mkdir(parents=True, exist_ok=False)
        _sync_dir(stage.parent)
        checkpoint("after_stage_dir")
        for filename in sorted(files):
            _safe_write(stage / filename, files[filename])
            checkpoint("after_file:" + filename)
        descriptor = _descriptor(scope.name, generation, old_id, files)
        descriptor_raw = (json.dumps(descriptor, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")) + "\n").encode("utf-8")
        _safe_write(stage / "generation.json", descriptor_raw)
        _sync_dir(stage)
        checkpoint("after_descriptor")
        _read_generation(scope, generation, _sha(descriptor_raw))
        checkpoint("before_commit")
        pointer = {"schema": _VERSION, "generation": generation,
                   "sha256": _sha(descriptor_raw)}
        pointer_raw = (json.dumps(pointer, sort_keys=True, separators=(",", ":"))
                       + "\n").encode("utf-8")
        try:
            _safe_write(scope / "CURRENT.json", pointer_raw)
            checkpoint("after_commit")
        except Exception as exc:
            raise CommitUncertainError("commit result uncertain; reconcile current") from exc
        return {"changed": True, "generation": generation, "parent": old_id,
                "status": "COMMITTED"}


def reconcile(root, dataset, cabinet, period):
    """Read-only-on-archive reconciliation. Never removes orphan evidence.

    Returns whether CURRENT selects a verified full generation. This is NOT
    yet an automatic restore or full B7 recovery mechanism.
    """
    scope = _scope(root, dataset, cabinet, period)
    with _write_lock(scope):
        try:
            active = _read_active_at(scope)
            generations = _orphans(scope, active["generation"] if active else None)
        except (OSError, ValueError) as exc:
            return {"status": "RECOVERY_REQUIRED", "error": str(exc)}
        if active is None:
            return {"status": "EMPTY" if not generations else "PENDING",
                    "unreferenced_generations": generations}
        return {"status": "ACTIVE_VERIFIED", "generation": active["generation"],
                "other_retained_generations": generations}
