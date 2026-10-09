# Hermes Operator Layer — master report

Base SHA: 2dc79bd43343fdf37d88dab22e9fff7acca66c5d. Overall PARTIAL. No production brokers installed.

| Block | Status | Tests / evidence | Deployed / remaining gap |
|---|---|---|---|
| 1 Bridge separation | BLOCKED BY OWNER ACTION | 2 local boundary tests PASS; local smoke PASS; bridge patch in operator-evidence | Private live fetch/push unavailable; no fresh Actions transport acceptance |
| 2 Capability registry | IN PROGRESS | — | — |
| 3 GitHub broker | PENDING | — | App provisioning required |
| 4 REMOTE broker | PENDING | — | root-owned installation required |
| 5 Production release | PENDING | — | protected releases/service identity required |
| 6 Runner isolation | PENDING | — | admin migration required |
| 7 Backup/restore | PENDING | — | — |
| 8 Google RO | PENDING | — | private consent/fixture required |
| 9 Task dispatch | PENDING | — | — |
| 10 Workflow | PENDING | — | — |
| 11 Telegram E2E | BLOCKED | Not run | Requires installed/authorized brokers |

## BLOCK 12 — Mandatory durable orchestration
Status: PARTIAL (local implementation verified; live integration pending).
Code: tasks.py, task_journal.py, Operator skill, capability hermes.durable_tasks.
Tests: test_tasks.py includes separate worker processes and real commit/crash recovery.
Deployed: no Gateway changes; journal library in development worktree only.
Remaining gap: Block 9 dispatch + broker idempotency adapters + actual Codex turns/Gateway restart + final Telegram delivery. Not an overall PASS.
Recovery note: prior blocks 2–7 have local commits through 72868e9; table above predates those commits and does not constitute production acceptance.

## BLOCK 13 — Mandatory multipart input collection
Status: PARTIAL. Local numbered/manual collection, persistence, receipts, atomic Durable Task linkage and before-debounce ingress are implemented. No production changes.
Tests: test_multipart.py and test_multipart_ingress.py; real pause, crash-in-transaction, concurrent recovery, unchanged debounce harness. Details: MULTIPART_TASKS.md.
Acceptance gap: scoped Block 9 dispatcher and actual early Telegram ingress seam deployment; real user's three-part Telegram E2E not run. Overall PASS forbidden.

## BLOCK 9 — independent worker core
Status: PARTIAL. Persistent additive migration, historic-probe tombstones, scoped
independent loop, fencing/heartbeat, receipt readback, atomic settlement and durable
outbox implemented. Independent launcher-exit/restart acceptance passed. Real Hermes
execution passed in separate systemd user cgroup. Production unit PREPARED, not installed.
Remaining: cooperative soft-deadline checkpoint, capability-backed real coding
acceptance, actual Telegram delivery adapter and separate production/E2E acceptance.
See QUEUE_WORKER.md. Block 8 Google test intentionally excluded from this commit.


## BLOCK 9 — final core acceptance
Status: PASS (local core only). Atomic soft-boundary policy A/B/C verified; real
registered sandbox mutation passed via AIAgent.run_conversation, independent readback,
receipt, journal checkpoint, DONE and durable outbox. Worker restart repeated neither
mutation nor execution. Current focused suite: 49 PASS. Production worker unit PREPARED;
no production activation, Multipart ingress installation or Telegram E2E performed.
Next separate stage: production worker activation + Multipart integration + user E2E.

## Production activation + multipart Telegram integration
Status: ACTIVE / ready for user's separate live E2E. Independent user worker
installed/enabled; durable_tasks native collector hot-attached before debounce,
Gateway PID unchanged. Authorized delivery smoke DONE -> DELIVERED (message 621),
restart produced no repeat. Local begin/cancel/incomplete collection no-dispatch and
persistence verified; historic tasks/outboxes/tombstones untouched. 52 tests PASS.
Details + rollback: PRODUCTION_ACTIVATION.md. Actual final multipart E2E NOT RUN.

## Live E2E recovery — checkpoint boundary
PASS after explicit saved-receipt normalization and authoritative readback audit.
Original live multipart/task/execution retained; no second model execution. Task
DONE, final outbox DELIVERED (Telegram 646). Unknown schemas isolate a task instead
of crashing worker. /task status links transferred collections. See RECEIPT_SCHEMA.md.
