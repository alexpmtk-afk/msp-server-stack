"""B7 experimental OFFLINE witnessed CURRENT repair (not automatic recovery).

Only an explicitly acknowledged, externally pinned generation/digest may be
selected. Local metadata alone cannot establish the last committed head.
Refuse any unaccounted generation, healthy divergent CURRENT, legacy archive,
or stale pointer bytes. Preserve exact preimage in a durable replayable journal.
This does NOT verify the authenticity of an operator-supplied external witness.
"""
from __future__ import annotations

import base64
import json
import os
import stat
from pathlib import Path

from .archive import _lock, _safe_write, _sha
from .generation_store import (
    GenerationError, _HASH_RE, _identifier, _ensure_scope_durable,
    _lineage, _orphans, _read_active_at, _read_generation, _require_plain,
    _scope, _strict_json, _sync_dir, _write_lock,
)
from .versioned_archive import _assert_no_legacy


class RestoreUncertainError(GenerationError):
    """CURRENT or journal state may have changed; retry with identical inputs."""

    def __init__(self, message, transaction=None):
        super().__init__(message)
        self.transaction = transaction


def _json_bytes(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False,
                       separators=(",", ":")) + "\n").encode("utf-8")


def _pointer_bytes(generation, descriptor_sha):
    return _json_bytes({"schema": 2, "generation": generation,
                        "sha256": descriptor_sha})


def _preimage(scope):
    path = scope / "CURRENT.json"
    _require_plain(path)
    if not path.exists():
        if path.is_symlink():
            raise GenerationError("CURRENT symbolic link forbidden")
        return None
    if not path.is_file():
        raise GenerationError("CURRENT is not a regular file")
    data = path.read_bytes()
    if len(data) > 16384:
        raise GenerationError("CURRENT pointer too large for evidence")
    return data


def _verify_witness(dataset, cabinet, period, generation, digest, reference):
    _identifier(generation)
    if type(digest) is not str or not _HASH_RE.fullmatch(digest):
        raise GenerationError("trusted descriptor pin must be SHA256 hex")
    if (type(reference) is not str or not reference.strip()
            or len(reference) > 160 or any(ord(ch) < 32 for ch in reference)):
        raise GenerationError("independent witness reference required")
    # This reference is an audit label, not a cryptographically verified proof.
    return {"dataset": dataset, "cabinet": cabinet, "period": period,
            "generation": generation, "descriptor_sha256": digest,
            "witness_reference": reference}


def _validate_journal_schema(record):
    # Python bool and float compare equal to int (True == 1, 1.0 == 1).
    # Reject before comparison, rewrite, or successful VERIFIED return.
    if type(record.get("schema")) is not int or record["schema"] != 1:
        raise GenerationError("invalid restore journal schema type/value")


def _resync_verified_journal(journal_dir: Path, journal: Path, transaction: str):
    """Finish possibly interrupted fsync after VERIFIED rename, even on retry.

    A visible VERIFIED is NOT evidence that the journal's parent directory
    was durably synced. Keep journal bytes untouched and retry both file and
    directory fsync; any failure is uncertain, never a successful return.
    """
    try:
        _ensure_scope_durable(journal_dir)
        fd = os.open(str(journal), os.O_RDONLY | os.O_NOFOLLOW)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise GenerationError("restore journal must be regular file")
            os.fsync(fd)
        finally:
            os.close(fd)
        _sync_dir(journal_dir)
    except Exception as exc:
        raise RestoreUncertainError(
            "VERIFIED journal sync uncertain; retry identical transaction",
            transaction,
        ) from exc


