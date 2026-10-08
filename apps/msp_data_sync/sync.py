#!/usr/bin/env python3
import argparse,csv,hashlib,io,json,os,re,sqlite3,sys,urllib.error,urllib.request
from datetime import datetime,timezone
from pathlib import Path

DIGITS=re.compile(r'^[0-9]+$')

def now(): return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00','Z')
def txt(v): return '' if v is None else str(v).strip()
def mp(v):
    v=txt(v).lower(); return {'wildberries':'wb','wb':'wb','ozon':'oz','oz':'oz'}.get(v,v)
def sku(v):
    v=txt(v)
    if not DIGITS.fullmatch(v): raise ValueError(f'marketplace_sku must be digits only: {v!r}')
    return v
def dt(v):
    v=txt(v)
    if not v:return None
    for f in ('%d.%m.%Y','%d.%m.%y','%Y-%m-%d'):
        try:return datetime.strptime(v,f).date().isoformat()
        except ValueError:pass
    raise ValueError(f'bad date: {v!r}')
def qty(v):
    from decimal import Decimal
    n=Decimal(txt(v).replace(' ','').replace(',','.'))
    if not n.is_finite() or n<=0 or n!=n.to_integral_value(): raise ValueError('quantity must be a positive integer')
    return int(n)
def h(*v): return hashlib.sha256(json.dumps(v,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def hdr(v): return re.sub(r'\s+',' ',txt(v)).lower()

def dbopen(path):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(p); c.row_factory=sqlite3.Row
    c.execute('pragma foreign_keys=on'); c.execute('pragma journal_mode=wal')
    legacy=c.execute("select name from sqlite_master where type='table' and name='self_purchase'").fetchone()
    migrate=bool(legacy and 'source_ordinal' not in [r[1] for r in c.execute('pragma table_info(self_purchase)')])
    if migrate:
        c.execute('drop view if exists v_self_purchase')
        c.execute('drop index if exists ix_self_sku_date')
        c.execute('alter table self_purchase rename to self_purchase_legacy')
    schema=Path(__file__).with_name('schema.sql').read_text()
    c.executescript(schema)
    if 'planned' not in [r[1] for r in c.execute('pragma table_info(sync_run)')]:
        c.execute('alter table sync_run add column planned integer not null default 0')
    if migrate:
        c.execute('insert into self_purchase select *,1 from self_purchase_legacy')
        c.execute('drop table self_purchase_legacy')
    c.commit(); return c

def cols(header,need):
    m={hdr(v):i for i,v in enumerate(header)}; out={}
    for k,aliases in need.items():
        for a in aliases:
            if hdr(a) in m: out[k]=m[hdr(a)]; break
        if k not in out: raise ValueError(f'missing column {k}: {header!r}')
    return out
def val(r,i): return r[i] if i<len(r) else ''
def err(c,run,source,row,e,raw):
    message=str(e)[:1000]; raw_json=json.dumps(raw,ensure_ascii=False)[:10000]
    exists=c.execute(
        'select 1 from sync_error where source=? and ifnull(source_row,-1)=ifnull(?,-1) and error=? and raw_json=? limit 1',
        (source,row,message,raw_json)
    ).fetchone()
    if exists:return
    c.execute('insert into sync_error(run_id,source,source_row,error,raw_json,created_at) values(?,?,?,?,?,?)',(run,source,row,message,raw_json,now()))

def fetch(c,cfg,source):
    st=c.execute('select etag,last_modified from sync_state where source=?',(source,)).fetchone(); hd={'User-Agent':'msp-data-sync/1.0'}
    if st and st['etag']:hd['If-None-Match']=st['etag']
    if st and st['last_modified']:hd['If-Modified-Since']=st['last_modified']
    last=c.execute('select status from sync_run where source=? and run_id<(select max(run_id) from sync_run where source=?) order by run_id desc limit 1',(source,source)).fetchone()
    if last and last['status']=='partial': hd.pop('If-None-Match',None); hd.pop('If-Modified-Since',None)
    gid=cfg['sources'][source]['gid']; sid=cfg['spreadsheet_id']; url=f'https://docs.google.com/spreadsheets/d/{sid}/export?format=csv&gid={gid}'
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers=hd),timeout=30) as r:
            return r.status,r.read(20_000_000),r.headers.get('ETag'),r.headers.get('Last-Modified')
    except urllib.error.HTTPError as e:
        if e.code==304:return 304,None,None,None
        raise

