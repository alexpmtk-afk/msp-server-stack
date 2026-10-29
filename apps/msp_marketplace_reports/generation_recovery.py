"""Explicit, offline, limited B7 recovery: quarantine uncommitted candidates.

This only works when CURRENT already selects a fully VERIFIED committed chain
and the operator supplies its exact generation + descriptor digest. It never
guesses a head after CURRENT disappears and never restores a corrupt active
generation. A full journalled restoration/migration protocol is still open.

The quarantine operation preserves each abandoned generation directory intact
in the same filesystem, changes no CURRENT, and is retryable after an
interrupted rename/fsync. Only explicitly approved candidate IDs are handled.
"""
from __future__ import annotations

import os
from pathlib import Path

from .generation_store import (
    GenerationError, _HASH_RE, _identifier, _lineage, _orphans,
    _read_active_at, _require_plain, _scope, _sync_dir, _write_lock,
    _ensure_scope_durable,
)


class RecoveryUncertainError(GenerationError):
    """Some evidence may have moved or its fsync may be incomplete.

    moved_in_attempt is observed progress, NOT a durability guarantee.
    Resuming must resync both directories for already moved candidates.
    """

    def __init__(self, message, *, moved_in_attempt=(), candidate=None):
        super().__init__(message)
        self.moved_in_attempt = tuple(moved_in_attempt)
        self.candidate = candidate


def quarantine_uncommitted(root: Path, dataset: str, cabinet: str,
                           scope_period: str, *, expected_generation: str,
                           expected_digest: str, candidates: list[str],
                           acknowledged: bool = False, fault=None):
    """Explicitly retain orphan evidence, with CAS under the publisher lock.

    CRITICAL: Never infer an unknown CURRENT is empty or uncommitted.
    Preconditions are a valid active committed chain AND an externally pinned
    exact active generation/digest. No automatic removal or snapshot rollback.
    """
    if acknowledged is not True:
        raise GenerationError("explicit operator acknowledgment required")
    _identifier(expected_generation)
    if type(expected_digest) is not str or not _HASH_RE.fullmatch(expected_digest):
        raise GenerationError("expected descriptor SHA256 pin required")
    if not isinstance(candidates, list) or not candidates:
        raise GenerationError("explicit nonempty list of candidate IDs required")
    if any(type(c) is not str for c in candidates):
        raise GenerationError("invalid candidate ID")
    candidates = [_identifier(c) for c in candidates]
    if len(candidates) != len(set(candidates)):
        raise GenerationError("duplicate candidate ID")

    scope = _scope(root, dataset, cabinet, scope_period)
    _require_plain(scope)
    if not scope.exists() or not (scope / ".writer.lock").is_file():
        raise GenerationError("no existing locked committed scope")
    with _write_lock(scope):
        active = _read_active_at(scope)  # missing/corrupt CURRENT raises
        if active is None:
            raise GenerationError("no committed CURRENT available")
        trusted = _lineage(scope, active)
        if (active["generation"] != expected_generation
                or active["manifest_sha256"] != expected_digest):
            raise GenerationError("stale recovery pin / CURRENT changed")
        pending = set(_orphans(scope, trusted))
        if set(candidates) & set(trusted):
            raise GenerationError("cannot quarantine committed generation")
        evidence = scope / "evidence"
        _require_plain(evidence)
        # Full-plan preflight: reject *every* source/target conflict before
        # moving the first candidate. This keeps ordinary validation errors
        # mutation-free, including when the second candidate is invalid.
        state = {}
        for candidate in candidates:
            source = scope / "generations" / candidate
            target = evidence / candidate
            _require_plain(source)
            _require_plain(target)
            if target.exists():
                if not target.is_dir() or source.exists():
                    raise GenerationError("candidate present in both stage and evidence or invalid evidence")
                state[candidate] = "already_retained"
            elif source.is_dir() and candidate in pending:
                state[candidate] = "to_move"
            else:
                raise GenerationError("candidate ID missing from pending/evidence inventory")
        if pending - set(candidates):
            raise GenerationError("unlisted uncommitted generations; refuse partial selection")
        if set(candidates) != pending | {c for c, kind in state.items()
                                         if kind == "already_retained"}:
            raise GenerationError("candidate ID missing from pending/evidence inventory")
        # Creation itself is durable/retry-safe. No archived evidence is deleted.
        _ensure_scope_durable(evidence)
        moved = []
        resynced = []
        for candidate in sorted(candidates):
            source = scope / "generations" / candidate
            target = evidence / candidate
            try:
                if state[candidate] == "to_move":
                    if fault is not None:
                        fault("before_evidence_rename:" + candidate)
                    os.replace(source, target)  # same-fs atomic directory rename
                    moved.append(candidate)  # observed, not necessarily durable
                # R96-1: EVEN when the target already exists from a prior
                # failed fsync/SIGKILL, repeat BOTH directory fsync operations
                # before success. Existence proves neither completed.
                _sync_dir(source.parent)
                _sync_dir(evidence)
                resynced.append(candidate)
                if fault is not None:
                    fault("after_evidence_fsync:" + candidate)
            except Exception as exc:
                raise RecoveryUncertainError(
                    "evidence relocation/sync uncertain; partial progress="
                    + ",".join(moved) + "; candidate=" + candidate
                    + "; reconcile and retry with same pin",
                    moved_in_attempt=moved, candidate=candidate,
                ) from exc
        # No generation was selected by mtime or UUID; active remains exact.
        post = _read_active_at(scope)
        if (post is None or post["generation"] != expected_generation or
                post["manifest_sha256"] != expected_digest):
            raise RecoveryUncertainError("CURRENT changed during evidence relocation")
        if _orphans(scope, _lineage(scope, post)):
            raise RecoveryUncertainError("unexpected pending generation after quarantine")
        return {"status": "EVIDENCE_RETAINED",
                "committed_generation": expected_generation,
                "manifest_sha256": expected_digest,
                "candidates": sorted(candidates),
                "moved_in_this_attempt": moved,
                "resynced_candidates": resynced,
                "current_unchanged": True}
