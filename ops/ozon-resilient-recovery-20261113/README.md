# Recoverable Ozon Nov1–13 collection —13.11.2026

PREPARED_NOT_INSTALLED. Original actual service is still HOLD/failed. No root
recovery service or provider continuation has been activated by these tests.
Owner explicitly authorized pausing and continuing safely after interruptions.

## Confirmed state and diagnosis

Original root release /var/lib/msp-ozon-current-accruals.ukayjhrw remains intact.
Dmitrieva13days/169rows accepted; Novokshenov1day/37rows retained, Laser not started.
Original worker stopped SIGTERM during an automatic Ubuntu update/systemd
reexecution. Exact historical signal sender is not recorded in the supplied log.
Old controller could stop a live process after losing its start notification;
this bug was independently reproduced without provider calls.

## Fixed behavior and boundaries

- Nonblocking same-unit start; distinguish client notification failure from the
  actual service state. Reattach to an owned live invocation, never start twice.
- All retained entries/raw bytes/meta/cursors/summaries are reconciled before
  any new transport. Completed days and completed cabinets are reused. Original
  128 sender entries per cabinet are cumulative, not reset by recovery.
- Current interrupted scope remains Nov1–13, all3cabinets, CURRENT dataset only.
  JanOct/WB/realization are neither refetched nor rewritten. Current data remain
  provisional. This does not silently advance to another business date.
- Resume after worker termination from saved pages/day checkpoints. Complete old
  multi-page days replay locally; publication acknowledgement is idempotent and
  derived CSV/summary/result writes are atomic. Existing source bytes unchanged.
- Temporary controller/manager, DNS or pre-entry quota outages pause; root
  service restarts after15sec and resumes after reboot within one fixed24h lease.
  The wrapper waits through root restart cycles; common run.py verifies final
  source/publication consistency. Paused states are actual observed conditions,
  not manually asserted activity or heartbeats.
- Unknown HTTP outcomes, corrupt/orphan pages, expired unfinished cursors,
  foreign invocation/control drift, exhausted budget remain HOLD/no blind retry.
  Authorization expiry is terminal HOLD and closes only exact owned activation;
  it does not reset budget or silently extend the window. An unrelated process
  or foreign activation is never stopped or cleaned up by the recovery path.
- DONE/HOLD conditions prevent replay at boot; transient root exit75 restarts,
  unsafe exit2 does not. No new model calls, timer, queue, bot restart or update
  disabling. All business work remains inside the existing shared executor,
  controller flock and Redis quota.

## Installation and verification

One root Bash line in ROOT_OZON_RECOVERY.txt copies a pinned launcher to a fresh
root-owned snapshot, validates archive members/outer+nested manifests, then
installs only the fixed recovery root unit and one-unit/start-only Hermes rule.
No infrastructure/runtime/account recreation. Old service/code/receipts retained.
Preflight pins original release manifest and interruption receipt, validates
accepted runtime/base unit, quota config, source pages/budgets and real completed
Dmitrieva verifier. Refuses active/foreign worker and any existing recovery setup.
One private claims file preserves original nonces for started cabinets and seals
one24h recovery deadline, never credentials in public receipts.

The new unit is enabled only for recovery across boot, not a recurring fetch.
A partial install is not automatically replayed. Cleanup validates exact owned
hashes, never stops a live process on notification failure, and removes its
start rule after verified completion. Original failed task remains historical;
new recovery task records a distinct execution with declarative counters/pauses.

Final read-only entry: /usr/bin/python3 -I -B ROOT/controller.py --verify.
Public receipt: /var/lib/msp-finance-control/results/ozon-current-recovery-20261113.json.

## Acceptance evidence

14 network-denied/local tests PASS on3.14 and3.12 against actual extracted payload:
notification loss, inactive reconciliation, terminal receipt/no restart, unsafe
failure/HOLD, old multi-page replay, same generation/budget/bytes, missing/orphan
response/HOLD, expired cursor/HOLD, pre-entry quota pause, nonroot refusal, live
cleanup refusal, root restart reattachment and service restart/terminal gates.

Separate harmless actual user-systemd fixture PASS: managed process survives
simulated notification loss, exactly one launch and verified completion, zero
provider/root/Redis changes. It is not a root-service/provider/reboot acceptance.
Root installation and real Novokshenov continuation remain pending owner command.
