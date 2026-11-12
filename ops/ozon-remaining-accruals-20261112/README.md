# Remaining Ozon accrual history — 12.11.2026

PREPARED_NOT_EXECUTED. Owner corrected the missing legal-entity handoff.
Dmitrieva Jan–Oct is already complete: 304 days, 7524 API records.
This package never downloads or rewrites Dmitrieva.

One fixed root service collects ozon_novokshenov then ozon_laser_master,
Jan–Oct 2026, 20 months / 608 cabinet-days. Each month has at most 128 durable
sender entries, ten pages/day, total 2560. Unknown transport outcomes, 429,
corrupt/conflicting publication or exceeded budget stop with HOLD; no restart
or blind retry. Existing accepted worker, shared Redis and controller lock reused.
Type catalog seed reused exactly; each cabinet gets only its own credentials.
Daily raw responses retained before parsing. Full nested values preserved.

Sequential child verifier checks all source pages/cursors/days/CSV values against
pinned publication before advancing to the next cabinet. Unlike Dmitrieva Jan,
no independent cabinet Excel reconciliation is claimed for these two cabinets.
Root service cleanup authenticates temporary worker controls and removes the
one-unit/start-only Hermes rule. Common run.py runs final read-only verification.
No new timer, model worker, gateway restart, realization import or source write.

Tests: python3 test_remaining.py (network audit denied), also /usr/bin/python3.
Seven tests include 608 synthetic day/source/publication round trips in separate
cabinet processes, online-January allowlist, scope/budget/corruption refusals,
unknown-outcome no-retry, ordered cabinet handoff and early HOLD.
These are isolated tests, not production API acceptance.

Owner command: ROOT_OZON_REMAINING.txt, one physical Bash line in root console.
It copies/verifies a root-owned launcher, then verifies the pinned tar and full
manifest before any installer execution. No credentials or financial raw data
are included. After owner execution read exact public/child receipts and verify
actual service invocation; launcher registration is not successful collection.

Public progress: /var/lib/msp-finance-control/results/ozon-remaining-accruals-2026.json
Child receipts: ozon-novokshenov-accruals-2026-remaining.json and
 ozon-laser-master-accruals-2026-remaining.json under that same results directory.
Current child counters are in its receipt current_period/months; main chain
records verified finished cabinets. No special task-panel code was added.

## Packaging correction —12.11.2026

Initial root activation stopped before installation/provider calls: nested child
MANIFEST.json files were incorrectly excluded by the outer archive builder.
The exclusion now applies only to the outer manifest; 36 files are included.
Added regression against the actual extracted deployment artifact and child
verify_payload (only inode ownership mocked in nonroot test), plus sanitized
child-failure diagnostics that exclude exception text/source lines. Both tests
were observed failing then passing; nine total tests PASS on3.14 and3.12.
Original root snapshot remains intact. Use only the regenerated pinned command.
Production activation remains pending, not verified by local packing tests.
