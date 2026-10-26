# MSP Production — two separate source catalogs

Sources provided October 26, 2026. This implementation is additive to the
existing /opt/mcp/data/msp/msp_data.sqlite3 and never changes product pricing,
self-purchases, stock, Hermes Gateway or existing 07:45/08:00 timers.

| Catalog | Google source tab | Physical table | Intended schedule |
|---|---|---|---|
| Маскировка/швейное производство | ГЗП МП/ОРК 25 | production_sewing_order | Daily 07:35 Europe/Moscow |
| Металлические изделия (ЛМ, АНТ) | Загрузка ЛМ/АНТ | production_metal_order | Owner has not selected schedule; manual only |

Source identities: spreadsheet IDs stored in protected REMOTE environment, tab
gids embedded in approved implementation. Google data is read by the same
unauthenticated CSV route previously accepted for MSP **only if** the two
source workbooks actually allow direct export from REMOTE; initial preflight
must verify both. Never broaden Google sharing permissions automatically.

Business columns exactly match the respective semantics
`config/msp-data/semantics/production_sewing.yaml` and
`config/msp-data/semantics/production_metal.yaml`.
Source row number is a physical location, not a unique order ID: a single
article can have many orders, one numbered order may cover several articles,
and an order can be split by /1 and /2. Do not merge them based on SKU or
order number, and do not pretend row moves are stable order identities.

`production_import_run` tracks every import, `production_row_revision`
records changed full source rows and previous values, `production_data_issue`
holds issues such as missing article, missing order number, invalid quantity
or ambiguous date. Date values without an unambiguous full four-digit year
are kept verbatim and ISO date is NULL. Zero is never invented for an empty
quantity. A business row without an article remains in the catalog.
Formula-only filler rows (e.g. metal column G showing 0 alone) are omitted.
Rows removed from the successful current source snapshot become
`is_current=0` but are not deleted. Every data field includes the raw value.

Sewing schedule is 07:35 MSK, 10 minutes before existing 07:45 cost and
25 minutes before 08:00 main sync. The sewing user oneshot
`msp-production-sewing.service` has 420-second timeout so a stalled
production read should terminate before 07:45. Timer is `Persistent=false`
to prevent unexpected catch-up. Metal `msp-production-metal.service`
is available as an on-demand unit with **no metal timer** until owner
selects its cadence. Both use the same independently installed executable
but different source and physical storage tables. Separate source-specific
backups, import acceptance and timer activation must be verified live.

Read-only preflight, after approved environment configuration:

```
MSP_PRODUCTION_SEWING_SHEET_ID=<protected-id> MSP_PRODUCTION_METAL_SHEET_ID=<protected-id> \
  python3 apps/msp_production_sync/sync.py --source sewing --preflight
```

The companion metal preflight uses `--source metal`.
The source parser must not write to a Google Sheet, and neither source
requires modifying the Excel/Google workbook.

First import safety gate: verify source counts and exact headers, existing
MSP DB integrity, protected online SQLite backup mode 0600, execute importer
under `hermes`, backread row counts and verify pre-existing catalog counts
unchanged. Activate 07:35 timer only after a successful first import of the
sewing dataset. Keep working Hermes and existing timers unchanged.
