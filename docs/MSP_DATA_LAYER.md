# MSP four-source data layer

The single public export spreadsheet is configured in `config/msp-data/sync.json`.
Do not fetch source working spreadsheets. Product catalog contains reference fields only.
All four sources run in dependency order: products, self purchases, current price journal, archive price journal.
Business data stays outside Git in `/opt/mcp/data/msp/msp_data.sqlite3`.

## Preparation and installation

1. Run tests, syntax and secret checks on a dedicated branch. Open a PR, wait for passing CI and merge.
2. Deploy the merged canonical main to `/opt/mcp/projects/msp-server-stack`.
3. As administrator run `bash scripts/deploy/install-msp-data-sync.sh /opt/mcp/projects/msp-server-stack`.
4. Run first sync with `python3 apps/msp_data_sync/sync.py --config config/msp-data/sync.json --source all`.
5. Run `--verify-only`. Check all four sources, errors, dates, origin segments and integrity.
6. Repeat sync. No product, self-purchase or price-event growth should occur for unchanged source data.
7. Check `systemctl is-enabled msp-data-sync.timer`, `systemctl is-active msp-data-sync.timer`, `systemctl list-timers msp-data-sync.timer` and `systemctl show msp-data-sync.service -p Result -p ExecMainStatus`.

Timer: 08:00 Europe/Moscow, Persistent=true. Do not delete/recreate SQLite every day.
Before schema upgrades, create a SQLite backup with the SQLite backup API in the designated backups directory.
Legacy self-purchase keys are migrated by adding occurrence ordinal 1 without deleting existing purchases.

## Agent queries

`v_product_catalog`: reference lookup by marketplace/store/marketplace_sku.
`v_self_purchase`: purchases with catalog fallback for names/internal articles.
`v_price_history`: UNION-equivalent complete history through price_event, with source_segment/source_sheet and catalog_match_status.
Unmatched price events stay visible. No direct foreign key is imposed on historical price events because obsolete listings may not exist in the current catalog.
Actual FK from self_purchase to product_listing is checked via PRAGMA foreign_key_check.

Examples:

```sql
SELECT * FROM v_product_catalog WHERE marketplace='oz' AND store='laser' AND marketplace_sku=?;
SELECT source_segment,event_date,new_price,old_price,internal_article,product_name,catalog_match_status
FROM v_price_history WHERE marketplace=? AND store=? AND marketplace_sku=? ORDER BY event_date,source_ordinal;
SELECT source,source_row,error,raw_json FROM sync_error ORDER BY error_id DESC;
```

## Semantics

Read all six YAML files in config/msp-data/semantics. New price files use JSON syntax, a valid YAML 1.2 subset.
Header mapping is independent per price source: archive has a different SKU column position.
`Артикул наш` in price sources is a product label, not an authoritative internal article.
Never match histories by that label. Numeric values remain exact decimal TEXT, not binary float.
No currency is invented. Technical Google columns are excluded.

## Accounting and limitations

Each nonempty source row contributes to source_rows and to inserted/updated/unchanged/rejected.
Invalid rows retain original values and source row in sync_error. The formula sentinel row is explicitly logged as technical and rejected from business history.
Identical source problems are stored once in sync_error; later runs still report rejected counts in sync_run but do not append duplicate copies of the same error.
Valid rows commit even when another row fails; partial runs exit nonzero and are retried. Source-level failures do not prevent other sources from being attempted.
Catalog duplicate business keys are logged rather than silently overwriting. Missing catalog matches reject self purchases and log raw rows; price events are retained with unmatched status and are not treated as sync errors.
No absent source rows are deleted from historical storage. Conditional HTTP and content SHA skip clean identical snapshots; retries of partial snapshots only change modified business rows.
Multiple same-card same-date rows use source-order ordinal within the key. An immutable source event ID is unavailable: reordering/removal of these rows can make identity ambiguous. This is an explicit limitation, not a guaranteed identity under arbitrary source rewrites.
Rows transferred between current/archive retain separate origins; cross-segment identity is not guessed.
Sync errors contain business data: never commit the database or raw error dumps.
This layer does not expose a new MCP server; future tools can use documented views and semantics.