def repair_current_with_witness(root: Path, dataset: str, cabinet: str,
                                scope_period: str, *, generation: str,
                                expected_digest: str,
                                expected_current_sha256: str | None,
                                witness_reference: str,
                                acknowledged: bool = False, fault=None):
    """Manual CAS repair of missing/corrupt CURRENT with journaled evidence.

    expected_current_sha256=None means CURRENT must be missing.
    When CURRENT is corrupt, its exact raw SHA256 must be supplied.
    Healthy CURRENT pointing to another head is never overwritten.
    All stored generations must belong to the nominated trusted lineage:
    if another staged/possibly committed version exists, refuse instead of
    guessing what was last committed.

    A human-supplied witness_reference is NOT independently authenticated.
    The owner must separately establish that the nominated pin was the actual
    authorized confirmed head. No automatic selection by filename/mtime/UUID.
    """
    if acknowledged is not True:
        raise GenerationError("explicit independent witness acknowledgment required")
    if expected_current_sha256 is not None and (
        type(expected_current_sha256) is not str
        or not _HASH_RE.fullmatch(expected_current_sha256)
    ):
        raise GenerationError("expected current byte SHA256 must be hex or None")
    witness = _verify_witness(dataset, cabinet, scope_period,
                              generation, expected_digest, witness_reference)
    scope = _scope(root, dataset, cabinet, scope_period)
    _require_plain(scope)
    if not scope.exists() or not (scope / ".writer.lock").is_file():
        raise GenerationError("cannot restore scope without existing writer lock")
    # For FINAL the legacy inventory is yearly; adapter accepts any month.
    sample_period = (scope_period + "-01" if dataset == "ozon_final_realization"
                     else scope_period)
    _assert_no_legacy(Path(root).expanduser(), dataset, cabinet, sample_period)
    def checkpoint(label):
        if fault is not None:
            fault(label)
    # Match both normal importers' lock order exactly.
    with _lock(root, cabinet, dataset):
        with _write_lock(scope):
            _assert_no_legacy(Path(root).expanduser(), dataset, cabinet, sample_period)
            candidate = _read_generation(scope, generation, expected_digest)
            trusted = _lineage(scope, candidate)
            old = _preimage(scope)
            observed_sha = _sha(old) if old is not None else None
            desired = _pointer_bytes(generation, expected_digest)
            # A healthy but different CURRENT is not repaired by overwriting it.
            healthy = None
            if old is not None:
                try:
                    healthy = _read_active_at(scope)
                    if healthy is not None:
                        _lineage(scope, healthy)
                except (OSError, ValueError):
                    healthy = None
            if healthy is not None and (
                healthy["generation"] != generation
                or healthy["manifest_sha256"] != expected_digest
            ):
                raise GenerationError("healthy divergent CURRENT must not be rolled back")
            # A verified different CURRENT is a clear no-rollback refusal;
            # only then evaluate unaccounted generations for unknown history.
            extra = _orphans(scope, trusted)
            if extra:
                raise GenerationError(
                    "UNRESOLVED_HEAD: non-ancestral generations need independent decision"
                )
            already_new = (old == desired and healthy is not None)
            if not already_new and observed_sha != expected_current_sha256:
                raise GenerationError("stale CURRENT byte CAS; do not alter evidence")
            transaction = _sha(_json_bytes({
                "witness": witness, "expected_previous_sha256": expected_current_sha256,
                "desired_sha256": _sha(desired)
            }))[:32]
            journal_dir = scope / "restore-journal"
            journal = journal_dir / (transaction + ".json")
            _require_plain(journal)
            # An uncompleted *different* repair requires separate reconciliation.
            if journal_dir.exists():
                _require_plain(journal_dir)
                for item in journal_dir.iterdir():
                    _require_plain(item)
                    if item.name == journal.name:
                        continue
                    if not item.is_file() or not item.name.endswith(".json"):
                        raise GenerationError("unexpected restore journal entry")
                    record = _strict_json(item.read_bytes())
                    _validate_journal_schema(record)
                    if record.get("state") != "VERIFIED":
                        raise GenerationError("another unfinished restore journal")
            old_b64 = None if already_new else (
                base64.b64encode(old).decode("ascii") if old is not None else None
            )
            expected_record = {
                "schema": 1, "transaction": transaction, "witness": witness,
                "expected_previous_sha256": expected_current_sha256,
                "desired_sha256": _sha(desired), "previous_b64": old_b64,
            }
            record = None
            if journal.exists():
                record = _strict_json(journal.read_bytes())
                _validate_journal_schema(record)
                if set(record) != set(expected_record) | {"state"} or any(
                    record.get(k) != v for k, v in expected_record.items()
                    if k != "previous_b64"
                ):
                    raise GenerationError("restore journal identity mismatch")
                if record.get("state") not in ("PREPARED", "VERIFIED"):
                    raise GenerationError("invalid restore journal state")
                # Exact preimage is immutable across retry; do not require it
                # to equal the postcommit CURRENT.
                if not already_new and record.get("previous_b64") != old_b64:
                    raise GenerationError("restore journal preimage differs")
                # Existing PREPARED journal is evidence of the *original*
                # preimage; never erase it on a post-CURRENT retry.
                preserved_b64 = record.get("previous_b64")
                if preserved_b64 is not None:
                    if type(preserved_b64) is not str:
                        raise GenerationError("restore preimage must be encoded bytes")
                    try:
                        preserved_raw = base64.b64decode(preserved_b64, validate=True)
                    except (ValueError, base64.binascii.Error) as exc:
                        raise GenerationError("invalid journal preimage encoding") from exc
                    if _sha(preserved_raw) != expected_current_sha256:
                        raise GenerationError("journal preimage hash mismatch")
                elif expected_current_sha256 is not None:
                    raise GenerationError("missing original CURRENT evidence")
                expected_record["previous_b64"] = preserved_b64
                if already_new and (record["state"] == "VERIFIED"):
                    _resync_verified_journal(journal_dir, journal, transaction)
                    return {"status": "CURRENT_VERIFIED", "generation": generation,
                            "manifest_sha256": expected_digest,
                            "transaction": transaction, "changed_in_attempt": False,
                            "local_chain_verified": True,
                            "external_witness_authenticated_by_code": False}
            elif already_new:
                raise GenerationError("CURRENT already valid without matching recovery journal")
            if record is None:
                # Stage durable evidence BEFORE attempting to change CURRENT.
                _ensure_scope_durable(journal_dir)
                record = dict(expected_record, state="PREPARED")
                try:
                    _safe_write(journal, _json_bytes(record))
                    checkpoint("after_prepare")
                except Exception as exc:
                    raise RestoreUncertainError(
                        "restore evidence preparation uncertain", transaction
                    ) from exc
            else:
                # Resync even if journal existed after interrupted fsync.
                _ensure_scope_durable(journal_dir)
                try:
                    _safe_write(journal, _json_bytes(record))
                except Exception as exc:
                    raise RestoreUncertainError(
                        "restore evidence retry fsync uncertain", transaction
                    ) from exc
            # Recheck CURRENT bytes after durable journal preparation. Another
            # cooperative writer cannot advance under our two held locks.
            current_now = _preimage(scope)
            if not already_new and current_now != old:
                raise RestoreUncertainError("CURRENT changed after preflight", transaction)
            if not already_new:
                try:
                    checkpoint("before_switch")
                    _safe_write(scope / "CURRENT.json", desired)
                    checkpoint("after_switch")
                except Exception as exc:
                    raise RestoreUncertainError(
                        "CURRENT switch uncertain; inspect and retry exact transaction",
                        transaction,
                    ) from exc
            try:
                active = _read_active_at(scope)
                if active is None or active["generation"] != generation or (
                        active["manifest_sha256"] != expected_digest):
                    raise GenerationError("restored CURRENT identity mismatch")
                _lineage(scope, active)
                checkpoint("after_verify")
                _safe_write(journal, _json_bytes(dict(expected_record, state="VERIFIED")))
                checkpoint("after_journal_verified")
            except Exception as exc:
                raise RestoreUncertainError(
                    "post-switch verification/journal uncertain", transaction
                ) from exc
            return {"status": "CURRENT_VERIFIED", "generation": generation,
                    "manifest_sha256": expected_digest,
                    "transaction": transaction,
                    "changed_in_attempt": not already_new,
                    "local_chain_verified": True,
                    "external_witness_authenticated_by_code": False}
