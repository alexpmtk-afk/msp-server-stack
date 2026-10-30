# Reviewing financial-report archives without production side effects

## 1. Pin scope and revisions

Read repository instructions, the shared-workflow contract, project decisions and the complete handoff in chronological order. Give late corrections precedence over historical status. Pin the feature head and legacy controller revision in an isolated checkout; never switch or reset a dirty production checkout. If the remote head changes during review, inspect its diff: incorporate documentation-only updates without discarding another author's log; rerun affected checks if code changed.

Record independently: source revision, published revision, installed revision, manual provider trials and actual scheduled execution. Do not infer one from another.

## 2. Inventory the runtime without secrets

Check the actual hostname, execution identity, archive-root existence, directory metadata and disk space. For queue discovery, use bounded read-only observations: TCP connectivity, listeners, named system/user units, binaries and the existence of configuration fields. A closed default TCP port says nothing conclusive about remote Redis, another port, a socket or an inaccessible container.

Do not print credentials, environment values or process arguments that may contain secrets. A permission-denied credential path is NOT VERIFIED, not absent; retain the owner's earlier credential validation as attributed historical evidence. Never weaken root-only directory permissions to finish an audit.

## 3. Compare quotas end to end

1. Compare controller implementation and Lua formats at pinned revisions.
2. Compare normalized quota-owner identity: seller-derived hash rather than rotating WB token; Client-Id rather than Ozon Api-Key. Use synthetic identities to test token rotation and isolation across sellers.
3. Compute the actual rule keys on both sides. Check endpoint host, scope/group, rate string, prefix, Redis endpoint/database and overrides. Matching controller code or Redis host does not establish a shared quota: a scope or rate-string difference changes hashed bucket identity.
4. Verify that every page and retry reserves the same shared rules and stores provider cooldown in them. Keep extra safety buckets additive to the canonical shared bucket; do not substitute a private bucket. Trace cooldown selection separately from admission: a controller may choose specific buckets instead of the global bucket when both are passed. Capture the actual deferred keys with a fake backend for each method and a long Retry-After. For a shared-owner throttle, prove the canonical global bucket is deferred as well as any private safety bucket, because older clients cannot observe a newly introduced private key.
5. Compare local pacing with shared intervals. If local pacing is shorter and reservation is nonblocking, a healthy second page can be rejected. Use structured retry-at scheduling plus a durable checkpoint, not fast retries or weakened limits.
6. Separate missing-approval tests, unavailable-backend tests and real multiprocess Lua tests. A mocked gate rejection is not a backend failure/concurrency test. Use an isolated disposable backend only when authorized; never mutate the production queue to test it.
7. Validate long Retry-After values without silently shortening provider waits; preserve uncertainty about method-specific quotas rather than inventing limits. Keep unverified provider methods blocked.

## 4. Run synthetic fault probes with networking denied

Run the existing suite first. Build additional reproductions outside production data, using synthetic rows and deny-by-default socket connections. Save a small result matrix and exact affected functions. Test the following behaviors independently:

| Probe | Required property |
|---|---|
| Repeat an already verified document | Avoid provider calls unless a documented revision/refresh reason requires them; CSV idempotency alone is insufficient |
| Fail after a successful page | Resume from the last durably committed cursor, not zero; fsync page bytes before atomically advancing the checkpoint |
| Reject a busy quota slot | Retain progress and retry timing without an unbounded loop or immediate repeat |
| Large/many pages | Bound cumulative memory and staging size, not only response bytes; account for decoded JSON, duplicate sets, raw JSON copies and annual rebuilds |
| Change an existing row | Preserve old and new document revisions with provenance, not silent overwrite or permanent rejection of legitimate corrections |
| Remove a provider row | Rebuild the selected document version rather than retaining every historical row in an eternal union |
| Corrupt old CSV, then import a valid unrelated row | Reject the previous checksum mismatch before merge; never recalculate a fresh manifest over corrupted retained values |
| Crash between CSV and manifest writes | Preserve or recover a committed generation; atomic single-file replacement is not a multi-file transaction |
| Crash between monthly/annual or CURRENT datasets | Readers see a coherent committed snapshot, with recovery tested at each publication boundary |
| Delete one/all monthly sources but retain annual output | Fail bidirectional inventory reconciliation; inspecting only existing files cannot prove nothing is missing |
| Return a legitimate empty report | Record explicit provider-proven empty coverage, distinct from missing or malformed data |
| Import through an offline path | Enforce the same dataset/type/period identity checks as HTTP ingestion and verify |

### Checkpoint and staging acceptance recipe