def product(c,rows,run):
    m=cols(rows[0],{'marketplace':['мп'],'store':['магазин'],'sku':['market_article'],'ma':['артикул_мп'],'ia':['артикул_наш'],'ian':['артикул_наш_▼'],'name':['наименование 1с']})
    n={'source_rows':0,'inserted':0,'updated':0,'unchanged':0,'rejected':0}; t=now(); source_keys=set()
    for no,r in enumerate(rows[1:],2):
        if not any(txt(x) for x in r):continue
        n['source_rows']+=1
        try:
            x=(mp(val(r,m['marketplace'])),txt(val(r,m['store'])).lower(),sku(val(r,m['sku'])),txt(val(r,m['ma'])),txt(val(r,m['ia'])),txt(val(r,m['ian'])).lower(),txt(val(r,m['name'])))
            if x[0] not in ('wb','oz') or not x[1]:raise ValueError('invalid marketplace/store')
            if x[:3] in source_keys:raise ValueError('duplicate catalog business key')
            source_keys.add(x[:3])
            rh=h(*x); old=c.execute('select row_hash from product_listing where marketplace=? and store=? and marketplace_sku=?',x[:3]).fetchone()
            if not old:
                c.execute('insert into product_listing values(?,?,?,?,?,?,?,?,?,?,?)',(*x,rh,t,t,t)); n['inserted']+=1
            elif old['row_hash']!=rh:
                c.execute('update product_listing set marketplace_article=?,internal_article=?,internal_article_normalized=?,product_name=?,row_hash=?,last_seen_at=?,updated_at=? where marketplace=? and store=? and marketplace_sku=?',(x[3],x[4],x[5],x[6],rh,t,t,x[0],x[1],x[2])); n['updated']+=1
            else:n['unchanged']+=1
        except Exception as e:n['rejected']+=1;err(c,run,'product_catalog',no,e,r)
    return n

def store_for(c,cfg,market,legal,s):
    if legal in cfg.get('legal_entity_store_mapping',{}):return cfg['legal_entity_store_mapping'][legal].lower()
    x=[r[0] for r in c.execute('select distinct store from product_listing where marketplace=? and marketplace_sku=?',(market,s))]
    if len(x)==1:return x[0]
    raise ValueError(f'cannot derive store for {legal!r}/{s}')

