# WB daily/weekly — candidate 13.11.2026

Status: PREPARED_NOT_INSTALLED. No production provider calls or test Telegram sends.
The root command is ROOT_WB_DAILY.txt, one physical Bash line, Linux root console.
Never execute start_root.py directly from a Hermes-writable checkout. The command
copies a pinned launcher into a fresh root-owned directory; it verifies the
archive, every member and both nested and outer manifests before execution.

## Owner policy

- Three cabinets: wb_dmitrieva, wb_laser_master, wb_novokshenov.
- Both reportType1 main and reportType2 WB buyouts/EAEU, not self-purchases.
- Every day08:45 Europe/Moscow, daily yesterday plus uncovered recent backlog.
- Monday starts with previous-week weekly discovery, ten total availability
  checks separated by20min. Ready documents/types are reused.
- Daily has three total checks separated by20min. Explicit204 absence is WAIT,
  not an exception and not proof of zero activity. After the limit, normal idle
  until the next applicable run and one scoped Remote Server notice.
- Bootstrap immediately refreshes weekly discovery from2025-12-29 through
  yesterday, reuses existing complete source documents and captures missing
  weekly documents; then plans daily dates from actual weekly coverage.
- Exact month/year report boundaries retained. Weekly replaces only equivalent
  fully covered daily periods, type and currency. No source/history deletion.
- The canonical WB reader selects one atomic active-source view; it never adds
  superseded daily data or old view generations. IDs remain exact Python ints
  and CSV strings; CSV preserves all columns and original row JSON.

## Isolation, limits and failures

Existing msp-wb-pilot executor, runtime, user995, shared Redis quota, fixed WB
finance list/detail endpoints. No second sender, token rotation, model calls,
Gateway changes, main merge, or unrelated service edits. Root lifecycle lock is
per marketplace; common finance slot is held only around owned worker steps,
not20min availability waits. Related Ozon code changes only this slot lifetime;
08:40 timer, requests, existing reports and other Ozon sources stay unchanged.
Each attempt has max100 durable request entries; quota pause resumes the same
attempt without resending cached pages. Unknown response, partial evidence,
HTTP errors, corrupt source, foreign activation or exhausted budget are HOLD,
not normal missing-report retries. Cached204 and complete pages replay locally.
Telegram SENDING/uncertain outcomes are never sent blindly a second time.

## Deployment and evidence

Installer refuses drift, active Ozon/shared worker, unknown targets and partial
installation before writes. Preserves backups of exact reader/guide/Ozon wiring
under /var/lib/msp-wb-daily-weekly/backups; preserves old immutable Ozon release.
No root installation has been exercised; transaction tests are isolated fixtures.
verify_release.py tests the actual extracted archive on Python3.14 and3.12,
checks import isolation, disables live network, runs WB35 and Ozon22 tests,
checks a real flock fixture and systemd unit syntax, and checks reproducibility.
Those tests do not establish live daily API permission, installed sandbox
acceptance, delivery, or successful initial/scheduled loading.

After owner root execution, read back:
- /var/lib/msp-wb-daily-weekly/installation.json
- /var/lib/msp-finance-control/results/wb-daily-weekly.json
- msp-wb-daily-weekly.service/.timer activity and next execution
- nested active Ozon root_release and unchanged next08:40 timer
- worker idle PrivateNetwork=yes/noDropIns after completion or normal pause
- per-cabinet list/detail terminal evidence, parts, request counts and catalog
  generation hashes; fully consume the canonical reader for both types.
Do not replay activation or provider requests merely to inspect status. A running
service is not proof of backfill completion. source204 means unavailable, not0.

Archive and source IDs stay local to this candidate directory. Published source
handoff excludes production baseline-coverage.json and original financial data.
