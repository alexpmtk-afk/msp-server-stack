
    create table if not exists product_listing(
      marketplace text not null, store text not null, marketplace_sku text not null,
      marketplace_article text, internal_article text, internal_article_normalized text, product_name text,
      row_hash text not null, first_seen_at text not null, last_seen_at text not null, updated_at text not null,
      primary key(marketplace,store,marketplace_sku),
      check(marketplace_sku<>'' and marketplace_sku not glob '*[^0-9]*'));
    create index if not exists ix_product_internal on product_listing(internal_article_normalized);
    create index if not exists ix_product_sku on product_listing(marketplace_sku);
    create table if not exists self_purchase(
      marketplace text not null, store text not null, legal_entity text not null, marketplace_sku text not null,
      internal_article text, product_name text, quantity integer not null check(quantity>0), purchase_date text not null,
      review_date text, review_url text, review_draft text, row_hash text not null, created_at text not null, updated_at text not null,
      source_ordinal integer not null default 1,
      primary key(marketplace,store,marketplace_sku,purchase_date,source_ordinal),
      foreign key(marketplace,store,marketplace_sku) references product_listing(marketplace,store,marketplace_sku));
    create index if not exists ix_self_sku_date on self_purchase(marketplace_sku,purchase_date);
    create table if not exists sync_state(source text primary key,etag text,last_modified text,content_sha256 text,last_success_at text,source_rows integer);
    create table if not exists sync_run(run_id integer primary key autoincrement,source text,started_at text,finished_at text,status text,http_status integer,source_rows integer default 0,inserted integer default 0,updated integer default 0,unchanged integer default 0,rejected integer default 0,planned integer not null default 0,skipped_missing_sku integer not null default 0,skipped_technical integer not null default 0,message text);
    create table if not exists sync_error(error_id integer primary key autoincrement,run_id integer,source text,source_row integer,error text,raw_json text,created_at text);
    create view if not exists v_product_catalog as select marketplace,store,marketplace_sku,marketplace_article,internal_article,internal_article_normalized,product_name from product_listing;
    create view if not exists v_self_purchase as select s.marketplace,s.store,s.legal_entity,s.marketplace_sku,coalesce(nullif(s.internal_article,''),p.internal_article) internal_article,coalesce(nullif(s.product_name,''),p.product_name) product_name,s.quantity,s.purchase_date,s.review_date,s.review_url,s.review_draft from self_purchase s left join product_listing p using(marketplace,store,marketplace_sku);
    
-- Additive price-history schema; business price values are exact decimal TEXT.
CREATE TABLE IF NOT EXISTS price_event (
 event_key TEXT PRIMARY KEY, source_segment TEXT NOT NULL CHECK(source_segment IN ('current','archive')),
 source_sheet TEXT NOT NULL, marketplace TEXT NOT NULL, store TEXT NOT NULL,
 marketplace_sku TEXT NOT NULL CHECK(marketplace_sku<>'' AND marketplace_sku NOT GLOB '*[^0-9]*'),
 event_date TEXT NOT NULL, source_ordinal INTEGER NOT NULL,
 new_price TEXT, old_price TEXT, list_price TEXT, minimum_price TEXT, discount_percent TEXT,
 direction TEXT, note TEXT, source_product_label TEXT, row_hash TEXT NOT NULL,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(source_segment,marketplace,store,marketplace_sku,event_date,source_ordinal)
);
CREATE INDEX IF NOT EXISTS ix_price_listing_date ON price_event(marketplace,store,marketplace_sku,event_date);
CREATE VIEW IF NOT EXISTS v_price_history AS SELECT e.*,
 p.internal_article,p.product_name,
 CASE WHEN p.marketplace_sku IS NULL THEN 'unmatched' ELSE 'matched' END AS catalog_match_status
 FROM price_event e LEFT JOIN product_listing p USING(marketplace,store,marketplace_sku);


-- Planned rows intentionally permit missing purchase date, quantity and SKU.
-- Source row number is the best available provisional identity until an immutable source ID exists.
CREATE TABLE IF NOT EXISTS self_purchase_plan (
 source_row INTEGER PRIMARY KEY CHECK(source_row>=2),
 marketplace TEXT NOT NULL CHECK(marketplace IN ('wb','oz')),
 store TEXT NOT NULL,
 marketplace_sku TEXT CHECK(marketplace_sku IS NULL OR (marketplace_sku<>'' AND marketplace_sku NOT GLOB '*[^0-9]*')),
 internal_article TEXT,
 product_name TEXT,
 quantity INTEGER CHECK(quantity IS NULL OR quantity>0),
 purchase_date TEXT,
 review_date TEXT,
 review_url TEXT,
 review_draft TEXT,
 row_hash TEXT NOT NULL,
 first_seen_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 is_current INTEGER NOT NULL DEFAULT 1 CHECK(is_current IN (0,1)),
 last_change_run INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_self_purchase_plan_store_sku ON self_purchase_plan(marketplace,store,marketplace_sku);
CREATE VIEW IF NOT EXISTS v_self_purchase_plan AS
SELECT source_row,marketplace,store,marketplace_sku,internal_article,product_name,
 quantity,purchase_date,review_date,review_url,review_draft,first_seen_at,updated_at
FROM self_purchase_plan WHERE is_current=1;


-- Source-row binding is provisional until the upstream source supplies immutable event IDs.
-- Only reconcile the prior completed event when row and listing (marketplace/store/SKU)
-- still match; do NOT delete completed rows merely absent from the current export.
CREATE TABLE IF NOT EXISTS self_purchase_source_link (
 source_row INTEGER PRIMARY KEY CHECK(source_row>=2),
 marketplace TEXT NOT NULL, store TEXT NOT NULL, marketplace_sku TEXT NOT NULL,
 purchase_date TEXT NOT NULL, source_ordinal INTEGER NOT NULL,
 linked_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_self_purchase_link_listing ON self_purchase_source_link(marketplace,store,marketplace_sku);

-- Previously completed entries removed from active analytics must remain auditable.
CREATE TABLE IF NOT EXISTS self_purchase_revision (
 revision_id INTEGER PRIMARY KEY AUTOINCREMENT,
 marketplace TEXT NOT NULL, store TEXT NOT NULL, legal_entity TEXT NOT NULL,
 marketplace_sku TEXT NOT NULL, internal_article TEXT, product_name TEXT,
 quantity INTEGER NOT NULL, purchase_date TEXT NOT NULL, review_date TEXT,
 review_url TEXT, review_draft TEXT, row_hash TEXT NOT NULL,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, source_ordinal INTEGER NOT NULL,
 archived_at TEXT NOT NULL, change_reason TEXT NOT NULL,
 source_row INTEGER, sync_run_id INTEGER
);
CREATE INDEX IF NOT EXISTS ix_self_purchase_revision_listing ON self_purchase_revision(marketplace,store,marketplace_sku,purchase_date);
CREATE VIEW IF NOT EXISTS v_self_purchase_revisions AS SELECT * FROM self_purchase_revision;


-- Per-run error details are distinct from the global deduplicated sync_error audit.
-- Latest run can report exact row numbers even when a persistent error was seen before.
CREATE TABLE IF NOT EXISTS sync_run_issue (
 run_id INTEGER NOT NULL,
 source TEXT NOT NULL,
 source_row INTEGER,
 error TEXT NOT NULL,
 created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_sync_run_issue_run ON sync_run_issue(run_id,source);
