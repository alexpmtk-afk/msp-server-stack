# MSP product cost catalog — five selected production sources

**State: implementation staged in GitHub, not activated on REMOTE.** No existing MSP data catalog or user service is replaced.

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

**Important access prerequisite:** the CSV path succeeds only if Google
already allows unauthenticated export of the two original workbooks. The
existing `_05_экпорт` is accessible by link; this is NOT proof that the
two original cost workbooks can be accessed without login. In particular,
do not make confidential cost sheets public to bypass permission checks.

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

For compatibility only, the old `MSP_COST_GOOGLE_SERVICE_ACCOUNT_FILE` key is recognized if the new key is absent. The loader accepts **only** `authorized_user` or `service_account` credentials; no external-account or arbitrary configuration URLs are accepted. Neither choice has been provisioned, and live Google access from REMOTE has not yet been verified.

Install `apps/msp_product_costs/requirements.txt` into a dedicated `hermes` virtual environment, not system Python. This is **not** part of the existing four-source `msp-data-sync.service`.

Read-only source preflight: run `python3 apps/msp_product_costs/sync.py --preflight` in the dedicated authenticated Hermes environment. It fetches only the reviewed columns, validates all five headers and counts issues; **it does not open or modify SQLite**. Partial status from known broken formulas is expected but must be reviewed, not silently ignored.

After protected access is independently verified: take an online SQLite backup; execute the bounded read-only source precheck, and only then approve a first import. Examine all five per-source statuses, duplicate/formula issue counts, integrity/FK checks, cost revision behavior, and unchanged Hermes/Telegram/four-source timer. Never overwrite the existing SQLite or run a root-level installer. Normal cost-sync warnings should be handled by a dedicated runbook; no notification is currently wired.

Proposed recurrence after first accepted import: the staged, **disabled** dedicated Hermes-user files `systemd/user/msp-product-cost.service` and `systemd/user/msp-product-cost.timer`. The timer proposes 08:15 Europe/Moscow, after the existing four-source 08:00 schedule. The service expects the dedicated authenticated Hermes venv and protected 0600 env file. **Neither unit is installed or enabled on REMOTE.** Confirm first import and the business cadence before enabling a persistent timer; enabling it may immediately run a missed synchronization.

## Offline verification

`python3 -m unittest discover -s tests -p 'test_msp_product_costs.py' -v`

The offline `--fixture` mode reads a developer-owned synthetic JSON mapping of exact source names to table rows and does not require Google credentials. Do **not** use a real private source snapshot as an unprotected fixture or commit it to GitHub.

## Semantic contract

Read `config/msp-data/semantics/product_cost.yaml` before using cost values; existing `product_catalog.yaml` explicitly excludes mutable costs. For an agent, both source variant and observed date must be named when quoting a value. The agent must not assume unmatched articles have zero cost.
