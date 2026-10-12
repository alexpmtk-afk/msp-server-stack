# Block 9 independent core

Status: PASS for Block 9 core local acceptance. Production not installed; Telegram integration is a separate stage.

Migration is additive/idempotent. `tasks.body` remains canonical for compatibility;
`durable_tasks`, `queue`, `executions` expose named schema fields. TaskQueue applies
migration before admission. Tombstones permanently prohibit admission of five
historic probes. No absent thread IDs or timestamps are fabricated.

`worker_service` runs a scoped polling loop under an independent systemd user
service. Each bounded execution obtains task + origin flock, owner, UUID fencing
token, incrementing generation, 90-second lease and 20-second heartbeat. Kernel
lock, not wall-clock expiry alone, prevents eviction of a live writer. Dead writers
with no execution return to queue; unknown executions become INTERRUPTED with
RECONCILIATION_REQUIRED. Startup readback uses durable receipts, otherwise BLOCKED.
Never retry an unknown operation. Settlement, journal/checkpoint, execution VERIFIED
and outbox insertion are one transaction. Runtime receipts are a preceding durable
transaction and survive settlement failure. Receipt absence is not proof of no mutation.

One block per execution. Soft=480, hard=600 seconds; task lifetime is unbounded.
Atomic boundary policy: CHECKPOINT BEFORE OPERATION -> OPERATION -> RECEIPT / READBACK
-> CHECKPOINT AFTER OPERATION. Budget guard checks a fixed registered estimate before
admission; exhausted budget produces checkpoint + WAITING_NEXT_TURN. An operation
already admitted is allowed to finish after soft boundary, up to the hard limit.
There is no soft-deadline process kill and no sleep-based budget control. Unknown
hard interruption becomes RECONCILIATION_REQUIRED; readback precedes continuation.
Tests use injected clocks and actual process crashes; no ten-minute live timeout test.

Hermes bootstrap + AIAgent.run_conversation is the only runtime entry. Registered
sandbox operations use the supported `api_mode=codex_responses` Hermes tool loop,
not Codex CLI and not global Gateway/runtime configuration changes. Only the narrow
operator_sandbox_marker tool can mutate its isolated target. Tool search/describe is
read-only. No arbitrary commands/paths/SQL are exposed. Parent verifier independently
reads target SQLite, not model assertions. Unregistered mutation blocks fail closed.
Fresh sessions continue the same task from structured journal; thread identity is not
task identity. Real production actions require their own registered capability adapters.

Outbox is inserted once per task and holds final structured result. Local admission
marks DELIVERY_UNKNOWN before sending. Unknown send cannot be resent without
readback; this avoids duplicates but may require manual reconciliation. Telegram
transport adapter is intentionally absent. No exactly-once Telegram claim.

## Supervisor preparation

User systemd manager and Linger=yes were verified. No administrator is needed for
this user service. `deploy/operator/hermes-durable-worker.service` is prepared and
systemd-analyze verified, NOT installed/enabled. Requires reviewed, mode-600
`~/.hermes/operator-tasks/worker-config.json` with root, exact scope
[profile, owner, origin_chat, session_key], poll. Never use fixture-owner scope for
production. The worker has no Telegram poller or gateway restart dependency.
Run isolated acceptance using a transient systemd user unit, not a background child
as production solution. Production enablement waits for remaining acceptance gaps.

## Verified evidence 2026-10-07

Separate enqueue launcher exited; independent worker completed three fixture steps,
remained alive, restart did not repeat DONE. Real independent systemd proof:
task ccebb160-d83c-4fba-914f-fabe7097b3ee, execution
7404e6356e1064d7e28fe40dbabbae22e7ab13e7d99be9063df4851ab4a1c4f3,
thread 01a11512-0f8d-7342-820d-93caa3ac81d4,
turn 01a11512-1023-7ca1-ad63-629894c965cc. DONE + VERIFIED receipt + PENDING outbox
read back independently. Transient unit stopped after evidence. Gateway untouched.

## Final registered mutation acceptance

2026-10-07: task f85fd237-339b-415e-9f0b-ab853afb9817, execution
1309b5de2e496872e25e45e3b37ab7cda90130acc8028dd7d933bc37bb22c014.
Hermes runtime transcript contains operator_sandbox_marker tool call with execute=true;
independent target readback found exactly one marker. Journal has before-operation and
after-readback checkpoints, execution VERIFIED, task DONE, one PENDING outbox.
A new independently supervised worker startup left counts unchanged: one mutation,
one execution, one outbox. Both isolated transient units stopped after acceptance.
Core tests: 49 PASS (6 boundary, 19 lifecycle/queue/executor, 6 journal, 18 multipart).
Permanent user unit remains PREPARED; no production worker or Telegram deployment.
