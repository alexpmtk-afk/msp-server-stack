# Consolidated discovery recovery and operator action — 2026-11-07

## Established facts and uncertainty

WB Laser Master has20 completed report receipts /15404 rows. Current failure is
list discovery, not detail-page size: exact nonce cdf5beea55974566a308b88b6850a599,
plan7dffbfc... for2025-12-29..2026-01-04, one HTTP200, zero unknown outcomes,
original entries1 of2, offset0, INVALID_DISCOVERY_METADATA. The old module threw
away the four-field projection before recording a validation reason. Exact bad
row cannot be recovered from the readable evidence; prior-year overlap is a
hypothesis, not an established production cause.

Earlier failures are distinct: numerical detail cursor ordering was wrong;
standalone60-second diagnostics repeated full archive reads and timed out;
now a list-validation failure loses its original evidence. Monitoring detects
these but does not make protected source code writable or cure unknown input.
No blanket root access or generic automatic HOLD bypass is introduced.

## Consolidated repair

- Retain bounded checksum-sealed ID/type/date metadata BEFORE semantic validation.
  Unexpected values become type markers; financial fields and arbitrary strings
  are excluded. Expose exact fixed reason + row index through existing public
  diagnostics. Do not expose credentials or original financial detail rows.
- Replay saved valid list metadata locally after interruption, without HTTP or a
  new budget entry. An uncertain dispatch with no retained evidence HOLDs.
- Validate every source identity/date and duplicate before classifying coverage.
  Valid wholly-other-year reports remain retained/excluded, not selected for2026;
  original source_count still advances the provider offset. Complete crossing
  weeks retain their original dates and ALL detail rows. No silent correction of
  malformed rows or coercion of booleans/IDs/dates.
- Cache a validated immutable publication snapshot only within ONE serialized
  root selection, separately per dataset/cabinet/year. Every report's staged and
  published business values still verify. New selection gets a new snapshot.
- Standalone root diagnostic deadline300s (previous60), installer wait330s for
  that fixed unit only; same network/credential/filesystem restrictions.
- Worker exceptions retain phase location/class/errno without exception text.
- A new failed discovery invocation reopens error investigation; an old
  blocked_external incident must not hide a different new nonce.

## Exact one-time recovery

Only the unchanged sealed discovery state85d62257... and known plan7dffbfc... can
reopen once. Under the existing executor lock, require the root-owned original
receipt AND all-nonce journal evidence of exactly one HTTP200 and no unknowns.
Original entries1/offset0 stay; the new evidence-retaining attempt spends entry2
of the SAME existing two-entry ledger. No reconstruction, reset, ceiling increase,
unknown-attempt retry or modification of completed reports. Every other HOLD stays.
If that response is still invalid, its actual sanitized metadata and reason are
retained/readable through the installed diagnose command; this is not a promise
that unseen provider data will pass validation.

## One owner operation

Run ROOT_REPAIR_AND_RESUME.txt as Linux root in the established console. It stages
and hash-checks the self-contained updater, verifies the EXACT installed56da...
release/wiring and idle services, snapshots its own wiring, installs a separate
immutable release and runs read-only diagnostics. Then it hash-checks the user
recovery program and drops to hermes. No password is requested in chat.

User recovery refuses concurrent/foreign/changed runs, backs up original user
state/wrapper, durably records DISPATCHING, invokes the existing fixed wake client
once, saves its exact root receipt and restarts the existing scoped background
driver ONLY after PASS. New HOLD stays stopped with evidence; repeating the
launcher cannot create another recovery attempt. Driver counters/history remain;
its reviewed new root-controller hash is pinned. Other cabinets, daily timers,
Ozon, gateway, existing credentials and original completed report data stay intact.

Rollback is updater --rollback from its root-owned snapshot: wiring only,
archives/evidence/spent requests retained. Unexpected drift/partial installation
is refusal, never overwrite. This update does not grant future arbitrary root
code deployment; ordinary wakes/diagnostics are already available without root.

## Acceptance, not merely process start

Offline tests exercise original failure conditions, valid prior-year exclusion,
full crossing week, malformed/missing/duplicate/reversed metadata, crash replay,
unknown-dispatch HOLD, same-ledger1->2 migration, generated user launcher and
re-invocation refusal, snapshot locality and read-only publication verification.
Synthetic payloads are not production downloads. Real acceptance requires the
new root receipt, same ledger progression, closed network, independent verified
publication and finally reconciliation of every available closed report/window
for the cabinet/year. A single successful report or active PID is not full-year
completion. Exact remaining volume/runtime is not established before discovery.
