# WB: durable chunk policy, 2026-11-06

## Finding (production evidence, not a size benchmark)

Report 601780521, wb_laser_master, original sealed budget 4. The first two
acknowledged pages contain 1000 rows each. The retained third response contains
846 unique IDs, 506 at/below request cursor 3111431040424; its final ID is
3111430415338. There are no shared IDs with the preceding 1000-row response.
This does not prove no overlap with the first page; protected replay checks all
acknowledged pages using full payload hashes before allowing advancement.

Failure was numerical cursor-order validation, not a demonstrated row-size,
timeout, memory, HTTP 429 or storage limit. No smaller-page comparison has run
against WB. There is no measured failure threshold or empirically optimal chunk
size. Do not claim 500/250 rows or longer sleep cures this observed failure.

Official contract, checked 2026-11-06:
https://dev.wildberries.cn/docs/openapi/documents-and-accounting
POST /api/finance/v1/sales-reports/detailed/{reportId}: limit <= 100000,
one request per minute per seller, continuation from the LAST original source
row rrdId, terminal HTTP 204. The contract does not promise numeric ordering.
The operational host stays finance-api.wildberries.ru; no host/token migration.

## Enforced general rule

- 1000 requested rows per page: conservative operational default, NOT vendor
  maximum and NOT a proven optimum. Keep a 64 MiB serialized-page hard cap.
- Persist original response + checksum before semantic processing. Persist the
  accepted page and fsync before atomically acknowledging its cursor.
- Persist not-before at least 70 seconds after the page step's start; the existing
  shared Redis limiter remains authoritative (including slow transport and other
  finance clients). This is a conservative start-to-start policy, not a claim
  that transport completion is followed by 70 seconds idle. Respect longer quota
  and provider Retry-After deadlines. No arbitrary sleep bypasses shared quotas.
- One existing service portion uses at most 3 new entries and the same original
  cumulative ledger (existing approved ceiling 1000); a checkpoint is not failure.
- Retain original row order and LAST source ID. Lower IDs are allowed. Verify
  full-payload consistency across pages; include new lower IDs, count exact
  identical overlaps once, HOLD conflicting duplicates and foreign report/type.
- The cursor chain must be contiguous and acyclic, not numerically increasing.
  Repeated cursor/self-loop HOLD before acknowledgement. Do not sort, max(),
  guess a cursor, skip rows or clear state to escape a cycle.
- A short page is not completion. Require 204, durable publication and verified
  business values. A saved response replays locally without HTTP/admission cost.
- Corruption, unknown outcome, throttling and generic HOLD are not normal page
  pauses. Do not auto-retry semantic errors or shrink batches after them.
- Completed reports remain excluded; weekly reports crossing New Year are whole.
  Other cabinets and daily scheduling are not activated by this repair.

## One-time migration and acceptance boundary

Only the exact diagnosed four-entry HOLD state c68ac57c... is eligible for the
migration in this release. Verify all-nonce four HTTP200 outcomes, zero unknowns,
original two-page prefix, retained response checksum AND independently pinned
ordered full-row hash profile from the root-owned diagnostic, new validation, conflict
checks and acyclic cursor before arming a durable local-only replay ticket.
The ticket pins response bytes and prefix and remains enforced after interruption;
missing/changed evidence cannot become a new HTTP request. Counter remains 4
until a later, separately admitted transport entry. This is not a general HOLD
bypass or budget reset. Older captured replay evidence remains checked.

Offline evidence: actual ID order from second/third pages with explicitly
SYNTHETIC business values; backward-cursor terminal publication, conflict HOLD,
cycle HOLD without refetch, crash-local replay, 70-second persisted timing,
12345 synthetic rows in 13 chunks + terminal 204. These are not production
report totals or a benchmark of WB response sizes.

Production is still HOLD with 2000 acknowledged rows + 846 retained rows until
this new immutable release is installed and the exact target run is verified.
The new updater pins the currently installed control-2a81ce92... release and
retains rollback of wiring only, never archive/budget/evidence deletion.
