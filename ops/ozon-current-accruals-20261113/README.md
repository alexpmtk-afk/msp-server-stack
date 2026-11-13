# Ozon November CURRENT snapshot —13.11.2026

PREPARED_NOT_EXECUTED. Owner authorizes continuing after JanOct to the latest
available Ozon accrual data, all three cabinets. Fixed scope 2026-11-01..13,
Dmitrieva → Novokshenov → Laser Master; 39 cabinet-date queries before pagination,
max128 durable sender entries per cabinet /384 total, ten pages/day. Startup
must occur on13November Moscow; later date requires a fresh pinned range.

Each daily source response is retained verbatim before parsing; paginated using
provider last_id, no assumption about one response being the whole day. Empty
latest day remains an observed empty response, not proof all financial data is
final or no future postings exist. Current month and today's data provisional.
Reported latest_nonempty_date is from actual returned rows, not presumed lag.

Daily JSON + one month.csv/coverage snapshot per cabinet. Versioned dataset
**ozon_current_accruals**, CURRENT layout, never PERMANENT/ozon_financial_accruals.
Existing JanOct and realization snapshots neither redownloaded nor overwritten.
No cleanup of financial snapshots; no recurring schedule created by this task.
All source branches and nested JSON retained in _raw_json, including non-SKU
costs. Only data exposed by the accrual endpoint is claimed, not all seller APIs.

Accepted existing root worker/sharedRedis/controllerlock reused; exact runtime
assets checked, only own temporary activation/credentials cleaned. One root unit
runs each cabinet and independent source/publication verifier before handoff.
No blind retry after unknown transport/429/expiredcursor/corrupt/conflicting data.
Common run.py runs final verifier; same task automatically receives declarative
three-cabinet day counters with exact supervisor run_id, no panel special cases.

One physical root Bash command in ROOT_OZON_CURRENT.txt. Root-owned snapshot,
archive/member/both nested+outer manifest validation before installer execution.
No secrets, cabinet source data or production financial values in package.
Local network-denied tests exercise three synthetic13day scopes/current
publication, empty latest day, out-of-range rejection, corruption, sequential
handoff/HOLD and nested archive manifests. They are not production API acceptance.
After root activation read exact unit invocation, actual HTTPmeta/day receipts,
public results and verifier output before declaring successful collection.
