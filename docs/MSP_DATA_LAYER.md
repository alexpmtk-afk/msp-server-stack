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

## Self-purchase source contract (2026-10-08)

The upstream workbook "Самовыкуп новых товаров" / "Реестр выкупов/отзывов"
feeds the public export spreadsheet's "самовыкупы" sheet. The current
headers are "мп", "магазин", "Артикул МП", etc.
Marketplace codes are wb/oz; store codes are laser/novok/ultra.
The column "магазин" gives the actual marketplace store/cabinet directly,
not a legal entity; do NOT derive or override it through the old ЮЛ mapping.
Completed rows must match source marketplace + store + numeric marketplace_sku
against product_listing and require date/quantity. When purchase date is missing,
the row is a planned self-purchase only if "Артикул МП" is a nonempty numeric SKU.
Quantity can remain SQL NULL until completed; missing date is normal and stored in
self_purchase_plan. A blank "Артикул МП" field skips the entire row without error
or an inferred SKU, regardless of date and quantity. Blank values must not be guessed.

The SQLite legal_entity column remains for backwards compatibility,
but is not supplied by the current source. New-format imports use an
empty string in this legacy field to indicate "not supplied" and must not
claim that legal_entity identifies a company. Old exports containing "ЮЛ"
and no "магазин" retain an explicit legacy-only mapping.
Owner-approved upstream source corrections on 2026-10-08 changed
12 historical entries (rows 68-75 and 80-83) to store novok.
Canonical semantics are in config/msp-data/semantics/catalog.yaml and self_purchase.yaml.

## Planned self-purchases and incremental completion (owner-approved 2026-10-08)

Current export rows without purchase date and WITH a numeric marketplace SKU are
planned purchases: 8 rows (42-46, 51-53) exist at the time of approval.
They are persisted in self_purchase_plan (v_self_purchase_plan for current plans),
with NULL for missing purchase date or quantity. Row 84 has no "Артикул МП"
and is deliberately SKIPPED, not imported as planned or completed. Plans are not included in
v_self_purchase, self_purchase_quantity, or any completed-sales adjustment.
An absent purchase date is not a rejected row or a sync error; it must not
make the self_purchase sync status partial. A blank "Артикул МП" is also not
a source error in this catalog; it is reported as skipped_missing_sku.
If a previously loaded planned row loses its SKU, mark that plan inactive
and keep prior content only in the internal audit table, never in the active
v_self_purchase_plan view. If the SKU is later filled, a new source refresh
can import it normally. Validate only this dataset, not prices or product catalog.

Every new/changed source snapshot is scanned fully, including older rows.
When a planned row acquires a valid date, SKU and positive quantity and
matches product_listing, ingestion inserts/upserts the completed self_purchase
and removes its current plan placeholder in the same transaction. A completed
row with missing mandatory fields remains rejected and auditable. Any changed
fields in an existing plan are updated; unchanged business rows are not
rewritten. Old completed purchases are not deleted when absent from source;
old plans missing from current source are marked is_current=0 and excluded
from the live plan view. Historic sync_error entries are retained as an
audit trail: use the latest sync_run and current plan view for live health.

The source has no immutable row/event ID. For plans, source_row (CSV/Sheet
line number) is a provisional identity; reordering or inserting rows can
change linkage. For duplicate completed SKU/date events, source_ordinal
remains provisional as documented below. Planned and completed counts are
separate, and sync_run.planned records the number of planned rows seen.

Queries:

```sql
SELECT source_row,marketplace,store,marketplace_sku,internal_article,quantity,purchase_date
FROM v_self_purchase_plan ORDER BY source_row;
SELECT count(*) AS planned_count FROM v_self_purchase_plan;
SELECT source,status,source_rows,planned,skipped_missing_sku,rejected FROM sync_run
WHERE source='self_purchase' ORDER BY run_id DESC LIMIT 1;
```

## Source-linked completed self-purchase dates (owner-approved 2026-10-08)

The Google register is the source of truth for which self-purchases are actually
completed, including moved or removed purchase dates. Completed items remain
in `self_purchase` and planned rows in `self_purchase_plan`. The upstream
source has no immutable event ID. `self_purchase_source_link` records the
provisional source row and its last completed business key
(marketplace,store,marketplace_sku,purchase_date,source_ordinal).

On each changed source snapshot, if a linked source row retains the SAME
marketplace+store+SKU but the date changes, import the newly dated completed
event and retire the old entry from active `self_purchase` into
`self_purchase_revision` (`v_self_purchase_revisions`). If the date is
removed, the formerly completed entry is retired into revisions and the row
becomes planned; the previous date, quantity, authoring data and timestamps
stay auditable. This happens transactionally; a repeated refresh must not
retire again or duplicate new records. An old key still represented elsewhere
in the current source is not retired, protecting repeated same-SKU purchases.

