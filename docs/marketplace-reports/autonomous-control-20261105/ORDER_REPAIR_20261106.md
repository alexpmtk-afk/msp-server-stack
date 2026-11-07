# Verified WB out-of-order response: actual fix and bounded continuation

## Established cause

The root read-only profile confirms report601780521/type1, 1000 unique IDs,
zero duplicate IDs, zero rows at/below requested cursor3111429097937, and one
internal order reversal at index970. The last original row is3111431040424,
while the page maximum is3111431399709; 686 received rows exceed the last ID.
The earlier validator incorrectly required ascending order inside each response.
This is NOT an inclusive-cursor duplicate or a proven conflict in financial values.

Official pagination contract: use rrdId from the LAST source row until HTTP204,
not max(rrdId): https://dev.wildberries.cn/docs/openapi/documents-and-accounting
The production endpoint remains finance-api.wildberries.ru; no host/token changes.

## Correction

1. Preserve received order and all original bytes/checksums. Accept unordered
   unique positive IDs above the request cursor; next cursor remains the original
   final row. Do not sort, invent a maximum cursor or skip intervening source data.
2. Preserve raw cross-page overlaps, but count/export exact full-payload matches
   only once. Conflicting values under the same ID HOLD before cursor advance;
   do not silently overwrite financial data. Same-page duplicate IDs still HOLD.
3. Both normal CSV/coverage and administrative read-only receipt paths use the
   same exact-match unique-row interpretation. Raw page hashes remain unchanged.
4. The investigated HOLD has a separate LOCAL replay ticket pinned to its exact
   budget-state digestbf7b..., raw response185b..., and prefixd2ae.... Verify all
   previous nonces, sealed counter and pages before any mutation. Replay itself
   cannot invoke the sender or spend another admission entry: counter stays3.
   Later authorized requests extend that SAME ledger to4,5,etc., through Redis.
5. Add optional --expect-report601780521 / expected_report_id constraint to the
   existing wake/control path. One job only; mismatched report/discovery is
   rejected under the administrative lock before dispatch. No new queue/sender.
6. New diagnostic payload exposes ID-only anomaly metadata for future selected
   responses. It does not grant arbitrary archive, root or credential access.

## Evidence and acceptance boundary

Tests include the exact1000-ID ordering exported by the root profile, with no
financial amounts. Controlled OFFLINE package tests replay saved data at zero
HTTP cost, model subsequent686 identical overlaps, preserve original source
cursor and bytes, publish1002 unique synthetic rows, and keep the cumulative
counter3->5. These are offline fixtures, NOT downloaded production row totals.
Negative cases cover conflicting overlap, changed retained response, unknown
older nonce, missing/corrupt budgets, wrong selected report and read-only receipt.

The installed release remains control-a99c... until root update. The real report
remains HOLD, counter3, first acknowledged page1000rows, plus the retained second
response. No real provider call was made preparing this correction. Do not
report full completion without new runtime terminal204 and verified publication.

## One administrative operation

ROOT_REPAIR_AND_RESUME.txt upgrades only the immutable financial control wiring
from the pinned a99c release, then drops to hermes and admits ONE bounded job
for wb_laser_master/report601780521 through the EXISTING msp-finance-wake.
It may perform up to3 new sender entries after zero-HTTP local replay, respecting
shared Redis/not-before. It cannot select another report, alter A/B/C/tokens,
activate daily scheduling or run another cabinet. It restores network denial
through the existing supervisor cleanup. A second invocation cannot redownload
an already complete target or silently move to another report.

Upgrade-only and wiring-only rollback remain available via UPGRADE_ONE_LINE.txt
and the installed root snapshot's --rollback. Rollback never removes archives,
logs, generations, quota state or budget spent after installation.
