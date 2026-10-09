# Mandatory Block 13 — Multipart Task Collector

## State and deployment
Local implementation only. Overall PARTIAL until real Telegram E2E.
Production Telegram adapter, Gateway, configuration, services and routing are unchanged.

## Protocol
Numbered first line: `TASK 1/3`, `TASK 2/3`, `TASK 3/3 END` with payload on following lines. Inline `TASK 1/3 — marker ALPHA` is also accepted. END is recognized only in the header and only on N/N. All numbers 1..N and final END are required. Out-of-order after first part is accepted and sorted numerically. A first part other than 1 is rejected, consumed, never sent to the agent. Same content under the same number is harmless; different content makes ERROR. A final header may later add END to the same unchanged N/N payload.

Manual: `/task begin`; subsequent ordinary texts are parts; `/task end` completes nonempty input. `/task status` reports progress; `/task cancel` closes an unsubmitted collection. Other `/task` controls and malformed numbered headers are consumed with an error rather than executed. One open collection per authenticated (profile, owner, origin chat, routing session). Numbered and manual modes cannot be mixed. ASSEMBLED remains open until a scoped dispatcher confirms queue acceptance; a second begin cannot steal it. Ordinary text during a numbered collection is consumed with a finish/cancel notice, not attached as an unnumbered part.

Default expiry policy: keep waiting; no automatic timeout dispatch. Explicit expire closes only COLLECTING. ERROR requires cancel. Once submission is UNKNOWN, cancellation/new input are refused until independent readback; a collection must not claim cancellation of work that may already be queued.

## Persistence and integrity
Same private Journal database: directory 0700, DB 0600, SQLite synchronous FULL. Each part retains number, message ID, update ID, receipt time, payload and SHA-256. Receipt fingerprints also cover the complete message/header. Scope comes from authenticated transport, never text.
Limits: 128 parts, 256,000 UTF-8 payload bytes; exceeding limits produces ERROR, never truncation or execution. Raw task input lives in private input tables, NOT in compact Journal goal/history snapshots or logs. Users must not submit secrets; transport/journal contents are not an authorization or policy source. No raw texts are returned in status.

COLLECTING → COMPLETE → ASSEMBLED → DISPATCHED. Alternate terminal paths CANCELLED / EXPIRED / ERROR. COMPLETE is persisted before assembly. A single IMMEDIATE transaction creates the deterministic UUID Durable Task, hash binding and pending dispatch record and transitions to ASSEMBLED. Crash before commit rolls everything back; recovery retries COMPLETE only. Unique scope/receipt/dispatch keys serialize independent processes. Assembled input is joined with exactly two newlines in part-number order and hash-checked whenever retrieved.

## Execution integration
`Ingress.receive` intercepts BEFORE automatic debounce, slash dispatch, busy-session routing and Codex. consumed=true means no fall-through even on disk errors. An authorized scope is mandatory. COMPLETE is automatically assembled locally. The ingress never invokes Codex.

The linked task has input_reference and requires_decomposition=true, starting PLANNING. Journal context carries reference, not a huge prompt. Read `Collector.input_for(task_id)` only in a scoped execution adapter. One planning turn sets a validated bounded execution plan with the input hash; `set_execution_plan` checkpoints and closes that turn. It cannot falsely finish the whole task merely by approving a plan. Subsequent turns execute one block each.

`prepare_dispatch` changes PENDING to UNKNOWN BEFORE transport and returns a fixed `submit_operator_task` spec, stable request ID, immutable routing and input hash. Sender must use a registered dispatcher with origin-session single-writer rules. `confirm_dispatch` requires independently read-back queue acceptance for exact task/request IDs. UNKNOWN cannot be retried until readback. A definitely-not-accepted readback returns to PENDING with the same key. Cancellation and pre-submit conflicts block/cancel the linked task and remove pending submission.

## Required production seam (not installed)
1. Add an owner-scoped collector provider at adapter startup, backed by the default profile private Journal.
2. In Telegram `_handle_text_message` and `_handle_command`, after existing authentication and route canonicalization but before `_enqueue_text_event`/`handle_message`, call Ingress with original unbatched text/message/update IDs and canonical scope.
3. For consumed events, acknowledge ingress durability and return a short status through normal transport. Never send individual parts to Gateway busy queue or Codex.
4. Drain pending assembled tasks through the reviewed Block 9 scoped durable dispatcher. Pass assembled input once after hash verification; retain origin/session/task IDs. Startup discovery recovers COMPLETE and pending submissions, never executes incomplete collections.
5. Leave existing debounce code untouched for consumed=false.

CAPABILITY GAP: hermes.task_dispatch — no installed scoped queue/worker yet. Production rollout is withheld for this dependency, not for missing local permissions. Enabling collection alone would misleadingly imply completed tasks execute. A direct Codex call or ordinary Gateway message replay is not an acceptable substitute.

## Local acceptance and remaining live acceptance
Tests cover both modes, missing/out-of-order/duplicate/conflicting parts, repeated updates/end, cancel, expiry, 10.1-second REAL pause, restart between parts, process kill inside task-creation transaction, concurrent recovery, exactly-one task, UNKNOWN dispatch readback, input decomposition and three checkpointed turns. An isolated harness executes the installed adapter's actual batching method unchanged: multipart never enters it, ordinary close messages still merge.

These are local Python processes/turn contexts, NOT actual Codex threads or a restarted Gateway. No actual Codex launch is asserted by a test spy. Real Telegram E2E remains pending: three real message IDs and timestamps, one multipart ID, no agent execution before final END, exact ALPHA/BRAVO/CHARLIE hashes, one durable ID, exact assembled Codex turn input, queue receipt, origin result.

After the dispatcher/transport seam is installed and readback verified, request the user's three markers with deliberate pauses. Do not run their semantic content or fabricate thread/turn evidence. No live test has been started.