def selfbuy(c,rows,run,cfg):
    # Current CSV: explicit store in "магазин". Old CSV: legacy "ЮЛ".
    m=cols(rows[0],{'marketplace':['мп'],'sku':['артикул мп'],'ia':['артикул наш'],'name':['название товара'],'q':['кол-во выкупов'],'pd':['дата выкупа'],'rd':['дата отзыва'],'url':['ссылка на отзыв'],'draft':['черновик отзывов']})
    headers={hdr(v):i for i,v in enumerate(rows[0])}
    store_col=headers.get('магазин')
    legal_col=headers.get('юл')
    if store_col is None and legal_col is None:
        raise ValueError('missing column магазин (or legacy ЮЛ)')
    n={'source_rows':0,'inserted':0,'updated':0,'unchanged':0,'rejected':0,
       'planned':0,'planned_inserted':0,'planned_updated':0,'planned_unchanged':0,'promoted':0}
    stamp=now(); seen={}; active_plan_rows=set()
    for no,r in enumerate(rows[1:],2):
        if not any(txt(x) for x in r):continue
        n['source_rows']+=1
        try:
            market=mp(val(r,m['marketplace']))
            if market not in ('wb','oz'):raise ValueError('invalid marketplace')
            raw_s=txt(val(r,m['sku']))
            purchase_date=dt(val(r,m['pd']))
            if store_col is not None:
                store=txt(val(r,store_col)).lower()
                if store not in ('laser','novok','ultra'):raise ValueError('invalid store code')
                legal=txt(val(r,legal_col)) if legal_col is not None else ''
            else:
                legal=txt(val(r,legal_col))
                store=store_for(c,cfg,market,legal,raw_s)
            internal=txt(val(r,m['ia'])); name=txt(val(r,m['name']))
            raw_qty=txt(val(r,m['q']))
            # No actual purchase date means a plan, never a completed purchase.
            if purchase_date is None:
                planned_sku=sku(raw_s) if raw_s else None
                planned_qty=qty(raw_qty) if raw_qty else None
                review_date=dt(val(r,m['rd']))
                plan=(market,store,planned_sku,internal,name,planned_qty,None,review_date,
                      txt(val(r,m['url'])),txt(val(r,m['draft'])))
                rh=h(*plan)
                old=c.execute('select row_hash,is_current from self_purchase_plan where source_row=?',(no,)).fetchone()
                if old is None:
                    c.execute('insert into self_purchase_plan(source_row,marketplace,store,marketplace_sku,internal_article,product_name,quantity,purchase_date,review_date,review_url,review_draft,row_hash,first_seen_at,updated_at,is_current,last_change_run) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?)',
                              (no,*plan,rh,stamp,stamp,run))
                    n['planned_inserted']+=1
                elif old['row_hash']!=rh or not old['is_current']:
                    c.execute('update self_purchase_plan set marketplace=?,store=?,marketplace_sku=?,internal_article=?,product_name=?,quantity=?,purchase_date=?,review_date=?,review_url=?,review_draft=?,row_hash=?,updated_at=?,is_current=1,last_change_run=? where source_row=?',
                              (*plan,rh,stamp,run,no))
                    n['planned_updated']+=1
                else:
                    n['planned_unchanged']+=1
                n['planned']+=1; active_plan_rows.add(no)
                continue
            # Completed rows require valid SKU, date and quantity plus catalog FK.
            s=sku(raw_s); amount=qty(raw_qty)
            base=(market,store,s,purchase_date)
            seen[base]=seen.get(base,0)+1
            ordinal=seen[base]; key=(*base,ordinal)
            if not c.execute('select 1 from product_listing where marketplace=? and store=? and marketplace_sku=?',(market,store,s)).fetchone():
                raise ValueError(f'sku not in product_catalog: {key}')
            x=(market,store,legal,s,internal,name,amount,purchase_date,
               dt(val(r,m['rd'])),txt(val(r,m['url'])),txt(val(r,m['draft'])))
            rh=h(*x)
            old=c.execute('select row_hash from self_purchase where marketplace=? and store=? and marketplace_sku=? and purchase_date=? and source_ordinal=?',key).fetchone()
            if old is None:
                c.execute('insert into self_purchase values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(*x,rh,stamp,stamp,ordinal))
                n['inserted']+=1
            elif old['row_hash']!=rh:
                c.execute('update self_purchase set legal_entity=?,internal_article=?,product_name=?,quantity=?,review_date=?,review_url=?,review_draft=?,row_hash=?,updated_at=? where marketplace=? and store=? and marketplace_sku=? and purchase_date=? and source_ordinal=?',
                          (legal,x[4],x[5],x[6],x[8],x[9],x[10],rh,stamp,*key))
                n['updated']+=1
            else:
                n['unchanged']+=1
            if c.execute('delete from self_purchase_plan where source_row=?',(no,)).rowcount:
                n['promoted']+=1
        except Exception as e:
            n['rejected']+=1
            err(c,run,'self_purchase',no,e,r)
    # An incomplete source row removed, completed or made invalid is not a CURRENT plan.
    # Retain old plan data for audit, but exclude it from the active-plans view.
    if active_plan_rows:
        placeholders=','.join('?' for _ in active_plan_rows)
        c.execute(f'update self_purchase_plan set is_current=0,updated_at=? where is_current=1 and source_row not in ({placeholders})',
                  (stamp,*sorted(active_plan_rows)))
    else:
        c.execute('update self_purchase_plan set is_current=0,updated_at=? where is_current=1',(stamp,))
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
        if st and st['content_sha256']==sha and not cfg.get('retry_rejected', True):
            c.execute('update sync_state set etag=?,last_modified=?,last_success_at=? where source=?',(etag,lm,now(),source));c.execute('update sync_run set finished_at=?,status=?,http_status=?,source_rows=? where run_id=?',(now(),'unchanged_snapshot',status,st['source_rows'] or 0,run));c.commit();return {'source':source,'status':'unchanged_snapshot',**n}
        rows=list(csv.reader(io.StringIO(body.decode('utf-8-sig'))))
        if not rows or not rows[0]: raise ValueError('empty or invalid CSV')
        if st and st['content_sha256']==sha and last_source_clean(c,source,run):
            c.execute('update sync_run set finished_at=?,status=?,http_status=?,source_rows=?,unchanged=? where run_id=?',(now(),'unchanged_snapshot',status,st['source_rows'],st['source_rows'],run));c.commit();return {'source':source,'status':'unchanged_snapshot',**dict(n,source_rows=st['source_rows'],unchanged=st['source_rows'])}
        c.execute('begin')
        n=product(c,rows,run) if source=='product_catalog' else selfbuy(c,rows,run,cfg) if source=='self_purchase' else prices(c,rows,run,source,cfg)
        c.execute('insert into sync_state values(?,?,?,?,?,?) on conflict(source) do update set etag=excluded.etag,last_modified=excluded.last_modified,content_sha256=excluded.content_sha256,last_success_at=excluded.last_success_at,source_rows=excluded.source_rows',(source,etag,lm,sha,now(),n['source_rows']));c.commit()
        c.execute('update sync_run set finished_at=?,status=?,http_status=?,source_rows=?,inserted=?,updated=?,unchanged=?,rejected=?,planned=? where run_id=?',(now(),'partial' if n['rejected'] else 'success',status,n['source_rows'],n['inserted'],n['updated'],n['unchanged'],n['rejected'],n.get('planned',0),run));c.commit();return {'source':source,'status':'partial' if n['rejected'] else 'success',**n}
    except Exception as e:
        c.rollback(); err(c,run,source,None,e,[]); c.execute('update sync_run set finished_at=?,status=?,message=? where run_id=?',(now(),'failed',f'{type(e).__name__}: {e}',run));c.commit();raise

def verify(c):
    return {'product_listing_count':c.execute('select count(*) from product_listing').fetchone()[0],'self_purchase_count':c.execute('select count(*) from self_purchase').fetchone()[0],'self_purchase_quantity':c.execute('select coalesce(sum(quantity),0) from self_purchase').fetchone()[0],'self_purchase_planned_count':c.execute('select count(*) from v_self_purchase_plan').fetchone()[0],'self_purchase_planned_without_sku':c.execute('select count(*) from v_self_purchase_plan where marketplace_sku is null').fetchone()[0],'self_purchase_planned_without_quantity':c.execute('select count(*) from v_self_purchase_plan where quantity is null').fetchone()[0],'foreign_key_errors':len(c.execute('pragma foreign_key_check').fetchall()),'invalid_marketplace_sku':c.execute("select count(*) from product_listing where marketplace_sku glob '*[^0-9]*' or marketplace_sku='' ").fetchone()[0],'price_segments':[dict(r) for r in c.execute('select source_segment,count(*) rows,min(event_date) min_date,max(event_date) max_date from price_event group by source_segment')],'price_history_count':c.execute('select count(*) from v_price_history').fetchone()[0],'unmatched_price_events':c.execute("select count(*) from v_price_history where catalog_match_status='unmatched'").fetchone()[0],'integrity':c.execute('pragma integrity_check').fetchone()[0],'last_runs':[dict(r) for r in c.execute('select run_id,source,status,source_rows,inserted,updated,unchanged,rejected,planned,finished_at from sync_run order by run_id desc limit 6')]}


def last_source_clean(c,source,run):
    row=c.execute('select status from sync_run where source=? and run_id<? order by run_id desc limit 1',(source,run)).fetchone()
    return bool(row and row['status'] in ('success','unchanged_snapshot','not_modified'))

def decimal_text(v):
    from decimal import Decimal, InvalidOperation
    v=txt(v).replace(' ','').replace('\u00a0','').replace(',','.')
    if not v:return None
    try:n=Decimal(v)
    except InvalidOperation:raise ValueError('invalid numeric business field')
    if not n.is_finite():raise ValueError('non-finite numeric field')
    return format(n,'f')

def prices(c,rows,run,source,cfg):
    mapping=cfg['sources'][source]['columns']; m=cols(rows[0],mapping)
    n={'source_rows':0,'inserted':0,'updated':0,'unchanged':0,'rejected':0}; seen={}; segment=cfg['sources'][source]['segment']; stamp=now()
    for no,r in enumerate(rows[1:],2):
        if not any(txt(x) for x in r):continue
        n['source_rows']+=1
        if txt(val(r,m['event_date']))=='СТРОКА ФОРМУЛ НЕ УДАЛЯТЬ':
            n['rejected']+=1;err(c,run,source,no,'technical formula row (not a business event)',r);continue
        try:
            market=mp(val(r,m['marketplace'])); store=txt(val(r,m['store'])).lower(); code=sku(val(r,m['marketplace_sku'])); day=dt(val(r,m['event_date']))
            if market not in ('wb','oz') or not store or not day:raise ValueError('invalid marketplace/store/event_date')
            base=(segment,market,store,code,day); seen[base]=seen.get(base,0)+1; ordinal=seen[base]; key=h(*base,ordinal)
            business={'new_price':decimal_text(val(r,m['new_price'])),'old_price':decimal_text(val(r,m['old_price'])),'list_price':decimal_text(val(r,m['list_price'])),'minimum_price':decimal_text(val(r,m['minimum_price'])),'discount_percent':decimal_text(val(r,m['discount_percent'])),'direction':txt(val(r,m['direction'])),'note':txt(val(r,m['note'])),'source_product_label':txt(val(r,m['source_product_label']))}
            x=(key,segment,cfg['sources'][source]['sheet'],market,store,code,day,ordinal,*business.values());rh=h(*x)
            old=c.execute('select row_hash from price_event where event_key=?',(key,)).fetchone()
            if not old:
                c.execute('insert into price_event values('+','.join('?' for _ in range(len(x)+3))+')',(*x,rh,stamp,stamp));n['inserted']+=1
            elif old['row_hash']!=rh:
                c.execute('update price_event set new_price=?,old_price=?,list_price=?,minimum_price=?,discount_percent=?,direction=?,note=?,source_product_label=?,row_hash=?,updated_at=? where event_key=?',(*business.values(),rh,stamp,key));n['updated']+=1
            else:n['unchanged']+=1
            # Unmatched historical price events are valid business history, not sync errors.
            # They remain queryable through v_price_history.catalog_match_status='unmatched'.
        except Exception as e:n['rejected']+=1;err(c,run,source,no,e,r)
    return n

def main():
    a=argparse.ArgumentParser();a.add_argument('--config',default='config/msp-data/sync.json');a.add_argument('--db');a.add_argument('--source',choices=['all','product_catalog','self_purchase','price_journal_current','price_journal_archive'],default='all');a.add_argument('--verify-only',action='store_true');x=a.parse_args()
    cfg=json.load(open(x.config,encoding='utf-8'));c=dbopen(x.db or os.getenv('MSP_DATA_DB',cfg['database_path']))
    try:
        if x.verify_only:print(json.dumps(verify(c),ensure_ascii=False,indent=2));return
        src=['product_catalog','self_purchase','price_journal_current','price_journal_archive'] if x.source=='all' else [x.source]
        results=[]
        for source in src:
            try: results.append(sync(c,cfg,source))
            except Exception as e: results.append({'source':source,'status':'failed','error':str(e)})
        print(json.dumps({'sync':results,'verify':verify(c)},ensure_ascii=False,indent=2))
        if any(r['status'] in ('partial','failed') for r in results): return 1
    finally:c.close()
if __name__=='__main__':
    try:sys.exit(main() or 0)
    except Exception as e:print(json.dumps({'status':'failed','error':f'{type(e).__name__}: {e}'},ensure_ascii=False),file=sys.stderr);raise
