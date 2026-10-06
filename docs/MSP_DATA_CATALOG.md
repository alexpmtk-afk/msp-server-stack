# MSP data catalog

The REMOTE data layer for MSP reference/event data lives in:

- runtime database: `/opt/mcp/data/msp/msp_data.sqlite3`
- deployed semantics: `/opt/mcp/projects/msp-server-stack/config/msp-data/semantics/`
- sync application: `/opt/mcp/projects/msp-server-stack/apps/msp_data_sync/sync.py`
- systemd timer: `msp-data-sync.timer`

The source workbook is the read-only export spreadsheet `_05_экпорт: бд для МСП`.
The first implemented sources are `артикулы` and `самовыкупы`.

## Canonical SKU rule

`marketplace_sku` is the digital-only marketplace SKU. Source aliases include `market_article`
and `Артикул МП`. It is not the same as the marketplace article field that may contain letters.

## Update model

The database is not replaced on every run. Rows are inserted or updated by stable business keys.
HTTP validators (ETag/Last-Modified) are used when Google returns them; otherwise the source SHA-256
is compared and SQLite work is skipped for an unchanged snapshot. Source disappearance does not delete
previously stored rows automatically.

## Current business keys

- product catalog: `marketplace + store + marketplace_sku`
- self purchases: `marketplace + store + marketplace_sku + purchase_date`

## Schedule

`msp-data-sync.timer` runs daily at 08:00 Europe/Moscow and is persistent, so a missed run is started after boot.

## Verification

```bash
python3 /opt/mcp/projects/msp-server-stack/apps/msp_data_sync/sync.py \
  --config /opt/mcp/projects/msp-server-stack/config/msp-data/sync.json \
  --verify-only
```
