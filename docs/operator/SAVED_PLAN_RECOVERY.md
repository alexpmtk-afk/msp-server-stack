# Saved planning receipt recovery — offline-only candidate

This runbook describes the **candidate** recovery path for an already blocked multipart planning execution. It is **not** an authorization to repair production, restart a service, replay a model call or deliver a Telegram message.

## Scope and prerequisites

- The exact task ID, execution/request ID and original SHA256 of the **SQLite `runtime_receipts.body` TEXT bytes encoded as UTF-8** must come from trusted read-only diagnostics. Do **not** reserialize the JSON before hashing.
- The journal must show one planning execution (block `-1`) in `UNKNOWN` with `error=plan_required`, `reconciliation=BLOCKED_SCHEMA_MISMATCH`, the queue and task `BLOCKED`, and the saved receipt intact.
- Multipart source parts, assembled input SHA256, exact originating scope and the accepted read-only plan must match. The plan must contain no `allowed_mutations`.
- A pinned code revision and verified online SQLite backup/rollback strategy are required **before any write**. Never overwrite the newer journal from an old snapshot.
- Production DevExec writes remain disabled. Gateway is unchanged. A separately approved, controlled **durable Worker stop** is required for applying the plan: the procedure refuses to write while the existing `worker-service.lock` is busy.

## Procedure design

- `python -m apps.operator_layer.saved_plan_recovery --config <CONFIG> --task-id <TASK_UUID> --execution-id <EXECUTION_SHA256> --receipt-sha256 <ORIGINAL_BODY_SHA256>` performs **read-only SQLite inspection** and outputs only validation metadata. Prefer `PYTHONDONTWRITEBYTECODE=1` and an isolated pinned checkout.
- Adding `--apply` performs only an **explicitly approved** offline reconciliation. It first obtains the pre-existing exclusive Worker lifetime lock, then rechecks all immutable inputs before opening the journal for writes.
- The execution adapter deliberately has no model execution implementation. It reads only the saved runtime receipt, applies strict normalization, the existing independent verifier, and the original `Worker.reconcile` settlement path.
- Expected postcondition: the **same** planning execution is `VERIFIED`, the task is `WAITING_NEXT_TURN`, `requires_decomposition=false`, and no implementation block has been executed or marked complete. No Telegram outbox entry is created.
- Missing or invalid proof, changed source text, wrong hashes, active Worker, an unexpected execution count, a scope mismatch or unsupported plan must **fail closed**. Do not call a model, invent a new execution ID, forge evidence or rerun unknown operations.

## Acceptance and deployment boundary

The isolated GitHub CI suite tests read-only preflight, wrong IDs/hashes, changed source input, active-worker lock, and one original-receipt-only offline reconcile. These tests are **not** live REMOTE acceptance.

Before enabling on REMOTE: separately confirm source/version pin, actual service unit/scope/owner, safe backup, no active tasks, stable Gateway handler, authorized stop/start of only the worker, journal consistency and after-restart integrity. Independently read back the preserved original receipt and resulting task state before allowing any new block. Avoid automatic model invocation in the recovery operation itself.

Do not automatically replay Telegram delivery. The original owner control task remains **BLOCKED** until a separately approved, recorded production reconciliation.