If a row disappears, or its marketplace/store/SKU changes at the same
position, it is AMBIGUOUS whether it is the same event: do not automatically
delete previously completed records. Source-line identity remains provisional
until the Google register has a permanent immutable event ID. The first new
sync initializes source links for currently completed records, including
previously existing rows. Legacy records WITHOUT links are not blindly
purged.

**One-time confirmed legacy reconciliation:** before source-row linkage,
five stale completed entries (WB/laser, rows 42-46, SKU 1535826937,
1591555117, 1682686239, 1683303349, 1685869122) remained in SQLite
after their dates were cleared from the Google register. The owner explicitly
approved moving ONLY those five exact events into revision history after
a full SQLite backup, verified source values and exact-key checks. This is
not a general permission for indiscriminate completed-event purging.

Queries:
```sql
SELECT count(*),coalesce(sum(quantity),0) FROM self_purchase;
SELECT marketplace_sku,purchase_date,quantity,change_reason,source_row
FROM v_self_purchase_revisions ORDER BY archived_at DESC;
SELECT source_row,marketplace_sku,purchase_date
FROM self_purchase_source_link ORDER BY source_row;
```

## Cleared price archive — owner-approved one-time reset 2026-10-08

Source: `_05_экпорт: бд для МСП`, sheet `журнал цен (архив)` (gid 2062539510).
The owner intentionally removed every archive business row and instructed REMOTE
to purge all previously loaded *archive* price events (6,472 events). The
separate `журнал цен` current source and all current price events (3,459 at
reset time) are expressly retained.

The archived sheet is empty in business columns A:R, including its header.
There are 260 residual, **technical-only** rows in W/Y/Z. None contains
a price event in A:R. These technical scraps are not archive business data.
The importer now considers an archive source with no values in business
columns A:R a valid **empty snapshot** (success with 0 source rows).
Only `price_journal_archive` receives this exception; an empty current
journal is a source error. The archive may be repopulated later; the normal
header-based importer will resume automatically.

**CRITICAL SAFEGUARD:** routine synchronization remains non-destructive
(`do_not_delete_on_source_absence`). No automatic purge occurs merely because
the archive became empty. The operator specifically authorized a one-time
admin-only deletion `DELETE FROM price_event WHERE source_segment='archive'`,
strictly after independent source-empty verification and an online SQLite
backup. Its preconditions and resulting archive/current counts are audited
in the corresponding one-time REMOTE deployment report. Old sync-run/error
logs remain as historical audit records, not live archive price events.

Agents must report archive = 0 and current = actual count **after** the
completed one-time reset; they must not use the pre-reset 6,472 historical
archive count as current fact.

## Accounting and limitations

Each nonempty source row contributes to source_rows; self_purchase also counts planned and skipped_missing_sku independently of inserted/updated/unchanged/rejected.
Price journals use skipped_technical for **explicitly recognized formula sentinel rows**, not for malformed business rows. In the current "журнал цен" export, the row with date-cell label "СТРОКА ФОРМУЛ НЕ УДАЛЯТЬ" is skipped only when marketplace, store and marketplace SKU fields are empty. It is never an actual price event. It is counted in source_rows and skipped_technical, not rejected and not sync_error. A full valid-business-data run therefore reports success, not partial. Missing business SKU/date or other invalid data still produce partial and a recorded error.
The skipped_technical counter is stored on sync_run (additively migrated), included in successful, unchanged-snapshot and not-modified reporting; old historical formula-row errors remain in sync_error audit, but do not indicate a current failure.
Identical source problems are stored once in sync_error; later runs still report rejected counts in sync_run but do not append duplicate copies of the same error.
Valid rows commit even when another row fails; partial runs exit nonzero and are retried. Source-level failures do not prevent other sources from being attempted.
Catalog duplicate business keys are logged rather than silently overwriting. Missing catalog matches reject self purchases and log raw rows; price events are retained with unmatched status and are not treated as sync errors.
No absent source rows are deleted from historical storage. Conditional HTTP and content SHA skip clean identical snapshots; retries of partial snapshots only change modified business rows.
Multiple same-card same-date rows use source-order ordinal within the key. An immutable source event ID is unavailable: reordering/removal of these rows can make identity ambiguous. This is an explicit limitation, not a guaranteed identity under arbitrary source rewrites.
Rows transferred between current/archive retain separate origins; cross-segment identity is not guessed.
Sync errors contain business data: never commit the database or raw error dumps.
This layer does not expose a new MCP server; future tools can use documented views and semantics.
