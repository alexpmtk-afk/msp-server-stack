# Durable task orchestration — mandatory Block 12

Implemented local journal API: apps/operator_layer/tasks.py. SQLite FULL transactions, event snapshots, restricted permissions, process-held kernel lock, explicit lease metadata, recoverable unknown mutations, stable request IDs, acceptance-gated DONE and transactional final-result outbox. No shell execution or runtime/thread takeover interface.

`Journal.create(origin, goal, plan)` creates UUID. `Journal.turn(task_id, writer, started=actual_turn_start)` yields compact context and holds lock for full execution. The process may call checkpoint, begin_operation, reconcile and complete. Reopening the journal discovers unfinished tasks independently of any Codex thread. OS process death releases lock; a subsequent holder records interrupted worker state. A deadline does not authorize stealing a live writer lock.

Budget: 600s hard constraint, 480s soft deadline; one major block per turn. Operation launch requires estimated duration to fit soft budget. Budget is cooperative; Gateway hard cancellation remains authoritative. New process/turn must not get arbitrary new runtime flags from journal data.

Recovery sequence: discover task → acquire writer → inspect compact context and pending operations → read-only git/provider/service verification → reconcile unknown effects → checkpoint recovery → resume first incomplete block. Readback evidence must come from authorized adapters, not a model's inference. No automatic command replay.

Local acceptance: three blocks in separate Python worker processes; forced exit after a real Git commit; new worker reconciles exact Git HEAD; stable request returns execute=false and no second commit; lock contention; completed task rejects resume; all acceptance booleans required; one durable final result. These are NOT three live Codex turns and NOT an actual Gateway restart test.

Remaining acceptance BLOCKED: scoped machine dispatch (Block 9), real new Codex-thread/Gateway restart, scoped origin-session writer, broker request-ID integration for PR/deploy/backup/install, and read-back-confirmed Telegram delivery. No production/runtime files, services or users changed by this block. Final overall Operator PASS remains forbidden.

Owner action: none needed for local journal. Installation/Gateway integration follows the reviewed Block 9 implementation; no invented admin command is supplied before that installer exists.
