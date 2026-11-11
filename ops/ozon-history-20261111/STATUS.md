# Ozon closed-month realization history — 11 November 2026

## Confirmed result

Dmitrieva January2026 actual API200,151 unique report rows,2026-01-01–2026-01-31.
Hermes independently read exact raw/CSV and matched published root receipt hashes:
response e2373acc17d2dedbbc8dacc8a072d8ecb9bc1b8b02e54bc24d3b434933cc5e49;
CSV 3e95d6d28b8f54c0e4420abb82b57d0781b538164987b01323734102fe458134.
Original pilot state is readable at `/opt/mcp/data/msp-marketplace-reports/ozon-pilot-20261110`.
Pilot unit inactive, PrivateNetwork=yes, no drop-ins, temporary credential removed.
This is a verified collected report, NOT yet annual publication or all Ozon expenses.

## New artifact: PREPARED_NOT_EXECUTED

Fixed30 cabinet/month pairs, January–October2026; cabinet order Dmitrieva,
Laser Master,Novokshenov. Existing January is replayed from pinned source without
credentials/HTTP and included in canonical publication. At most29 new send entries.
No November/CURRENT or WB requests. No LLM/subagents/heartbeat, timer, new queue,
Redis provisioning, general privilege broker, unrelated restart or PR merge.

One pinned root launcher starts one transient deterministic supervisor
`msp-ozon-history-20261111.service` via systemd-run --no-block. It outlives console
disconnect; Restart=no, two-hour bound, explicit owned-control cleanup ExecStopPost.
Only the supervisor is root: provider HTTP executes as existing msp-reports identity
inside EXISTING msp-wb-pilot.service, exact FINAL path/body/cabinet with minimal
LoadCredential and expiring root job. Original controller.lock held across campaign.
Accepted base-unit/runtime/Redis origin+typed acceptance/config/active state verified.
No foreign controls, campaign directories or previous unit accepted; rerun refuses
instead of silently creating a fresh budget. Payload executable files are root-owned
and pinned before activation; trusted code uses only fixed root/data destinations.

Each month reserves existing atomic shared Redis Client-Id global bucket + safety
bucket60s, with additional inter-report65s pacing. Quota-only busy leaves no send
entry and allows at most10 bounded waits on same month; entry is durable before HTTP.
HTTP429 records shared cooldown and holds, no automatic HTTP replay. Timeout,
unknown outcome, corrupt/empty response, conflicting published month or any state
identity mismatch HOLD. Raw200 bytes retained and hashed before JSON/schema parsing.
No state/budget reset, deletion of source or automatic unknown-outcome retry.

Each monthly CSV retains source nested objects and _raw_json. B7 publisher uses
canonical month/year stable keys and atomic generation switch; staged and pinned
published business values compared, not only totals/hashes. Annual derives only
from verified monthly files. Exact Ozon generation scopes get reader0755/0644;
locks private, archive root0711 retained, WB untouched. Cleanup ownership is fsynced
before temporary controls; remove/stop only matching owned controls/credential.
Private ownership digest is not emitted in public progress. Cleanup/readback of
PrivateNetwork=yes and no drop-ins is required after every month and at stop.

## Tests, not installed runtime claims

Nine network-denied tests pass on Python3.14 and actual host3.12:
all30 fixed scopes and actual annual-value reconciliation; stable no-op publication;
corrupt/conflicting period HOLD; quota wait without send entry; job expiry/scope;
foreign-control refusal; owned cleanup; nonblocking/no-restart launch; full mocked
campaign and fail-stop at third job preserving original plan. Actual pilot151 rows
also passed offline CSV/B7 business-value roundtrip with zero provider calls and
zero production archive writes. New batch runtime/TLS/other-cabinet API access NOT
VERIFIED until the owner executes ROOT_OZON_HISTORY.txt and receipts are read back.
Packaging deterministic; exact manifest/archive/launcher/command hashes in
package-receipt.json. Shell command is one physical line, syntax checked.

## Targets, observability and next acceptance

- Raw monthly state: `/opt/mcp/data/msp-marketplace-reports/ozon-final-2026/CABINET/2026-MM/`
- B7: archive `.b7-generations/ozon_final_realization/CABINET/2026/`
- Root cumulative plan/attempts: `/var/lib/msp-ozon-history-20261111/` (private).
- Public progress: `/var/lib/msp-finance-control/results/ozon-history-2026.json`.
- Canonical reader instruction: docs/data-sources/OZON_FINANCIAL_REPORTS.md.

Scheduled/active is NOT complete. Completion requires30 exact identities with
COMPLETE worker receipts, actual retained responses/CSV, published generation
business-value equality, read access, annual month coverage and restored isolation.
Read final public receipt then independently reconcile current three annual scopes.
If HOLD, inspect exact month/nonce/state without repeating launcher. Do not infer
zero sales from an empty/missing report or claim full financial profit coverage.
Realization includes its listed commission components, not all logistics/advertising
expenses, accruals, bank payout or profit. WB current month remains paused.
