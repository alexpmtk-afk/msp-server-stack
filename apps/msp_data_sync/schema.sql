
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
    create table if not exists sync_run(run_id integer primary key autoincrement,source text,started_at text,finished_at text,status text,http_status integer,source_rows integer default 0,inserted integer default 0,updated integer default 0,unchanged integer default 0,rejected integer default 0,message text);
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
