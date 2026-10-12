---
name: hermes-operator
description: Bounded, recoverable Operator tasks with capability checks and no security bypass.
---
# Operator workflow
Classify first: SMALL only if a single bounded block is confidently sufficient; otherwise DURABLE.
For DURABLE create Journal task before mutations. Plan each block with goal, named boolean acceptance evidence, allowed mutations, expected output, dependencies (zero-based), readback and rollback.
Use apps.operator_layer.tasks.Journal in a private 0700 directory; database is 0600. Never store credentials, raw prompts, provider responses or sensitive logs; only short sanitized identifiers/summaries. The content filter is defense-in-depth, not a secret detector guarantee.
Hold `Journal.turn(task_id, writer)` for the entire turn. Never acquire/release a lock per individual RPC. One major block per turn, even if time remains. Hard limit 600s; soft deadline 480s from actual Gateway turn start, not from late journal creation. If start is unknown, one block only and checkpoint early. Budget.can_start includes an estimated operation duration; reserve final 120 seconds. No sleeps to extend execution.
DISCOVER → PREFLIGHT → READ SOURCE → PLAN → BRANCH → IMPLEMENT → TEST → PUSH → PR → CI → MERGE → DEPLOY → ACCEPTANCE → REPORT.
Required capabilities include hermes.durable_tasks for large tasks; missing runtime integration is CAPABILITY GAP, not permission to bypass it.
On interruption load compact context; read git status/branch/HEAD and relevant service/provider state before checkpoint('recovery', ...). Unknown operations require independent readback; never blindly rerun.
Before mutation call begin_operation with a stable logical operation name. It returns request_id and execute. If execute=false, DO NOT invoke the provider again. Pass request_id to broker. UNKNOWN blocks execution until reconcile with verified readback. NOT_APPLIED permits retry with SAME request ID. This journal cannot make a non-idempotent external provider exactly-once by itself.
Checkpoint after commit/tests, before mutations, after mutations AND readback, and block boundary. Complete only with every named acceptance criterion verified. Completion closes the turn against further blocks.
After each turn report TASK ID, BLOCK N/total (display one-based), BLOCK STATUS, CHECKPOINT, COMMIT, TESTS, STATE CHANGES, NEXT BLOCK, SAFE TO RESUME.
Machine dispatch adapter (not installed yet) must hold task and origin-session locks, enqueue compact next context with stable task/block dispatch key, restrict identity/profile/chat, and drain durable outbox to origin. Never share ownership of a Codex thread. If dispatch unavailable, resume via next user message and the same journal. DONE must reject execution. Final result outbox has one record per task; actual Telegram delivery requires readback/delivery receipt and cannot be inferred from enqueue.

## Explicit multipart input (mandatory Block 13)
Use the authenticated transport Collector before debounce, never model interpretation. TASK X/N or /task begin means input collection, not execution. Do not launch any partial part. Require complete numbering and final END (or /task end), then atomically link assembled input to one Journal task. Keep input reference/hash in compact continuation; retrieve full input only after scoped authorization. Conflicts, missing parts, expiry and storage errors never dispatch. UNKNOWN queue submission requires independent readback, not retry. Default keep-waiting policy, 128 parts/256,000 bytes, no automatic partial timeout. See docs/operator/MULTIPART_TASKS.md for exact protocol and pending production seam. Existing debounce remains ordinary-chat convenience only. Until runtime deployment is verified, do not tell users live Telegram multipart guarantees exist.
