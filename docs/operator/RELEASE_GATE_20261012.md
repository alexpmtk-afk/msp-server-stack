# Hermes Operator release gate — 2026-10-12

**STATUS: NOT DEPLOYED / RUNTIME UPDATE BLOCKED.**

This is a frozen handoff for the owner's authorized scoped update of the existing Hermes Gateway and the existing `hermes-durable-worker.service`. The chat-accessible GitHub bridge has a read-only whitelist and does **not** provide an approved end-to-end service deployment operation. An attempted new executable deployment workflow was denied by the connected tool security gate; it was **not created or executed**. Do not work around that denial using unrelated service commands or broadened permissions.

## Pinned source and acceptance

Canonical draft PR: https://github.com/alexpmtk-afk/msp-server-stack/pull/32

Pinned source revision: `6bff5db9fd36c76e5367818dd4cf07aeb927ebae` (last code candidate; any later documentation-only commits do not change release binaries).

The enlarged portable test suite at code commit `6bff5db9fd36c76e5367818dd4cf07aeb927ebae` passed **143/143**; GitHub Actions workflow run `38244155592`. Secret Scan run `38244155623` PASS. Tests reject saved-plan recovery while unrelated tasks/collections are active and prohibit silently verifying UNKNOWN execution from progress counters or decomposition flags.

All digests below are **Git blob SHA-1**, not SHA256 of file bytes:

| Existing REMOTE source path relative to `/home/hermes/projects/hermes-operator-layer/` | Expected before | Required new blob |
| --- | --- | --- |
| `apps/operator_layer/tasks.py` | `7ee310e53589e88f9a418e62ee7a3a3a43ff1964` | `dcb3e2d3936ed1308a83ae8a260976d3348f60ab` |
| `apps/operator_layer/queue.py` | `bb092df614e2740726ac27d580b81a89b1eec0dd` | `bfa4fa867a23dd542e3b295a9a174920a8145d79` |
| `apps/operator_layer/worker_service.py` | `f83fb4693df1c4fde0e4a18e08da52867c679065` | `affb0b2376000dcb14c0f3613bbc11b901ae2692` |
| `apps/operator_layer/hermes_executor.py` | `b5192a431d0820a27073bcf9a727542a34a48841` | `125eb824d3031c7a418a40db9ad5dbed31b319f8` |
| `apps/operator_layer/receipt_schema.py` | `b47df48b7ebb69a6b5c66028cd53b1af7e70afca` | `7215986426d1e17f207a1690adc4827b5161745c` |
| `apps/operator_layer/production.py` | `37772af6e9e4e03d336a5cef041f7c27b6e9b235` | `f32b221e289fc06baf74e3a54178fc154464daa4` |
| `apps/operator_layer/saved_plan_recovery.py` | ABSENT | `b5a46c99dfd1f5d50f936f4b118f6aca798b8fc5` |
| `deploy/hermes_plugins/durable_tasks/__init__.py` | `e23fdd87418458895cff6f66f32ad8fce6bcf24a` | `094046d0546a66b7ad657160c0e878ebd1ce3340` |

The installed plugin `/home/hermes/.hermes/plugins/durable_tasks/__init__.py` must be updated with the **same exact new plugin blob**. The unchanged `scripts/operator/worker_entry.py` is the actual systemd user unit entry script and imports `apps.operator_layer.worker_service.main`. Do not provision a new Worker.

## Verified production baseline — read-only

Private bridge issue [#272](https://github.com/alexpmtk-afk/msp-server-bridge/issues/272): Gateway ACTIVE, Worker ACTIVE, `natural_multipart_enabled=true`, `devexec_write_enabled=false`, origin task `e00d1337-0412-59f0-a8c3-3a4a074af0ea` BLOCKED with exactly one original planning execution, no active queue rows, no collecting multipart, two historic unsent outbox rows unchanged, `PRAGMA quick_check=ok`, 45 GB free, REMOTE Git branch `feat/hermes-operator-layer` clean at short HEAD `571eee4`. The unit identity and `worker_entry.py` entry point were confirmed in bridge [#274](https://github.com/alexpmtk-afk/msp-server-bridge/issues/274). These results are a timestamped baseline, not a standing guarantee: **repeat preflight immediately before any write**.

The original task's saved immutable planning receipt was independently accepted under the pinned candidate in READ-ONLY mode via bridge [#271](https://github.com/alexpmtk-afk/msp-server-bridge/issues/271): original request ID derived from exact original execution, single non-mutating plan, matching UTF-8 receipt SHA256 and multipart input hashes. Journal not modified and model not called.

## Authorized rollout boundary (not executed)

Crash recovery must never promote an UNKNOWN execution directly to VERIFIED on the basis of advanced block counters, changed planning flags or DONE markers. A saved receipt and independent verifier are required. This is covered by two additional regression tests (143 total).\n\nA one-task offline reconcile must fail closed when **any other** queue task is active or an incomplete multipart collection exists: the underlying claim path normally invokes shared queue recovery and must not mutate unrelated state. These guards were added in the pinned candidate and verified with tests. Treat owner ingress quiescence as an external rollout prerequisite; a preflight by itself is not a mutex against messages arriving later.

1. Repeat narrow source and queue/service preflight. Abort on any active/unknown task, changed source blobs, config/scope drift, open collection or modified original receipt.
2. Stage only the above exact pinned source blobs. Create a restricted 0700 per-release rollback directory under the existing operator activation backup area; back up exact existing source/plugin/config and use **SQLite online backup** for current journal and runtime databases. Verify backup integrity and preserve timestamps/provenance.
3. Use **only the existing user systemd unit** to stop Worker. Confirm it stopped and its exclusive lifetime flock is available. Do not stop unrelated services.
4. Install only these eight source files and the installed Telegram plugin, atomically; check digests. Run the full **143-test** portable suite in isolated fixtures. On failure, restore only touched files and restart the old Worker; never overwrite a newer live journal with a stale snapshot.
5. A Gateway hot reload alone is insufficient: previous hot reload trials did not replace the callback. Use a separately bounded, owner-approved **single-service Gateway restart**, followed by independent new PID, control socket, native attached handler and source-version readback.
6. Restart the same Worker user unit from its existing `worker_entry.py`. Independently confirm it imports pinned current source and that the original task is **still BLOCKED**, with exactly one planning execution. Commit changed source files to REMOTE branch only after acceptance; preserve unrelated worktrees.
7. **Separately**, after a new stable baseline and explicit stop of Worker, perform `saved_plan_recovery`'s default read-only preflight and, when gates hold, lock-fenced offline `--apply`. It verifies exact task/request/receipt SHA256 and input parts, confirms the original planning execution as VERIFIED, and leaves 0 execution blocks completed and the task WAITING_NEXT_TURN. It must not invoke model, mutate production data outside Task Journal, or deliver Telegram itself.
8. Restart only Worker and observe the actual read-only execution block, independent verdict and Telegram delivery ACK. Do not claim completion until confirmed. No blind retry for unknown executions or uncertain Telegram send outcomes.
9. On activation failure, preserve immutable journals and restore files/config from the verified release backup. If the journal advanced during rollout, **do not replace it with the snapshot**. Leave Worker stopped on unresolved inconsistent state and obtain explicit recovery review.

**Not yet accepted:** live REMOTE pinned installation, Gateway new callback, Worker new version, offline saved-plan application and final Telegram acknowledgement. DevExec production write remains OFF.
