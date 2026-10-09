# Production activation — 2026-10-07

Baseline saved privately under ~/.hermes/operator-tasks/activation-backup:
config snapshot, SQLite online backups of session + journal, baseline.json.
Gateway 474156 (2026-10-06 13:52:16 UTC), dashboard 748, runner 740.
One legacy BLOCKED task, five nonretryable tombstones, empty queue/executions,
two historical pending outboxes. No historic task/outbox was admitted or sent.

## Active deployment

User service hermes-durable-worker enabled/active, independent user systemd cgroup,
hermes identity, Linger=yes, config/journal fixed under ~/.hermes/operator-tasks.
Exact scope: default / 639699477 / telegram:639699477 /
agent:main:telegram:dm:639699477. Sandbox mutation disabled. Other private users,
groups, channel and discussion updates are outside this plugin scope and retain
all original routing/auth. No root/sudo/capability grants were added.

Native durable_tasks plugin hot-enabled through `hermes plugins enable`.
PTB handler group -96 consumes authorized multipart BEFORE old commands/debounce.
Gateway's own callback readback recorded attached PID=474156. No restart required.
Ordinary text returns without consumption; existing debounce code unmodified.
Commands /task begin|end|status|cancel and numbered markers use durable collection.
COLLECTING never submits a durable task. Complete assembly deterministically creates
one task. Queue execution is never spawned by the handler.

Registered Hermes tool-loop api_mode=codex_responses explicitly selected for queue
executions (global model/runtime config unchanged). This limits tasks to registered
operations, unlike native Codex shell tools. Production readonly plan is schema
validated. Unregistered mutations fail closed as capability gaps, not arbitrary shell.
Source input supplied to subsequent turns as well as planning. Model final output
must contain structured evidence.answer for user-facing delivery.

Outbox delivery admits only DONE queue rows in exact scope. Historic report rows
without queue membership are excluded. Before network call: DELIVERY_UNKNOWN.
Telegram send ACK (origin + message_id) -> DELIVERED. Unknown send is never resent
without external evidence/reconciliation; absence of Bot API readback is a blocker,
not permission to retry. Delivery errors never rerun task business execution.

## Smoke evidence

Production begin/cancel and incomplete numbered 1/3 were synthetic LOCAL ingress
calls, not Telegram impersonation or final multipart E2E. Queue/executions stayed
zero. Incomplete collection survived worker restart and was then cancelled.
Native-handler fixture verified authorized ordinary text passes through, multipart
consumes before debounce, unauthorized input is not intercepted. Actual main chat
session/history persisted; routing/security/model config sections unchanged.

Explicit authorized delivery smoke task 8d2930f1-b4d6-4443-8faf-726ee6285101:
DONE, one VERIFIED execution, one DELIVERED outbox; Telegram ACK message 621 in
639699477. Worker restarted after delivery: execution count=1, same ACK, no resend.
Worker current PID observed 553337. Main session retained 1682 messages at snapshot
check. Tombstones=5, retry_allowed=0. No open collections. Tests: 52 PASS.
Journal credential-pattern scan returned no matches (not a guarantee about unrelated
historical logs). No credentials in unit/config/new journal payloads.

No live ordinary inbound has been fabricated after activation; ordinary routing
acceptance is native-handler/debounce harness plus preserved live chat session.
The user's genuine three-message multipart E2E is deliberately still pending.

## Rollback

1. `hermes plugins disable durable_tasks` (native callback hot-removal/readback).
2. `systemctl --user disable --now hermes-durable-worker.service`.
3. Preserve journal/collections/outbox/tombstones; never restore a stale database
   over newer receipts or retry unknown executions/deliveries.
4. If hot-removal fails, arrange controlled Gateway restart separately. No current
   Gateway restart is required or performed.

Next: user sends live TASK 1/3, TASK 2/3, TASK 3/3 END with pauses. Do not synthesize
that final E2E or announce it passed from these smoke tests.