1. Enumerate publication boundaries: temporary page write, page rename, page-directory sync, cursor-state rename, and terminal-state rename. Run an actual killed subprocess at those boundaries as well as injected sync failures; a callback after successful fsync does not exercise the preceding rename-to-sync window. Repeat for each report type.
2. Verify pending-page integrity before advancing a cursor. Save a digest with the page before cursor acknowledgement, then mutate only a financial value while preserving identifiers after a simulated crash. Replay must reject without rewriting state or blessing the changed bytes with a freshly calculated digest. Independently test whitespace/noncanonical JSON: the state hash must describe the actual stored bytes, not an unstored canonical serialization.
3. Reconcile HTTP, serialized-page and staging-reader size limits before writing. Use a scaled-down cap to reproduce the same boundary cheaply; assert an oversized payload cannot leave a permanent unreadable pending file. Distinguish a scaled algorithm test from a full-size production load test.
4. Inject file and directory fsync errors separately and retry. A failed temporary-file sync before rename may require fetching again; a durably saved page must be reused. Preserve page bytes and the last proven cursor across quota, transport and storage errors.
5. Review worker integration explicitly: sync versus async sender contract, one authoritative cursor, structured retry-not-before, terminal response semantics, and the writer/coverage acknowledgement. Finish consuming any lock-holding page reader into local staging before entering a writer that takes the same lock, because nested acquisition can deadlock. A completed download stage is not a published archive or committed coverage record.

Before accepting an integrity fix, replay the identical original reproducer on the pinned before/after modules. Then test every dataset with corrupt CSV, corrupt/missing manifest fields, malformed manifest shapes, either orphaned pair member and byte-identical incoming data; compare the entire business-file/backup snapshot after rejection, not merely whether an exception occurred. Deny socket connections in the harness and retain its reproducible stdout.

Trace every dependency consumed by a derived publication. Validate all earlier monthly sources with the same full validator used for the target: schema, dataset, cabinet, expected period, status, bytes, row count and SHA. Derive expected identity from the trusted path/registry, not the manifest being checked. Corrupt an untouched prior month's metadata and import a different month to expose validators that protect only the immediate destination. Run whole-group preflight under the writer lock before the first write or backup; an exception after changing a monthly file is not an unchanged-state rejection.

Inject failure after CSV replacement but before manifest replacement, then retry through the real importer. A new fail-closed check may correctly prevent recertification while making the publisher's own interrupted output unretryable. Preserve the check and require explicit recovery to a proven pair or committed generation; never restore apparent health by deleting metadata or recalculating checksums. Distinguish this recovery gap from the original corruption defect, and distinguish the original reproducer passing from acceptance of the full patch.

Validate immutable generations or a commit journal plus atomic current pointer; test actual restoration, not just the presence of backup files. Keep independent expected inventory: discovered document IDs/types/fragments, periods, cursors, terminal provider response, row counts, hashes and revision provenance. Local integrity is not provider completeness.

## 5. Inspect credential and transport boundaries

Review fixed-host allowlists, redirect refusal, bounded responses, secret-free exceptions and no network on import. Review credentials with descriptor-based O_NOFOLLOW open, fstat, a trusted parent/owner/mode check, bounded reading and structural validation. A protected real parent can make a reader race unexploitable there, but it does not validate the same reader under a future writable-parent deployment. Do not overstate a synthetic unsafe-parent test as evidence of actual compromise.

## 6. Report and publish only the authorized review

Begin in plain Russian with the practical verdict. Use the user's requested sections and PASS/FAIL/NOT VERIFIED; list each blocking finding with file/function, demonstrated mechanism and smallest fix. Give one priority next action. Count scenarios programmatically by category; separate positive checks from defect reproductions rather than reporting every executed scenario as PASS. Distinguish official method existence/version evidence from a complete request/response contract and a verified special quota; a conservative local interval is not a provider limit. Keep code review, offline tests, deployed queue tests and live provider tests separate. Do not call uncompleted provider/schema research verified.

Publish the review and an appended handoff entry in the reviewer's own branch/PR, preserving the author's branch and prior log. Re-read exact remote files, SHA, base/head and open/unmerged state. Preserve concurrent log additions. Check both test execution and workflow path triggers: a test present in the discovery wildcard can still be absent from the workflow trigger list. Report CI only for its observed revision.


## One-pass collaboration and complete offline wiring proof

For this archive, consolidate related fixes into one pinned review; do not rerun unchanged historical matrices solely to increase counts. Separate scoped patch acceptance from live readiness. Exercise the actual SharedQuota.cooldown wrapper, not only inherited defer, with a fake backend and real environment unchanged. For pending-page recovery, verify persisted payload digest before cursor ack and raw-byte state hash after replay, including innocuous whitespace and financial-value mutation. Test oversize rejection before write and successful later bounded retry. A standalone vertical slice may join real page staging/streamed CSV/pinned generation/coverage receipt with fake provider/queue: label it offline proof, never installed worker or provider completeness. Record actual module placement before proposing cross-repository wiring; code on an old host does not write the new VPS merely because paths look alike. Keep one job scheduler and one cursor, close locked page iterators before entering a publisher lock, and propagate structured not-before. Project knowledge updates are not application deployment.
