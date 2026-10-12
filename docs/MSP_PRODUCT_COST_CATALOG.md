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

## REMOTE authentication and safety barrier

These sheets are presently readable using the connected Google Drive account, **not yet verified as readable by the REMOTE host**. Do not make either workbook public to work around access. Use a new narrowly scoped Google Cloud **service account**, share **only those two workbooks** as Viewer with its identity, and store the JSON credential exclusively on REMOTE under `/home/hermes/.config/msp/product-cost-reader.json` with `hermes` ownership and mode `0600`. Keep its identity/permissions documented privately. No access token, JSON key, source costs, or raw payloads in Git, issue comments, logs or Telegram.

Store the following keys in a distinct Hermes-owned mode-0600 environment file (never in the shared Hermes Gateway secrets file):

```text
MSP_COST_MAIN_SHEET_ID=<private Google spreadsheet id>
MSP_COST_LASER_SHEET_ID=<private Google spreadsheet id>
MSP_COST_GOOGLE_SERVICE_ACCOUNT_FILE=/home/hermes/.config/msp/product-cost-reader.json
```

Install `apps/msp_product_costs/requirements.txt` into a dedicated `hermes` virtual environment, not system Python. This is **not** part of the existing four-source `msp-data-sync.service`.

After protected access is independently verified: take an online SQLite backup; execute a bounded read-only source precheck, and only then approve a first import. Examine all five per-source statuses, duplicate/formula issue counts, integrity/FK checks, cost revision behavior, and unchanged Hermes/Telegram/four-source timer. Never overwrite the existing SQLite or run a root-level installer. Normal cost-sync warnings should be handled by a dedicated runbook; no notification is currently wired.

Proposed recurrence after first accepted import: a **separate Hermes user** oneshot+timer following the 08:00 MSK existing catalog sync, e.g. 08:15 Europe/Moscow. This is a proposal, **not installed or enabled**. A timer alone does not establish successful imports.

## Offline verification

`python3 -m unittest discover -s tests -p 'test_msp_product_costs.py' -v`

The offline `--fixture` mode reads a developer-owned synthetic JSON mapping of exact source names to table rows and does not require Google credentials. Do **not** use a real private source snapshot as an unprotected fixture or commit it to GitHub.

## Semantic contract

Read `config/msp-data/semantics/product_cost.yaml` before using cost values; existing `product_catalog.yaml` explicitly excludes mutable costs. For an agent, both source variant and observed date must be named when quoting a value. The agent must not assume unmatched articles have zero cost.
