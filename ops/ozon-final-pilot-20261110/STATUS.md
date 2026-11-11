# Ozon closed-month collection — 10 November 2026

**Prepared and locally tested; no authenticated Ozon request or privileged activation has run.**

Owner scope: collect closed months January–October 2026 for Dmitrieva, Laser Master,
Novokshenov. November/current data and daily WB collection remain paused.
First step is one January FINAL realization-by-posting report for `ozon_dmitrieva`.
This report is not a complete accounting of all Ozon expenses or bank payouts.
Do not mark the year closed on this pilot, or substitute orders for realized sales.

## Evidence and installation boundary

- 12 network-denied local tests pass, including no-refetch after timeout,
  successful response retention before failed validation, corrupt-response/CSV
  HOLD, exact method/body/cabinet scope, shared Redis key identity, separate
  global/safety cooldown, root refusal and temporary-activation cleanup model.
- Packaging is byte-reproducible; regular files only, pinned archive/manifest,
  bounded member inventory, hashes before extraction, root-owned executable snapshot.
  `package-receipt.json` records hashes. One-line Bash command syntax checked;
  launcher actually refused non-root before any protected reads/writes.
- Existing protected Ozon credentials have not yet been read or proved valid.
  New runtime/TLS/provider response/real cleanup are NOT VERIFIED.
- Current official docs redirect-loop; current official developer community
  confirms the report family. Exact request/response shape comes from an attributed
  mirrored OpenAPI artifact in `method-contract.json`, not a claim of a live current spec.
  A strict bounded pilot may HOLD on a changed contract while retaining response bytes.

## Fixed execution contract

`ROOT_OZON_PILOT.txt` is ONE physical Bash line for a Linux root console.
It copies a pinned verifier into a fresh root-owned directory. The verifier pins
and validates the complete archive before writing executable payload files.
The reviewed code temporarily activates the EXISTING `msp-wb-pilot.service`,
under its existing `msp-reports` UID/GID, using the existing shared Redis admission.
No new queue, account, Redis install, timer, general privilege broker or model job.

Before mutation, check accepted base-unit, interpreter, Redis package/runtime links,
accepted quota receipt, loopback Redis configuration, selected credential shape,
inactive executor/no foreign drop-ins, exact archive owner/mode and absent prior run.
Hold `/var/lib/msp-finance-control/controller.lock` for the entire activation.
Only one minimal Ozon pair enters systemd LoadCredential; WB credentials are excluded.
Only `/v1/finance/realization/posting`, body year=2026/month=1, one sender entry.
The four-method Ozon blanket gate remains unset. Global Client-Id Redis key is
unchanged and additional safety pacing is 60s (local precaution, not claimed vendor cap).
No redirects/proxies/retry. Response bounded at 128 MiB and saved before JSON/schema work.
Entry/hash journals are fsynced and cannot be silently reset.
One successful complete monthly response has no pagination in the recovered contract.
Non-200, empty report, ambiguous JSON, invalid period/identity, corruption or unknown
network outcome hold without another request.

## Outputs and reconciliation

Executor state:
`/opt/mcp/data/msp-marketplace-reports/ozon-pilot-20261110/`

- response.json: exact successful provider bytes, including legal/report header.
- response.meta.json: HTTP status and response digest.
- entry.json + dispatch.json: conservative cumulative entry versus dispatch attempt.
- report.csv: BOM/semicolon canonical staging; nested objects and _raw_json retained.
- worker-result.json: sanitized result (not raw monetary/header/secret data).

Public root receipt:
`/var/lib/msp-finance-control/results/ozon-dmitrieva-2026-01-pilot.json`

Only `VALIDATED_PILOT_NOT_PUBLISHED` + HTTP200 + hashes + rows + cleanup=true
proves the pilot stage. Annual B7 publication/coverage is explicitly false.
An inactive service or successful command alone proves neither download nor year closure.
Read the exact public receipt and verify CSV/raw hashes after the owner runs the command.
If HOLD, inspect saved sanitized shape/status/frames; do not rerun the launcher,
delete state or reset budget. Valid saved responses are processed without credentials/transport.

Temporary activation is expiring, Restart=no, 180s runtime bound; only the owned
drop-in is removed after inactivity, and original PrivateNetwork=yes/no drop-ins
must read back. Only matching minimal credential copy is removed. Retain reports,
original credentials, root snapshots and all cumulative evidence. Unknown partial
installation or foreign controls require reconciliation, never broad cleanup.

Next acceptance after successful pilot: offline validated B7 monthly/annual publication,
read access through the default-profile instruction, remaining January–October months
under original cumulative per-month plans and same controller, then coverage reconciliation
for all three legal entities. Additional Ozon financial expense reports need explicit
source semantics; realization is not total profit or a bank payment.


## Preflight correction — 11 November 2026

Owner ran the pinned launcher: snapshot `/var/lib/msp-ozon-final._6rkj4nr`, preflight line111 HOLD before any executor start/state/admission. Root console frames establish erroneous whole-receipt SHA comparison. The accepted supervisor compares receipt.probe_sha256 (probe program origin), then exact typed acceptance fields. Fixed Ozon verifier to reproduce that contract, reject duplicate keys/wrong origin/failed results/type-confused values, and require active existing Redis. No new synthetic writes or backend/credential permission changes. 13 network-denied tests PASS. Revised bundle/launcher prepared, NOT root-executed; old preflight failure is not a provider error or consumed send entry. Preserve old snapshot; same January cabinet/plan and max1 budget.
