# MSP product cost catalog — five selected production sources

**State as of 2026-10-12: initial data already loaded. Daily import proposed at 07:45 MSK via a separate Hermes-user timer; see live REMOTE acceptance before claiming it is active.** Existing four-source sync stays at 08:00 Europe/Moscow. The importer ran from a pinned canonical GitHub checkout in the self-hosted runner workspace, not from a deployed module in `/opt/mcp/projects/msp-server-stack`; deployment to the protected project path is a separate prerequisite before enabling a daily user timer.

## Accepted first import — 2026-10-12, 08:22 UTC

- Preflight run: https://github.com/alexpmtk-afk/msp-server-bridge/actions/runs/38222771252
- Owner-authorized one-time backed-up first import: https://github.com/alexpmtk-afk/msp-server-bridge/actions/runs/38223166837
- Pinned canonical importer: `5c66211caaeea48384629d6f2ab77073be34ad46`
- Protected DB: `/opt/mcp/data/msp/msp_data.sqlite3`
- Independently verified backup (0600): `/opt/mcp/backups/msp/msp_data_before_product_cost_20261012T082235Z.sqlite3`
- Imported cost-current records: **957**, across **5** source/variant keys.
- Per-source imported: `ultra=148`, `zavoz=223`, `more=52`, `laser_old=277`, `laser_new=257`.
- Per-source rejected with run-level issue details: `ultra=12` (8 invalid costs and 4 duplicate-article rows), `zavoz=53` (invalid/blank cost), `more=16`, `laser_old=8`, `laser_new=0`. **Total rejected 89**. Four source sync runs are `partial` for these accepted source-quality issues; Laser new is `success`.
- Cost revision events: 0 on the initial snapshot (expected). Future changes append revisions.
- SQLite `integrity_check=ok`, `foreign_key_check=0`.
- Existing `product_listing`, `self_purchase`, `self_purchase_plan`, `price_event` and `sync_run` table row counts were independently confirmed **unchanged**.
- No cost timer/oneshot installed, no daily update enabled and no Telegram cost notifications configured.

These 957 entries are **cost-source records, not 957 distinct marketplace products**: Laser Master old/new represent two separate cost variants for many of the same internal articles.



## Input contract

Five source sheets were supplied by the owner on 2026-10-12:

| Source name | Exact tab | SKU/article field | Name | Cost field | Variant |
|---|---|---|---|---|---|
| ultra | Ultra24 | A | B | C «Себестоимость» | production |
| zavoz | Zavoz24 | A | B | C «Себестоимость» | production |
| more | MORE | A | B | C «Себестоимость» | production |
| laser_old | Лазер-Мастер | A | B | C «Себестоимость» | with_profit_legacy |
| laser_new | Себес без прибыли | E | F | AL «Себестоимость без прибыли» | without_profit_current |

The first three and the two Laser Master sheets belong to **two different** owner-selected workbooks. Spreadsheet IDs belong only in a separately protected REMOTE environment file, not in public Git. Source texts and amounts are not published to Git.

**Laser Master has two independent cost variants**; 'new, without profit' is the source chosen for current economic-cost analysis, while 'old, with profit' is retained for backwards comparison. Never blend them or silently fall back from one to the other. Other manufacturers' C columns do not explicitly establish whether profit is included; do not make that claim.

2026-10-12 read-only sampling of the populated source columns: 160 Ultra rows (152 valid cost), 276 Zavoz (223 valid), 68 MORE (52 valid), 285 Laser old (277 valid), 257 Laser new (257 valid). Two duplicate internal articles were observed in Ultra24. This is source health at inspection time, not live server import validation.

## Source quality status — numeric values and missing data

For every **present internal article row** from each of five feeds, keep a current
`product_cost_source_status` record, queryable through `v_product_cost_source_status`.
The `cost_status` is one of:

| cost_status | Display text | Current cost |
|---|---|---|
| available | Есть данные | Exact decimal value |
| no_data | Нет данных | SQL NULL |
| invalid_value | Ошибка источника | SQL NULL |
| duplicate_article | Повтор артикула | SQL NULL |

