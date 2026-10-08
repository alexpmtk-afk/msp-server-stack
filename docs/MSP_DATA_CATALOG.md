# MSP data catalog — current four-source implementation

Canonical detailed contract: [MSP_DATA_LAYER.md](MSP_DATA_LAYER.md).

## Runtime and source

- Business SQLite: `/opt/mcp/data/msp/msp_data.sqlite3` (not committed to Git).
- Schema and sync: `/opt/mcp/projects/msp-server-stack/apps/msp_data_sync/`.
- Machine-readable semantics: `/opt/mcp/projects/msp-server-stack/config/msp-data/semantics/`.
- Configuration: `/opt/mcp/projects/msp-server-stack/config/msp-data/sync.json`.
- Source: the single read-only Google export workbook `_05_экпорт: бд для МСП`; do not separately fetch upstream working workbooks.

**All four source datasets are implemented:**

1. `артикулы` → `product_catalog`: Marketplace/store/SKU ↔ internal article and product name.
2. `самовыкупы` → `self_purchase`: completed purchases and separate plans.
3. `журнал цен` → `price_journal_current`: current price events.
4. `журнал цен (архив)` → `price_journal_archive`: separate archived segment, currently an intentionally empty source snapshot.

The read views include `v_product_catalog`, `v_self_purchase`, `v_self_purchase_plan`, `v_self_purchase_revisions` and the unified `v_price_history`. Semantics and the complete handling rules live in `config/msp-data/semantics/` and `docs/MSP_DATA_LAYER.md`.

## Canonical SKU

`marketplace_sku` is the digits-only marketplace SKU, also called `Артикул МП` in source tables. Do not confuse this with a marketplace article containing letters. Catalog listing identity is `marketplace + store + marketplace_sku`.

Completed self-purchase identity includes marketplace, store, marketplace_sku, purchase_date **and occurrence ordinal**. Planned purchases are provisionally bound to source row position; this is not an immutable event ID. Records with missing purchase date but a valid numeric SKU remain plans; blank-SKU rows are skipped. Do not infer a missing SKU or silently delete historical events when source rows change. See the detailed reconciliation and revision rules in the main data-layer document.

## Synchronization and notifications

The database is incremental, not rebuilt daily: ETag/Last-Modified and content SHA-256 can skip unchanged snapshots; valid changed business rows are applied without duplicating existing events. A missing source row is not an automatic instruction to delete historical events. The archived price journal's currently empty snapshot is owner-approved; it must not trigger a repeated destructive purge.

Production uses the `hermes` **user** units:

- `systemd/user/msp-data-sync.service` — calls `apps/msp_data_sync/run_with_alerts.py`.
- `systemd/user/msp-data-sync.timer` — 08:00 Europe/Moscow daily, `Persistent=true`.
- Telegram alerts go through the existing Hermes bot to `АП_Лазер / Удалённый сервер` on source `partial`/`failed`, with deduplication and a single recovery alert; ordinary healthy runs are silent.

Run `systemctl --user` as `hermes`, **not** root-level `systemctl`. The retired root installer/system units are not supported recovery paths. For reviewed user-systemd installation/recovery, use `scripts/deploy/install-msp-data-sync.sh --check` first and follow [MSP_DATA_LAYER.md](MSP_DATA_LAYER.md). Installing a persistent timer may execute a missed run; it is not a read-only check.

## Safe verification (read-only)

Check timer: `systemctl --user is-active msp-data-sync.timer` and `systemctl --user list-timers msp-data-sync.timer`.

Check SQLite and four-source ingestion without fetching live sources:

`python3 /opt/mcp/projects/msp-server-stack/apps/msp_data_sync/sync.py --config /opt/mcp/projects/msp-server-stack/config/msp-data/sync.json --verify-only`

A timer being enabled does not prove the scheduled sync actually ran: verify the latest `sync_run` status and timestamps for each of the four sources. SQLite integrity and foreign keys should also be checked before claiming acceptance.
