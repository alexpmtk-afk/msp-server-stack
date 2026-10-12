# Receipt/checkpoint reconciliation contract

Root cause: top-level model `updates` passed directly to Turn.checkpoint. Checkpoint
FIELDS accepts current_branch, last_commit, tests_status, owner_action_required,
last_error, production_state, next_action. Real planning receipt contained instead:
mutations_performed=false, plan_approval=Pending, planning_only=true,
source_instructions_executed=false, test_result=Not determined. Model annotations
are not task authority or proof of acceptance.

Explicit v0 -> canonical v1 normalizer: only kind=plan may migrate those five known
legacy annotations into evidence.planning_metadata. Canonical updates contains only
checkpoint FIELDS; values are string/null except production_state=dict. All raw
fields remain in immutable runtime_receipts and receipt_normalizations.raw_body,
SHA256 identifies the original. No silent field loss, unknown fields or versions
are allowed. v1 model must place annotations in evidence, not updates. Last checkpoint
now has schema_version=1. Normalization failures preserve raw evidence, set task
BLOCKED + BLOCKED_SCHEMA_MISMATCH and execution reconciliation/error. No automatic
retry of blocked tasks. Deterministic settlement errors cannot crash worker.

Recovered live task ec35a698-de8a-5681-b10c-0a8ffd4edfa6 from saved execution
2483c9cb5384e7a94b1b49cf7cd984bdc3fc86df19b17a91cd261f93ea7de1c5.
Planning receipt reconciled, then explicit registered readback finalizer satisfied
both readonly audit/report blocks using actual multipart/task/execution records.
Model execute method was disabled during reconciliation. No new task/input/model
execution. Raw planning receipt unchanged. One task, one execution; checkpoint and
outbox recorded DONE. Telegram delivered final result: message 646. This is recovery
of the original live E2E, not a synthetic repeat.

/task status now links latest DISPATCHED collection to task, worker, execution,
last checkpoint/activity and outbox. Native handler activation requires live verification; a reload acknowledgement
alone does not prove replacement of an already registered callback. Worker PID 556015, restart counter held at 51 across verification.
Normal bad-task + process-restart regression tests demonstrate isolation and no
repeated execution. Production database snapshot preserved before reconciliation.