A bad or blank cost does **not** turn into 0 and is **not** silently taken from
another cost variant. The source status view exposes `last_confirmed_cost_decimal`
in a **different field** if an earlier valid observation exists, with timestamp.
An agent must not treat that historical number as a verified current cost.
Fixing a Google Sheet later automatically changes the status to `available`
on the next successful import. Current status rows from a previous snapshot
that have since disappeared from a successfully fetched sheet are retired;
the separate run-issue history remains.

For scheduler health, routine source gaps are visible as source-quality
`partial` records without producing a failing exit code. Missing/unauthorized
CSV, wrong headers, corrupt DB and unexpected transport errors still fail the
job; **never suppress a real operational failure**.

## Daily schedule and deployment

- Cost timer: `systemd/user/msp-product-cost.timer` at **07:45 Europe/Moscow**
- Existing four-source timer: **08:00 Europe/Moscow**, unchanged
- Cost oneshot: `systemd/user/msp-product-cost.service`, bounded by 540 seconds
- Runtime script: `/home/hermes/.local/share/msp-product-cost/sync.py`
  installed from an exact canonical GitHub commit with SHA verification
- Protected environment file: `/home/hermes/.config/msp/product-costs.env`
  (mode `0600`, owner `hermes`), specifies the direct CSV transport and both sheet IDs
- Python: `/usr/bin/python3`; CSV mode needs no OAuth client and no extra Python packages
- Timer `Persistent=false` avoids an unintended immediate missed-run catch-up
  on first activation; a day when REMOTE is down will not be backfilled automatically
- No modifications to `msp-data-sync.timer`, Hermes Gateway or source Google Sheets

Installation/activation is a separate protected operation and must be verified by
`systemctl --user` and a post-run SQLite integrity/row-status audit.

## Storage

The importer is isolated: `apps/msp_product_costs/sync.py`. Additive tables in the existing protected SQLite at `/opt/mcp/data/msp/msp_data.sqlite3`:
`product_cost_current`, `product_cost_revision`, `product_cost_run`, `product_cost_run_issue`, plus `v_product_cost_current` and `v_product_cost_listing_matches`.

Business key is `production + variant + normalized internal article`, not marketplace SKU; join to the existing product catalog using the internal article. A given internal article can have multiple marketplace listings and multiple independent manufacturing sources. The listing view exposes all matches, not one invented selection.

Prices are held as exact decimal TEXT, with comma decimal and nonbreaking spaces normalized. Cost formulas such as `#REF!`, blank, zero, and duplicate keys are not promoted as new costs; the last known valid value is preserved and a source issue recorded. Product records absent from new snapshots are not deleted. A changed cost produces an auditable revision. No effective-from date is supplied by source; `observed_at` is an ingestion timestamp only.

## Existing MSP CSV transport — preferred precheck

The first four production data catalogs use unauthenticated
`https://docs.google.com/spreadsheets/d/<id>/export?format=csv&gid=<gid>`.
The new cost importer now supports exactly the same HTTP/CSV path, with
`MSP_COST_TRANSPORT=csv` in its **protected environment file**.

For each of the five owner-selected tabs it uses the reviewed `gid`.
The old cost fields are A/B/C (and optional D), and the Laser new
cost fields are E/F/AL. It does not scrape the separate formulas,
helper columns or source working-sheet files.

**Access verified on REMOTE 2026-10-12:** all five cost tabs and the existing control tab returned HTTP 200 with correct CSV headers via unauthenticated Google export. Evidence: https://github.com/alexpmtk-afk/msp-server-bridge/actions/runs/38222133876 . No new account, OAuth or credential was used for the accepted first import. These sensitive original workbooks currently permit CSV access by their links; access policy deserves a separate owner review, and must never be broadened by the sync process.

Before any production import, run the read-only `--preflight` on REMOTE
using this transport and check **all five** source statuses. A login page,
HTML response, HTTP 403, wrong column headers or source formula issues
cannot be treated as successful data. Failed reads never replace
last-valid costs and do not modify existing catalog entries. If private
workbooks deny CSV export, use protected OAuth access or a separately
reviewed restricted export; no new Google account is inherently required.

```text
MSP_COST_TRANSPORT=csv
MSP_COST_MAIN_SHEET_ID=<main private workbook id>
MSP_COST_LASER_SHEET_ID=<Laser Master workbook id>
```

