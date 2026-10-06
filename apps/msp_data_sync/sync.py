#!/usr/bin/env python3
import argparse,csv,hashlib,io,json,os,re,sqlite3,sys,urllib.error,urllib.request
from datetime import datetime,timezone
from pathlib import Path

DIGITS=re.compile(r'^\d+$')

def now(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')
def txt(v): return '' if v is None else str(v).strip()
def mp(v):
    v=txt(v).lower(); return {'wildberries':'wb','wb':'wb','ozon':'oz','oz':'oz'}.get(v,v)
def sku(v):
    v=txt(v); v=v[:-2] if v.endswith('.0') and v[:-2].isdigit() else v
    if not DIGITS.fullmatch(v): raise ValueError(f'marketplace_sku must be digits only: {v!r}')
    return v
def dt(v):
    v=txt(v)
    if not v:return None
    for f in ('%d.%m.%Y','%d.%m.%y','%Y-%m-%d'):
        try:return datetime.strptime(v,f).date().isoformat()
        except ValueError:pass
    raise ValueError(f'bad date: {v!r}')
def qty(v): return int(txt(v).replace(' ','').replace(',0','').replace('.0',''))
def h(*v): return hashlib.sha256(json.dumps(v,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def hdr(v): return re.sub(r'\s+',' ',txt(v)).lower()

def dbopen(path):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(p); c.row_factory=sqlite3.Row
    c.execute('pragma foreign_keys=on'); c.execute('pragma journal_mode=wal')
    c.executescript('''
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
      primary key(marketplace,store,marketplace_sku,purchase_date),
      foreign key(marketplace,store,marketplace_sku) references product_listing(marketplace,store,marketplace_sku));
    create index if not exists ix_self_sku_date on self_purchase(marketplace_sku,purchase_date);
    create table if not exists sync_state(source text primary key,etag text,last_modified text,content_sha256 text,last_success_at text,source_rows integer);
    create table if not exists sync_run(run_id integer primary key autoincrement,source text,started_at text,finished_at text,status text,http_status integer,source_rows integer default 0,inserted integer default 0,updated integer default 0,unchanged integer default 0,rejected integer default 0,message text);
    create table if not exists sync_error(error_id integer primary key autoincrement,run_id integer,source text,source_row integer,error text,raw_json text,created_at text);
    create view if not exists v_product_catalog as select marketplace,store,marketplace_sku,marketplace_article,internal_article,internal_article_normalized,product_name from product_listing;
    create view if not exists v_self_purchase as select s.marketplace,s.store,s.legal_entity,s.marketplace_sku,coalesce(nullif(s.internal_article,''),p.internal_article) internal_article,coalesce(nullif(s.product_name,''),p.product_name) product_name,s.quantity,s.purchase_date,s.review_date,s.review_url,s.review_draft from self_purchase s left join product_listing p using(marketplace,store,marketplace_sku);
    '''); c.commit(); return c

def cols(header,need):
    m={hdr(v):i for i,v in enumerate(header)}; out={}
    for k,aliases in need.items():
        for a in aliases:
            if hdr(a) in m: out[k]=m[hdr(a)]; break
        if k not in out: raise ValueError(f'missing column {k}: {header!r}')
    return out
def val(r,i): return r[i] if i<len(r) else ''
def err(c,run,source,row,e,raw): c.execute('insert into sync_error(run_id,source,source_row,error,raw_json,created_at) values(?,?,?,?,?,?)',(run,source,row,str(e)[:1000],json.dumps(raw,ensure_ascii=False)[:10000],now()))

def fetch(c,cfg,source):
    st=c.execute('select etag,last_modified from sync_state where source=?',(source,)).fetchone(); hd={'User-Agent':'msp-data-sync/1.0'}
    if st and st['etag']:hd['If-None-Match']=st['etag']
    if st and st['last_modified']:hd['If-Modified-Since']=st['last_modified']
    gid=cfg['sources'][source]['gid']; sid=cfg['spreadsheet_id']; url=f'https://docs.google.com/spreadsheets/d/{sid}/export?format=csv&gid={gid}'
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers=hd),timeout=30) as r:
            return r.status,r.read(20_000_000),r.headers.get('ETag'),r.headers.get('Last-Modified')
    except urllib.error.HTTPError as e:
        if e.code==304:return 304,None,None,None
        raise

def product(c,rows,run):
    m=cols(rows[0],{'marketplace':['мп'],'store':['магазин'],'sku':['market_article'],'ma':['артикул_мп'],'ia':['артикул_наш'],'ian':['артикул_наш_▼'],'name':['наименование 1с']})
    n={'source_rows':0,'inserted':0,'updated':0,'unchanged':0,'rejected':0}; t=now()
    for no,r in enumerate(rows[1:],2):
        if not any(txt(x) for x in r):continue
        n['source_rows']+=1
        try:
            x=(mp(val(r,m['marketplace'])),txt(val(r,m['store'])).lower(),sku(val(r,m['sku'])),txt(val(r,m['ma'])),txt(val(r,m['ia'])),txt(val(r,m['ian'])).lower(),txt(val(r,m['name'])))
            if not x[0] or not x[1]:raise ValueError('marketplace/store empty')
            rh=h(*x); old=c.execute('select row_hash from product_listing where marketplace=? and store=? and marketplace_sku=?',x[:3]).fetchone()
            if not old:
                c.execute('insert into product_listing values(?,?,?,?,?,?,?,?,?,?,?)',(*x,rh,t,t,t)); n['inserted']+=1
            elif old['row_hash']!=rh:
                c.execute('update product_listing set marketplace_article=?,internal_article=?,internal_article_normalized=?,product_name=?,row_hash=?,last_seen_at=?,updated_at=? where marketplace=? and store=? and marketplace_sku=?',(x[3],x[4],x[5],x[6],rh,t,t,x[0],x[1],x[2])); n['updated']+=1
            else:
                c.execute('update product_listing set last_seen_at=? where marketplace=? and store=? and marketplace_sku=?',(t,*x[:3])); n['unchanged']+=1
        except Exception as e:n['rejected']+=1;err(c,run,'product_catalog',no,e,r)
    return n

def store_for(c,cfg,market,legal,s):
    if legal in cfg.get('legal_entity_store_mapping',{}):return cfg['legal_entity_store_mapping'][legal].lower()
    x=[r[0] for r in c.execute('select distinct store from product_listing where marketplace=? and marketplace_sku=?',(market,s))]
    if len(x)==1:return x[0]
    raise ValueError(f'cannot derive store for {legal!r}/{s}')

def selfbuy(c,rows,run,cfg):
    m=cols(rows[0],{'marketplace':['мп'],'legal':['юл'],'sku':['артикул мп'],'ia':['артикул наш'],'name':['название товара'],'q':['кол-во выкупов'],'pd':['дата выкупа'],'rd':['дата отзыва'],'url':['ссылка на отзыв'],'draft':['черновик отзывов']})
    n={'source_rows':0,'inserted':0,'updated':0,'unchanged':0,'rejected':0}; t=now(); seen=set()
    for no,r in enumerate(rows[1:],2):
        if not any(txt(x) for x in r):continue
        n['source_rows']+=1
        try:
            market=mp(val(r,m['marketplace'])); legal=txt(val(r,m['legal'])); s=sku(val(r,m['sku'])); pd=dt(val(r,m['pd'])); st=store_for(c,cfg,market,legal,s)
            if not pd:raise ValueError('purchase_date empty')
            key=(market,st,s,pd)
            if key in seen:raise ValueError(f'duplicate source key {key}')
            seen.add(key)
            if not c.execute('select 1 from product_listing where marketplace=? and store=? and marketplace_sku=?',(market,st,s)).fetchone():raise ValueError(f'sku not in product_catalog: {key}')
            x=(market,st,legal,s,txt(val(r,m['ia'])),txt(val(r,m['name'])),qty(val(r,m['q'])),pd,dt(val(r,m['rd'])),txt(val(r,m['url'])),txt(val(r,m['draft'])))
            rh=h(*x); old=c.execute('select row_hash from self_purchase where marketplace=? and store=? and marketplace_sku=? and purchase_date=?',key).fetchone()
            if not old:
                c.execute('insert into self_purchase values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(*x,rh,t,t)); n['inserted']+=1
            elif old['row_hash']!=rh:
                c.execute('update self_purchase set legal_entity=?,internal_article=?,product_name=?,quantity=?,review_date=?,review_url=?,review_draft=?,row_hash=?,updated_at=? where marketplace=? and store=? and marketplace_sku=? and purchase_date=?',(legal,x[4],x[5],x[6],x[8],x[9],x[10],rh,t,*key)); n['updated']+=1
            else:n['unchanged']+=1
        except Exception as e:n['rejected']+=1;err(c,run,'self_purchase',no,e,r)
    return n

def begin_run(c,source):
    r=c.execute('insert into sync_run(source,started_at,status) values(?,?,?)',(source,now(),'running')).lastrowid; c.commit(); return r

def sync(c,cfg,source):
    run=begin_run(c,source)
    n={'source_rows':0,'inserted':0,'updated':0,'unchanged':0,'rejected':0}
    try:
        status,body,etag,lm=fetch(c,cfg,source)
        if status==304:
            c.execute('update sync_run set finished_at=?,status=?,http_status=? where run_id=?',(now(),'not_modified',304,run));c.commit();return {'source':source,'status':'not_modified',**n}
        sha=hashlib.sha256(body).hexdigest(); st=c.execute('select content_sha256,source_rows from sync_state where source=?',(source,)).fetchone()
        if st and st['content_sha256']==sha:
            c.execute('update sync_state set etag=?,last_modified=?,last_success_at=? where source=?',(etag,lm,now(),source));c.execute('update sync_run set finished_at=?,status=?,http_status=?,source_rows=? where run_id=?',(now(),'unchanged_snapshot',status,st['source_rows'] or 0,run));c.commit();return {'source':source,'status':'unchanged_snapshot',**n}
        rows=list(csv.reader(io.StringIO(body.decode('utf-8-sig')))); c.execute('begin')
        n=product(c,rows,run) if source=='product_catalog' else selfbuy(c,rows,run,cfg)
        if n['rejected']:raise RuntimeError(f'{n["rejected"]} rejected source rows')
        c.execute('insert into sync_state values(?,?,?,?,?,?) on conflict(source) do update set etag=excluded.etag,last_modified=excluded.last_modified,content_sha256=excluded.content_sha256,last_success_at=excluded.last_success_at,source_rows=excluded.source_rows',(source,etag,lm,sha,now(),n['source_rows']));c.commit()
        c.execute('update sync_run set finished_at=?,status=?,http_status=?,source_rows=?,inserted=?,updated=?,unchanged=?,rejected=? where run_id=?',(now(),'success',status,n['source_rows'],n['inserted'],n['updated'],n['unchanged'],n['rejected'],run));c.commit();return {'source':source,'status':'success',**n}
    except Exception as e:
        c.rollback(); c.execute('update sync_run set finished_at=?,status=?,message=? where run_id=?',(now(),'failed',f'{type(e).__name__}: {e}',run));c.commit();raise

def verify(c):
    return {'product_listing_count':c.execute('select count(*) from product_listing').fetchone()[0],'self_purchase_count':c.execute('select count(*) from self_purchase').fetchone()[0],'self_purchase_quantity':c.execute('select coalesce(sum(quantity),0) from self_purchase').fetchone()[0],'foreign_key_errors':len(c.execute('pragma foreign_key_check').fetchall()),'invalid_marketplace_sku':c.execute("select count(*) from product_listing where marketplace_sku glob '*[^0-9]*' or marketplace_sku='' ").fetchone()[0],'last_runs':[dict(r) for r in c.execute('select run_id,source,status,source_rows,inserted,updated,unchanged,rejected,finished_at from sync_run order by run_id desc limit 6')]}

def main():
    a=argparse.ArgumentParser();a.add_argument('--config',default='config/msp-data/sync.json');a.add_argument('--db');a.add_argument('--source',choices=['all','product_catalog','self_purchase'],default='all');a.add_argument('--verify-only',action='store_true');x=a.parse_args()
    cfg=json.load(open(x.config,encoding='utf-8'));c=dbopen(x.db or os.getenv('MSP_DATA_DB',cfg['database_path']))
    try:
        if x.verify_only:print(json.dumps(verify(c),ensure_ascii=False,indent=2));return
        src=['product_catalog','self_purchase'] if x.source=='all' else [x.source]
        print(json.dumps({'sync':[sync(c,cfg,s) for s in src],'verify':verify(c)},ensure_ascii=False,indent=2))
    finally:c.close()
if __name__=='__main__':
    try:main()
    except Exception as e:print(json.dumps({'status':'failed','error':f'{type(e).__name__}: {e}'},ensure_ascii=False),file=sys.stderr);raise
