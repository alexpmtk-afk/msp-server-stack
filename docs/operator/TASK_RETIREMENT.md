# Manual historical-task retirement

Related: #41. Code-only change; no deployment or live retirement replay.

## Provenance and audit

This replaces a local one-off helper used for historical cleanup. That helper
held per-task locks and used one SQLite transaction, but did not fence the
Worker lifetime, accepted an externally supplied history file without checking
all history rows, opened the database read-write even for inspection, and used
removed active rows plus existing queue tombstones. Queue admission/claim were
fenced, but a stale direct `Journal.save()` could recreate a removed task.
Do not replay historical cleanup or publish its database/archive.

The reusable implementation generates its own backup and history under a write
fence. It retains active-table records as `ARCHIVED`, stores exact original
TEXT in `archived_tasks`, removes only the explicitly selected queue entries,
and preserves all events, operations, execution records and outbox rows.
Journal save/turn and queue transitions now reject tombstoned or archived IDs.
Legacy removed rows remain fenced; no import/re-admission is necessary.

## Contract

- Only explicitly selected, idle `BLOCKED` tasks with no executions,
  operations, outbox, lease, multipart links or external task references.
- Dependencies are conservatively detected by task-ID references in other
  task documents and multipart documents; blocks within a task stay intact.
- Default inspection uses SQLite `mode=ro` and `query_only=ON`, makes no files,
  invokes no model/API and performs no migrations.
- Applying requires the existing Worker to be stopped by its authorized owner.
  The tool **does not stop/start services**. Its existing lifetime lock and
  selected task locks must be obtainable. Never kill or bypass a lock owner.
- Apply uses `BEGIN IMMEDIATE`, repeats all checks under the write fence,
  writes an online SQLite backup and selected exact history, verifies integrity
  and hashes, fsyncs files/directories, then retires the entire batch in one
  `synchronous=FULL` transaction.
- Archive directory must be new, private, local and outside GitHub. Backup
  includes the whole journal and can contain private data. Do not publish it.
- Four safeguards against replay: terminal `ARCHIVED` state, retained originals,
  permanent `retry_allowed=0` tombstones, and Journal/queue admission guards.
- Already retired batches return `ALREADY_ARCHIVED` without writes. Mixed,
  inconsistent, unknown or quarantined batches fail closed.
- A write error or pre-commit process crash rolls SQLite back. A completed
  backup may remain: retain it as evidence; use a new archive destination for
  an explicitly authorized retry. Never overwrite a newer live journal with
  an old snapshot. An error after commit requires readback, not blind retry.

## Invocation after separate deployment approval

Use the installed, reviewed checkout in an isolated interpreter with its path
explicitly inserted, or the canonical launcher environment. Example variables
below are placeholders; never put live task data into repository examples.

```python
import sys
sys.path.insert(0, CHECKOUT_PATH)
from apps.operator_layer.task_retirement import main
main(['--root', JOURNAL_DIRECTORY,
      '--task-id', TASK_UUID,
      '--archive-dir', NEW_PRIVATE_ARCHIVE_DIRECTORY])  # read-only
# Only after explicit retirement approval and confirmed stopped Worker:
# append '--apply' to the same explicit arguments.
```

CLI stdout contains only status and count. It never prints task bodies or
configuration. No bulk selection, timer, automatic cleanup or restoration API.
Deploy the Journal/queue guards **together** with the tool after separate review;
no running services or production data are changed by this PR.

## Tests and limits

Use synthetic databases only. Tests cover queue and journal-only retirement,
read-only preflight, preserved DONE/outbox/history, tombstone admission,
direct Journal resume/save, Worker reconciliation without a model call,
unknown IDs, active locks, archive I/O failure, SQLite failure and hard process
exit midway through the transaction, followed by safe recovery.

Filesystem tampering or raw SQL writes by an equally privileged owner are not
prevented by application-level fences. Keep journal/archives private. Tasks
with execution/operation evidence or multipart linkage need a separately
reviewed reconciliation workflow; this tool deliberately refuses them.
