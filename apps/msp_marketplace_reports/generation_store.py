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

_VERSION = 2  # New opt-in store; no production generations exist yet.
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
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
    expanded = Path(root).expanduser()
    # Do not silently resolve the configured root through a symlink.
    _require_plain(expanded)
    return expanded.resolve() / ".b7-generations" / dataset / cabinet / period


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


def _descriptor(scope_name, generation, parent, parent_sha256, files):
    if (parent is None) != (parent_sha256 is None):
        raise GenerationError("parent identity/digest must occur together")
    if parent_sha256 is not None and not _HASH_RE.fullmatch(parent_sha256):
        raise GenerationError("invalid parent descriptor digest")
    return {"schema": _VERSION, "scope": scope_name, "generation": generation,
            "parent": parent, "parent_sha256": parent_sha256,
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
    if set(descriptor) != {"schema", "scope", "generation", "parent", "parent_sha256", "files"}:
        raise GenerationError("invalid generation descriptor fields")
    if descriptor.get("generation") != generation or descriptor.get("scope") != scope.name:
        raise GenerationError("generation scope/identity mismatch")
    parent = descriptor.get("parent")
    digest = descriptor.get("parent_sha256")
    if parent is not None:
        _identifier(parent)
        if type(digest) is not str or not _HASH_RE.fullmatch(digest):
            raise GenerationError("invalid parent digest")
    elif digest is not None:
        raise GenerationError("parent digest without parent")
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
    return {"generation": generation, "parent": parent,
            "parent_sha256": digest, "files": files,
            "manifest_sha256": _sha(descriptor_raw)}


def _read_active_at(scope):
    current = scope / "CURRENT.json"
    _require_plain(current)
    if not current.exists():
        # A missing pointer is distinguishable from pristine scope only if
        # no generation evidence exists. Never classify missing CURRENT
        # and existing generations as uncommitted.
        folder = scope / "generations"
        _require_plain(folder)
        if folder.exists() and any(folder.iterdir()):
            raise GenerationError("UNKNOWN_COMMIT_STATE: CURRENT missing with generation evidence")
        return None
    pointer = _strict_json(current.read_bytes())
    _integer(pointer, "schema", _VERSION)
    if set(pointer) != {"schema", "generation", "sha256"}:
        raise GenerationError("invalid CURRENT pointer")
    generation = _identifier(pointer["generation"])
    if type(pointer.get("sha256")) is not str or not _HASH_RE.fullmatch(pointer["sha256"]):
        raise GenerationError("CURRENT digest must be SHA256 hex")
    return _read_generation(scope, generation, pointer["sha256"])


def read_active(root, dataset, cabinet, period):
    """Read the CURRENT-anchored complete committed chain as a pinned snapshot."""
    scope = _scope(root, dataset, cabinet, period)
    active = _read_active_at(scope)
    if active is not None:
        _lineage(scope, active)
    return active


def read_generation(root, dataset, cabinet, period, generation, *,
                    expected_digest):
    """Read only a CURRENT-anchored committed ancestor using caller's pin.

    A staged candidate is never public, even if its generation.json is valid.
    A pin must be obtained from a previous trusted read/commit receipt; this
    digest is an integrity assertion, not a signature or secret capability.
    """
    if type(expected_digest) is not str or not _HASH_RE.fullmatch(expected_digest):
        raise GenerationError("committed reader requires expected descriptor SHA256 pin")
    scope = _scope(root, dataset, cabinet, period)
    active = _read_active_at(scope)
    if active is None:
        raise GenerationError("no committed CURRENT generation")
    trusted = _lineage(scope, active)
    if generation not in trusted:
        raise GenerationError("generation not in committed CURRENT ancestry")
    expected = trusted[generation]
    if expected != expected_digest:
        raise GenerationError("pinned generation digest mismatch")
    return _read_generation(scope, generation, expected_digest)


def _ensure_scope_durable(scope):
    """Resumable durable directory initialization for the entire scope chain.

    Existing directories are *not* evidence of completed fsync. A previous
    mkdir can succeed while its parent fsync fails (or the process dies).
    Re-sync the name in its parent and the directory itself on EVERY attempt,
    including retrying existing levels, before any CURRENT commit.
    """
    _require_plain(scope)
    scope = Path(scope)
    directories = list(reversed((scope, *scope.parents)))
    for folder in directories[1:]:  # anchor itself has no parent in this path
        _require_plain(folder)
        if not folder.exists():
            try:
                folder.mkdir()  # never implicitly create unverified ancestors
            except FileExistsError:
                # Cooperating initializers may race before acquiring flock;
                # still validate and fsync the directory on this attempt.
                pass
        if not folder.is_dir():
            raise GenerationError("non-directory component in generation store")
        # Neither call may be skipped just because folder already exists.
        _sync_dir(folder.parent)
        _sync_dir(folder)


@contextmanager
def _write_lock(scope):
    _ensure_scope_durable(scope)
    lock = scope / ".writer.lock"
    _require_plain(lock)
    if lock.exists() and not lock.is_file():
        raise GenerationError("invalid writer lock")
    fd = os.open(str(lock), os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        os.fsync(fd)
        _sync_dir(scope)  # durability of the newly created lock name
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


def _lineage(scope, active):
    """Return CURRENT-anchored {generation:descriptor_sha256} for each ancestor.

    Parent links are bound by the child descriptor digest. Repacking an
    apparently consistent old CSV/metadata/descriptor cannot silently
    rewrite previously committed history while CURRENT remains unchanged.
    """
    accepted = {}
    item = active
    while item is not None:
        name = item["generation"]
        if name in accepted:
            raise GenerationError("cyclic generation parent chain")
        accepted[name] = item["manifest_sha256"]
        parent = item["parent"]
        item = (_read_generation(scope, parent, item["parent_sha256"])
                if parent is not None else None)
    return accepted


def _orphans(scope, committed):
    folder = scope / "generations"
    if not folder.exists():
        return []
    _require_plain(folder)
    ids = []
    for child in folder.iterdir():
        _require_plain(child)
        if not child.is_dir() or not _ID_RE.fullmatch(child.name):
            raise GenerationError("unknown entry in generation store")
        if child.name not in committed:
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
        old_digest = active["manifest_sha256"] if active else None
        # An interrupted, uncommitted generation is evidence requiring an
        # explicit recovery decision, not a candidate to silently overwrite.
        if _orphans(scope, _lineage(scope, active)):
            raise GenerationError("pending generation requires reviewed recovery")
        if active and active["files"] == files:
            return {"changed": False, "generation": old_id,
                    "manifest_sha256": old_digest, "status": "COMMITTED"}
        if old_id != expected_generation:
            raise GenerationError("stale expected generation; re-read current")
        generation = uuid.uuid4().hex
        stage = scope / "generations" / generation
        _require_plain(stage)
        # The first generation also introduces the "generations" directory:
        # fsync its name in scope, then the stage name in generations.
        _ensure_scope_durable(stage.parent)
        stage.mkdir(exist_ok=False)
        _sync_dir(stage.parent)
        _sync_dir(stage)
        checkpoint("after_stage_dir")
        for filename in sorted(files):
            _safe_write(stage / filename, files[filename])
            checkpoint("after_file:" + filename)
        descriptor = _descriptor(scope.name, generation, old_id, old_digest, files)
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
                "manifest_sha256": _sha(descriptor_raw), "status": "COMMITTED"}


def reconcile(root, dataset, cabinet, period):
    """Read-only-on-archive reconciliation. Never removes orphan evidence.

    Returns whether CURRENT selects a verified full generation. This is NOT
    yet an automatic restore or full B7 recovery mechanism.
    """
    scope = _scope(root, dataset, cabinet, period)
    _require_plain(scope)
    if not scope.exists():
        return {"status": "EMPTY", "uncommitted_generations": []}
    if not (scope / ".writer.lock").is_file():
        return {"status": "RECOVERY_REQUIRED", "error": "missing scope lock"}
    with _write_lock(scope):
        try:
            active = _read_active_at(scope)
            generations = _orphans(scope, _lineage(scope, active))
        except (OSError, ValueError) as exc:
            return {"status": ("UNKNOWN_COMMIT_STATE" if
                    "UNKNOWN_COMMIT_STATE" in str(exc) else "RECOVERY_REQUIRED"),
                    "error": str(exc)}
        if active is None:
            return {"status": "EMPTY" if not generations else "PENDING",
                    "uncommitted_generations": generations}
        if generations:
            return {"status": "RECOVERY_REQUIRED", "generation": active["generation"],
                    "uncommitted_generations": generations}
        return {"status": "ACTIVE_VERIFIED", "generation": active["generation"]}