In CSV mode, `MSP_COST_GOOGLE_CREDENTIALS_FILE` is not needed.

## REMOTE authentication and safety barrier

ChatGPT can read both selected workbooks through a connected Google account; **that connector does not authorize the REMOTE process**. On 2026-10-12, GitHub Runner read-only audits in private `msp-server-bridge` Issues #246 and #247 found no existing Google Sheets/Drive credential or relevant registered MCP available to the `hermes` service. Current four-source MSP sync does not have OAuth: it reads the separate public-by-link CSV export.

**A new Google account is NOT required.** The supported choices for a future protected connector are:
- **User OAuth (preferred when using the owner's existing Google account):** owner personally consents once to read-only Google Sheets API permissions for the MSP program; save the resulting *authorized-user* refresh credentials in a protected server file. This may require creating an OAuth client application in Google Cloud, but it is not a new Google account. Its scope may cover all spreadsheets accessible to that Google account, so owner approval and token protection are essential.
- **Google service account (optional):** a dedicated non-human identity with read-only Viewer access granted only to the two source workbooks. This is an optional least-privilege alternative, not a prerequisite.

In either case, do not make source workbooks public and do not copy ChatGPT connector tokens into the server. Store **one owner-authorized credential JSON** as a regular file (never a symlink) with `hermes` ownership, mode 0600 under `/home/hermes/.config/msp/google-cost-reader.json`. Never put an OAuth client secret, access/refresh token, service account key, business cost or raw source sheet into GitHub, issues, Telegram or logs.

The dedicated protected `/home/hermes/.config/msp/product-costs.env` (owner `hermes`, mode 0600) will contain:
```text
MSP_COST_MAIN_SHEET_ID=<first private Google spreadsheet id>
MSP_COST_LASER_SHEET_ID=<second private Google spreadsheet id>
MSP_COST_GOOGLE_CREDENTIALS_FILE=/home/hermes/.config/msp/google-cost-reader.json
```

For compatibility only, the old `MSP_COST_GOOGLE_SERVICE_ACCOUNT_FILE` key is recognized if the new key is absent. The loader accepts **only** `authorized_user` or `service_account` credentials; no external-account or arbitrary configuration URLs are accepted. Neither OAuth choice has been provisioned, because **CSV already works from REMOTE**. OAuth remains optional if access to source workbooks is later restricted.

Install `apps/msp_product_costs/requirements.txt` into a dedicated `hermes` virtual environment, not system Python. This is **not** part of the existing four-source `msp-data-sync.service`.

Read-only source preflight: run `MSP_COST_TRANSPORT=csv python3 apps/msp_product_costs/sync.py --preflight` with the protected two source IDs in the Hermes environment. It fetches only the reviewed columns, validates all five headers and counts issues; **it does not open or modify SQLite**. Partial status from known broken formulas is expected but must be reviewed, not silently ignored.

The first owner-authorized import followed the read-only precheck and verified online backup. For subsequent imports, verify source availability, database health and non-overlapping writes first; do not delete historical data. Examine all five per-source statuses, duplicate/formula issue counts, integrity/FK checks, cost revision behavior, and unchanged Hermes/Telegram/four-source timer. Never overwrite the existing SQLite or run a root-level installer. Normal cost-sync warnings should be handled by a dedicated runbook; no notification is currently wired.

Legacy 08:15 schedule proposal is superseded by the owner's final **07:45 Moscow** choice. Verify actual enabled state from the REMOTE audit; documentation is not evidence of service activation.

## Offline verification

`python3 -m unittest discover -s tests -p 'test_msp_product_costs.py' -v`

The offline `--fixture` mode reads a developer-owned synthetic JSON mapping of exact source names to table rows and does not require Google credentials. Do **not** use a real private source snapshot as an unprotected fixture or commit it to GitHub.

## Semantic contract

Read `config/msp-data/semantics/product_cost.yaml` before using cost values; existing `product_catalog.yaml` explicitly excludes mutable costs. For an agent, both source variant and observed date must be named when quoting a value. The agent must not assume unmatched articles have zero cost.
