"""Two source tabs, one complaint population. No writes to Google or marketplaces."""
import argparse
from collections import Counter,defaultdict
from datetime import datetime,timezone
import fcntl
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import urllib.parse

SHEET='1YMvYrVoPkMv5N1ig7tDaBz10_Epxpkglrkc2V4q-KDE'
TABS={'main':('Таблица по бракам',0),'laser':('Таблица по бракам для Лазер',1442102002)}
HEADERS={
    'main':['ГЗП в 2026','МП и Юр.Лицо','Производство','','Артикул','Наименование товара','Дата','Номер заказ','Жалоба покупателя','Категория жалобы','Источник обращения','Статус','Дата статуса','Комментарий статуса'],
    'laser':['ГЗП в 2026','Артикул','Наименование товара','Дата','Жалоба покупателя','Статус','Комментарий Статуса']}
DEFAULT_ROOT=Path('/opt/mcp/data/msp/defects-feedback')
def encode(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def now():return datetime.now(timezone.utc).isoformat()
def digest(x):return sha256(encode(x).encode()).hexdigest()
def atomic(path,data):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temp=path.with_suffix(path.suffix+'.new');temp.write_text(encode(data));temp.chmod(0o600)
    with temp.open('rb') as f:os.fsync(f.fileno())
    os.replace(temp,path)
    fd=os.open(path.parent,os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)

def date_value(raw,issues,code):
    if not raw.strip():return None
    for fmt in ('%d.%m.%Y','%d.%m.%y','%d.%m.%Y %H:%M','%d.%m.%Y %H:%M:%S','%Y-%m-%d'):
        try:return datetime.strptime(raw.strip(),fmt).date().isoformat()
        except ValueError:pass
    issues.append(code);return None

def parse_rows(kind,rows):
    if not rows:raise ValueError('MISSING_HEADER')
    header=[str(x).strip() for x in rows[0]]
    expected=HEADERS[kind]
    if header[:len(expected)]!=expected:raise ValueError('HEADER_MISMATCH_'+kind)
    result=[]
    for number,raw in enumerate(rows[1:],2):
        values=[str(x) for x in raw];v=values+['']*max(0,len(expected)-len(values))
        # Formula-only A and auxiliary AD do not create complaints.
        relevant=v[1:14] if kind=='main' else v[1:7]
        if not any(x.strip() for x in relevant):continue
        article_column=4 if kind=='main' else 1
        if v[article_column].strip()=='0' and not any(v[i].strip() for i in range(1,len(expected)) if i!=article_column):continue
        main=kind=='main';issues=[]
        article=v[4 if main else 1];date_raw=v[6 if main else 3]
        complaint=v[8 if main else 4];status=v[11 if main else 5]
        if not article.strip():issues.append('MISSING_ARTICLE')
        if not complaint.strip():issues.append('MISSING_COMPLAINT')
        received=date_value(date_raw,issues,'INVALID_DATE')
        if not date_raw.strip():issues.append('MISSING_DATE')
        status_date=v[12] if main else ''
        record={'source':kind,'source_row':number,'internal_article_raw':article,
            'internal_article_key':article.strip().casefold(),'product_name':v[5 if main else 2],
            'received_date_raw':date_raw,'received_date':received,'complaint':complaint,
            'marketplace_cabinet_raw':v[1] if main else None,
            'production_raw':v[2] if main else None,'order_number_raw':v[7] if main else None,
            'category_raw':v[9] if main else None,'contact_source_raw':v[10] if main else None,
            'status_raw':status,'status_date_raw':status_date,
            'status_date':date_value(status_date,issues,'INVALID_STATUS_DATE'),
            'status_comment_raw':v[13 if main else 6],
            'production_year_marker_raw':v[0],'production_year_marker_year':2026,
            'marker_semantics':'PRODUCTION_ORDER_SUBMITTED_NOT_COMPLETED_PRODUCTION',
            'issues':issues,'raw_cells':values}
        result.append(record)
    return result

def match_key(r):
    if not r['internal_article_key'] or not r['received_date'] or not r['complaint'].strip():return None
    return r['internal_article_key'],r['received_date'],r['complaint']

def link_rows(main,laser):
    candidates=defaultdict(list);counts=Counter(match_key(r) for r in main)
    for r in laser:
        key=match_key(r)
        if key:candidates[key].append(r)
    links=[]
    for r in main:
        key=match_key(r);matches=candidates.get(key,[])
        state='NOT_APPLICABLE';chosen=None
        if r['production_raw'].strip() in ('Лазер','АНТ'):
            state='NO_MATCH'
            if key and (counts[key]>1 or len(matches)>1):state='AMBIGUOUS'
            elif len(matches)==1:state='EXACT_MATCH';chosen=matches[0]
        status=r['status_raw'];comment=r['status_comment_raw']
        if state in ('AMBIGUOUS','NO_MATCH'):
            status=None;comment=None
        if chosen:
            if (r['status_raw'].strip() and chosen['status_raw'].strip() and r['status_raw'].strip()!=chosen['status_raw'].strip()) or (r['status_comment_raw'].strip() and chosen['status_comment_raw'].strip() and r['status_comment_raw']!=chosen['status_comment_raw']):
                state='STATUS_CONFLICT';status=None;comment=None
            else:status=chosen['status_raw'];comment=chosen['status_comment_raw']
        links.append({'main_row':r['source_row'],'laser_row':chosen['source_row'] if chosen else None,
            'state':state,'effective_status':status,'effective_comment':comment})
    return links

SCHEMA='''
CREATE TABLE IF NOT EXISTS defects_run(id INTEGER PRIMARY KEY,started_at TEXT NOT NULL,finished_at TEXT,status TEXT NOT NULL,snapshot_sha TEXT NOT NULL,stats_json TEXT);
CREATE TABLE IF NOT EXISTS defects_source_row(source TEXT NOT NULL,source_row INTEGER NOT NULL,record_json TEXT NOT NULL,row_sha TEXT NOT NULL,is_current INTEGER NOT NULL,last_seen_run INTEGER NOT NULL,PRIMARY KEY(source,source_row));
CREATE TABLE IF NOT EXISTS defects_row_revision(id INTEGER PRIMARY KEY,run_id INTEGER NOT NULL,source TEXT NOT NULL,source_row INTEGER NOT NULL,operation TEXT NOT NULL,old_record_json TEXT,new_record_json TEXT);
CREATE TABLE IF NOT EXISTS defects_link(main_row INTEGER PRIMARY KEY,laser_row INTEGER,state TEXT NOT NULL,effective_status TEXT,effective_comment TEXT);
CREATE VIEW IF NOT EXISTS defects_current AS SELECT r.source_row,json_extract(r.record_json,'$.internal_article_raw') internal_article,json_extract(r.record_json,'$.internal_article_key') internal_article_key,json_extract(r.record_json,'$.marketplace_cabinet_raw') marketplace_cabinet,json_extract(r.record_json,'$.received_date') received_date,json_extract(r.record_json,'$.complaint') complaint,json_extract(r.record_json,'$.category_raw') category,l.effective_status,l.effective_comment,l.state link_state,r.record_json FROM defects_source_row r LEFT JOIN defects_link l ON l.main_row=r.source_row WHERE r.source='main' AND r.is_current=1;
'''

def store_snapshot(db,records,snapshot_sha):
    db=Path(db);db.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    con=sqlite3.connect(db);con.executescript(SCHEMA)
    stats={'inserted':0,'changed':0,'unchanged':0,'retired':0}
    try:
        with con:
            run=con.execute('insert into defects_run(started_at,status,snapshot_sha) values(?,?,?)',(now(),'running',snapshot_sha)).lastrowid
            for source,rows in records.items():
                for r in rows:
                    payload=encode(r);hash_=digest(r);key=(source,r['source_row'])
                    old=con.execute('select record_json,row_sha,is_current from defects_source_row where source=? and source_row=?',key).fetchone()
                    if old is None:operation='inserted'
                    elif old[1]!=hash_ or not old[2]:operation='changed'
                    else:operation='unchanged'
                    stats[operation]+=1
                    if operation!='unchanged':con.execute('insert into defects_row_revision(run_id,source,source_row,operation,old_record_json,new_record_json) values(?,?,?,?,?,?)',(run,*key,operation,old[0] if old else None,payload))
                    con.execute('insert into defects_source_row values(?,?,?,?,1,?) on conflict(source,source_row) do update set record_json=excluded.record_json,row_sha=excluded.row_sha,is_current=1,last_seen_run=excluded.last_seen_run',(*key,payload,hash_,run))
                stale=con.execute('select source_row,record_json from defects_source_row where source=? and is_current=1 and last_seen_run<>?',(source,run)).fetchall()
                for n,old in stale:
                    con.execute('insert into defects_row_revision(run_id,source,source_row,operation,old_record_json) values(?,?,?,?,?)',(run,source,n,'retired',old));stats['retired']+=1
                con.execute('update defects_source_row set is_current=0 where source=? and last_seen_run<>?',(source,run))
            links=link_rows(records['main'],records['laser'])
            con.execute('delete from defects_link')
            con.executemany('insert into defects_link values(?,?,?,?,?)',[(x['main_row'],x['laser_row'],x['state'],x['effective_status'],x['effective_comment']) for x in links])
            stats.update(main_rows=len(records['main']),laser_rows=len(records['laser']),link_states=dict(Counter(x['state'] for x in links)),source_issue_rows=sum(bool(r['issues']) for rows in records.values() for r in rows))
            con.execute('update defects_run set finished_at=?,status=?,stats_json=? where id=?',(now(),'success',encode(stats),run))
        return {**stats,'run_id':run,'snapshot_sha':snapshot_sha}
    finally:con.close();db.chmod(0o600)

def fetch():
    spec=importlib.util.spec_from_file_location('msp_drive_auth','/home/hermes/.hermes/google-drive/drive_audit.py')
    auth=importlib.util.module_from_spec(spec);spec.loader.exec_module(auth)
    headers={'Authorization':'Bearer '+auth.auth()}
    base='https://sheets.googleapis.com/v4/spreadsheets/'+SHEET
    def get(params,path=''):return auth.call(base+path+'?'+urllib.parse.urlencode(params,doseq=True),headers=headers)
    meta=get({'fields':'spreadsheetId,properties(title),sheets(properties(sheetId,title,gridProperties))'})
    selected={}
    for source,(title,gid) in TABS.items():
        props=next((s['properties'] for s in meta['sheets'] if s['properties']['title']==title and s['properties']['sheetId']==gid),None)
        if not props:raise ValueError('TAB_IDENTITY_MISMATCH')
        grid=props['gridProperties'];nr,nc=grid['rowCount'],grid['columnCount']
        if nr>20000 or nc>52:raise ValueError('GRID_TOO_LARGE')
        letters='';n=nc
        while n:n,k=divmod(n-1,26);letters=chr(65+k)+letters
        rg="'"+title+"'!A1:"+letters+str(nr)
        raw=get({'ranges':rg,'includeGridData':'true','fields':'sheets(properties(sheetId,title),data(startRow,startColumn,rowData(values(formattedValue,userEnteredValue,dataValidation))))'})
        data=raw['sheets'][0]['data'][0]
        if data.get('startRow',0)!=0 or data.get('startColumn',0)!=0:raise ValueError('GRID_OFFSET')
        rows=[[v.get('formattedValue','') for v in row.get('values',[])] for row in data.get('rowData',[])]
        separate=get({'valueRenderOption':'FORMATTED_VALUE'},'/values/'+urllib.parse.quote(rg,safe='')).get('values',[])
        def trim(rs):
            out=[]
            for row in rs:
                row=list(row)
                while row and row[-1]=='':row.pop()
                out.append(row)
            while out and not out[-1]:out.pop()
            return out
        if trim(rows)!=trim(separate):raise ValueError('SOURCE_CHANGED_DURING_READ')
        selected[source]={'title':title,'gid':gid,'rows':rows,'grid':raw,'bounds':grid}
    return {'spreadsheet_id':SHEET,'sources':selected}

def verify(root):
    root=Path(root);receipt=json.loads((root/'last-success.json').read_text())
    snapshot=json.loads((root/'snapshots'/ (receipt['snapshot_sha']+'.json')).read_text())
    assert digest(snapshot)==receipt['snapshot_sha']
    records={s:parse_rows(s,x['rows']) for s,x in snapshot['sources'].items()}
    with sqlite3.connect((root/'catalog.sqlite3').resolve().as_uri()+'?mode=ro',uri=True) as c:
        assert c.execute('pragma integrity_check').fetchone()[0]=='ok'
        for source,rows in records.items():
            got=c.execute('select source_row,record_json from defects_source_row where source=? and is_current=1 order by source_row',(source,)).fetchall()
            assert got==[(r['source_row'],encode(r)) for r in rows]
        got=c.execute('select main_row,laser_row,state,effective_status,effective_comment from defects_link order by main_row').fetchall()
        assert got==[(r['main_row'],r['laser_row'],r['state'],r['effective_status'],r['effective_comment']) for r in link_rows(records['main'],records['laser'])]
    return {'verified':True,**receipt}

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['sync','verify','query']);p.add_argument('--root',type=Path,default=DEFAULT_ROOT);p.add_argument('--article');p.add_argument('--from',dest='start');p.add_argument('--to',dest='end');a=p.parse_args()
    if a.action=='verify':print(encode(verify(a.root)));return
    if a.action=='query':
        if not a.article:p.error('--article is required; use internal article, not marketplace SKU')
        with sqlite3.connect((a.root/'catalog.sqlite3').resolve().as_uri()+'?mode=ro',uri=True) as c:
            c.row_factory=sqlite3.Row
            sql='select * from defects_current where internal_article_key=?';args=[a.article.strip().casefold()]
            if a.start:sql+=' and received_date>=?';args.append(a.start)
            if a.end:sql+=' and received_date<=?';args.append(a.end)
            rows=[dict(r) for r in c.execute(sql+' order by received_date,source_row',args)]
        print(encode({'internal_article':a.article,'complaint_count':len(rows),'records':rows}));return
    a.root.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (a.root/'sync.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            snapshot=fetch();records={s:parse_rows(s,x['rows']) for s,x in snapshot['sources'].items()}
            if len(records['main'])<100 or len(records['laser'])<50:raise ValueError('SUSPICIOUSLY_SHORT_SOURCE')
            db=a.root/'catalog.sqlite3'
            if db.exists():
                with sqlite3.connect(db.resolve().as_uri()+'?mode=ro',uri=True) as c:
                    for s,new in records.items():
                        old=c.execute('select count(*) from defects_source_row where source=? and is_current=1',(s,)).fetchone()[0]
                        if len(new)<old*0.8:raise ValueError('SHARP_SOURCE_SHRINK_REQUIRES_REVIEW')
            hash_=digest(snapshot);atomic(a.root/'snapshots'/(hash_+'.json'),snapshot)
            result=store_snapshot(db,records,hash_);result['finished_at']=now()
            atomic(a.root/'last-success.json',result)
            verify(a.root);atomic(a.root/'last-attempt.json',{'status':'verified',**result});print(encode(result))
        except (Exception,SystemExit) as exc:
            atomic(a.root/'last-attempt.json',{'status':'failed','error_class':type(exc).__name__,'finished_at':now()})
            print('Загрузка не выполнена; предыдущие данные сохранены.',flush=True)
            raise SystemExit(1) from None

if __name__=='__main__':main()
