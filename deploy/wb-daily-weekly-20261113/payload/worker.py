"""Fixed read-only WB list/detail capture, durable replay and active catalog."""
import asyncio,csv,datetime,uuid,hashlib,importlib.util,io,json,os,re,signal,stat,sys,time,traceback,urllib.request,urllib.error
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import catalog
from apps.msp_marketplace_reports import quota as q
from apps.msp_marketplace_reports.providers import Request,WB_LIST,WB_DETAIL
from apps.msp_marketplace_reports.runtime import load_credentials,_headers,_NoRedirect
from recovery import Paused
ROOT=Path(__file__).resolve().parent
ARCHIVE=catalog.ARCHIVE
STOP=False
LIMIT=128*1024*1024
BUDGET=100
def checkpoint():
    if STOP:raise Paused('cooperative pause')
def stop(signum,frame):
    global STOP
    STOP=True
def strict(raw):
    def pairs(items):
        out={}
        for k,v in items:
            if k in out:raise ValueError('duplicate JSON key')
            out[k]=v
        return out
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite JSON')))
def read_job():
    p=Path(os.environ['MSP_REPORT_JOB']);s=p.lstat()
    if not stat.S_ISREG(s.st_mode) or s.st_uid!=0 or s.st_mode&0o022 or s.st_nlink!=1:raise ValueError('job trust')
    job=strict(p.read_bytes())
    if set(job)!={'cabinet','date_from','date_to','period','cycle_id','attempt','nonce','bootstrap'}:raise ValueError('job keys')
    if job['cabinet'] not in catalog.CABINETS or job['period'] not in ('daily','weekly') or type(job['attempt']) is not int or not 1<=job['attempt']<=(10 if job['period']=='weekly' else 3):raise ValueError('job scope')
    for k in ('nonce','cycle_id'):
        if not re.fullmatch('[0-9a-f]{32}',job[k]):raise ValueError('job identity')
    today=datetime.datetime.now(__import__('zoneinfo').ZoneInfo('Europe/Moscow')).date()
    if not datetime.date(2025,12,29)<=catalog.date(job['date_from'])<=catalog.date(job['date_to'])<today or type(job['bootstrap']) is not bool:raise ValueError('past-date bounds')
    if job['period']=='daily' and job['date_from']!=job['date_to']:raise ValueError('daily scope')
    if not job['bootstrap'] and len(catalog.days(job['date_from'],job['date_to']))>7:raise ValueError('weekly window')
    return job
def state_dir(job):return ARCHIVE/'wb-scheduled-capture'/job['cabinet']/job['cycle_id']/(job['period']+'-'+job['date_from']+'-'+job['date_to'])/('attempt-%02d'%job['attempt'])
def cell(v):return '' if v is None else (json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')) if isinstance(v,(bool,dict,list)) else str(v))

class Transport:
    def __init__(self,job,state):self.job=job;self.state=state;self.credential=None;self.allowed=set();self.verified_files={}
    def __call__(self,key,path,body):
        checkpoint();read_job()
        if path==WB_LIST:
            if set(body)!={'dateFrom','dateTo','period','limit','offset'} or (body['dateFrom'],body['dateTo'],body['period'],body['limit'])!=(self.job['date_from'],self.job['date_to'],self.job['period'],1000) or type(body['offset']) is not int or not 0<=body['offset']<=9000:raise ValueError('list request scope')
        elif path.startswith(WB_DETAIL):
            if path[len(WB_DETAIL):] not in self.allowed or set(body)!={'limit','rrdId'} or body['limit']!=10000 or type(body['rrdId']) is not int or body['rrdId']<0:raise ValueError('detail request scope')
        else:raise ValueError('endpoint scope')
        if not re.fullmatch('[a-z0-9-]+',key):raise ValueError('entry key')
        paths=[self.state/(key+s) for s in ('.entry.json','.response','.meta.json')]
        exists=[p.exists() or p.is_symlink() for p in paths]
        identity={'cabinet':self.job['cabinet'],'path':path,'body':body}
        if any(exists):
            if not all(exists):raise ValueError('unknown request outcome; no retry')
            entry=strict(catalog.safe(paths[0]).read_bytes());raw=catalog.safe(paths[1]).read_bytes();meta=strict(catalog.safe(paths[2]).read_bytes())
            if any(entry.get(k)!=v for k,v in identity.items()) or meta['sha256']!=catalog.digest(raw) or meta['bytes']!=len(raw) or meta['truncated']:raise ValueError('retained response conflict')
            return self.parse(meta['status'],raw)
        entries=list(self.state.glob('*.entry.json'))
        if len(entries)>=BUDGET:raise ValueError('cumulative attempt budget exhausted')
        if self.credential is None:
            creds=load_credentials(Path(os.environ['CREDENTIALS_DIRECTORY'])/'cabinets.json')
            if set(creds)!={self.job['cabinet']}:raise ValueError('credential scope')
            self.credential=creds[self.job['cabinet']]
        gate=q.SharedQuota('wb',self.credential);request=Request('wb',path,body)
        try:rules=gate.reserve(request)
        except q.QuotaBusy:raise Paused('quota not yet available before sender')
        except Exception as exc:
            if str(exc)=='API DOWNLOAD BLOCKED: shared queue reservation failed' or isinstance(exc,(ConnectionError,TimeoutError,OSError)) or type(exc).__module__.startswith('redis.'):raise Paused('quota dependency unavailable before sender')
            raise
        # A budgeted durable entry precedes construction of the actual sender.
        catalog.save(paths[0],catalog.doc(dict(identity,entry_number=len(entries)+1)))
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),_NoRedirect())
        req=urllib.request.Request('https://finance-api.wildberries.ru'+path,data=catalog.doc(body),headers=_headers('wb',self.credential),method='POST')
        try:
            with opener.open(req,timeout=60) as response:status=int(response.status);raw=response.read(LIMIT+1)
        except urllib.error.HTTPError as exc:
            status=exc.code;raw=exc.read(LIMIT+1)
            if status==429:gate.cooldown(rules,exc.headers)
        catalog.save(paths[1],raw);catalog.save(paths[2],catalog.doc({'status':status,'bytes':len(raw),'sha256':catalog.digest(raw),'truncated':len(raw)>LIMIT}))
        return self.parse(status,raw)
    def parse(self,status,raw):
        if len(raw)>LIMIT:raise ValueError('oversized response')
        if status==204:
            if raw.strip():raise ValueError('204 with unexpected content')
            return 204,None
        if status!=200:raise ValueError('HTTP is not a report-absence signal')
        value=strict(raw)
        if not isinstance(value,list) or any(not isinstance(r,dict) for r in value):raise ValueError('WB list schema')
        return status,value

def discover(job,sender):
    reports={}
    for page in range(10):
        status,rows=sender('list-%03d'%page,WB_LIST,{'dateFrom':job['date_from'],'dateTo':job['date_to'],'period':job['period'],'limit':1000,'offset':page*1000})
        if status==204:return reports
        for row in rows:
            rid=row.get('reportId');typ=row.get('reportType')
            if type(rid) is not int or rid<=0 or type(typ) is not int or typ not in (1,2):raise ValueError('report identity/BigInt')
            start=str(row.get('dateFrom',''))[:10];end=str(row.get('dateTo',''))[:10];catalog.days(start,end)
            if end<job['date_from'] or start>job['date_to'] or end>job['date_to'] or not row.get('currency') or not row.get('sellerFinanceName'):raise ValueError('foreign/unformed document')
            key=str(rid)
            if key in reports and reports[key]!=row:raise ValueError('conflicting list metadata')
            reports[key]=row
        if len(rows)<1000:return reports
    raise ValueError('discovery limit not terminal')

def capture_report(job,sender,meta,index):
    rid=str(meta['reportId']);typ=meta['reportType'];key=job['period']+'|'+str(typ)+'|'+rid
    start=str(meta['dateFrom'])[:10];end=str(meta['dateTo'])[:10];currency=meta['currency']
    prior=index['reports'].get(key)
    if prior:
        if (prior['from'],prior['to'],prior['currency'])!=(start,end,currency):raise ValueError('known document metadata drift')
        if prior['csv'] not in sender.verified_files:sender.verified_files[prior['csv']]=catalog.filehash(prior['csv'])
        if sender.verified_files[prior['csv']]!=prior['sha256']:raise ValueError('known source integrity')
        return prior
    sender.allowed.add(rid);pages=[];cursor=0;seen=set();fields={'reportId','reportType','rrdId'}
    for n in range(1,81):
        status,rows=sender('detail-'+rid+'-%03d'%n,WB_DETAIL+rid,{'limit':10000,'rrdId':cursor})
        if status==204:break
        if not rows:raise ValueError('empty 200 is not terminal detail')
        for row in rows:
            if type(row.get('reportId')) is not int or str(row['reportId'])!=rid or row.get('reportType')!=typ or type(row.get('rrdId')) is not int or row['rrdId']<=0 or row['rrdId'] in seen:raise ValueError('detail identity/duplicate')
            if (str(row.get('dateFrom',''))[:10],str(row.get('dateTo',''))[:10],row.get('currency'))!=(start,end,currency):raise ValueError('detail/list period mismatch')
            seen.add(row['rrdId']);fields.update(row)
        nxt=rows[-1]['rrdId']
        if nxt<=cursor:raise ValueError('cursor not advancing')
        cursor=nxt;pages.append(sender.state/('detail-'+rid+'-%03d.response'%n))
    else:raise ValueError('detail not terminal')
    # A listed document without detail is not used to supersede any daily data.
    if not seen:return None
    folder=catalog.root(job['cabinet'],ARCHIVE)/'documents';catalog.mkdir(folder)
    target=folder/(job['period']+'-'+str(typ)+'-'+rid+'.csv')
    headers=['reportId','rrdId','reportType']+sorted(fields-{'reportId','rrdId','reportType','_raw_json'})+['_raw_json']
    tmp=target.with_name('.'+target.name+'.'+uuid.uuid4().hex+'.partial')
    if tmp.exists():raise ValueError('incomplete CSV stage requires reconciliation')
    with tmp.open('x',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=headers,delimiter=';',lineterminator='\n');writer.writeheader()
        for p in pages:
            for row in strict(p.read_bytes()):
                value={k:cell(row.get(k)) for k in headers};value['_raw_json']=json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(',',':'));writer.writerow(value)
        f.flush();os.fchmod(f.fileno(),0o644);os.fsync(f.fileno())
    if target.exists():
        if catalog.filehash(target)!=catalog.filehash(tmp):raise ValueError('existing document conflict')
        tmp.unlink()
    else:os.rename(tmp,target)
    catalog.sync(folder)
    result={'report_id':rid,'report_type':typ,'from':start,'to':end,'currency':currency,'rows':len(seen),'period':job['period'],'csv':str(target),'sha256':catalog.filehash(target),'baseline':False}
    index['reports'][key]=result;catalog.store_index(index,ARCHIVE);return result

def execute(job,state):
    spec=importlib.util.spec_from_file_location('wb_existing_reader',ROOT/'baseline_reader.py');reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
    index=catalog.seed_baseline(job['cabinet'],reader,ARCHIVE);sender=Transport(job,state)
    reports=discover(job,sender)
    weekly={}
    for r in index['reports'].values():
        if r['period']=='weekly':weekly.setdefault((r['report_type'],r['currency']),set()).update(catalog.days(r['from'],r['to']))
    parts=[]
    for typ in (1,2):
        selected=[r for r in reports.values() if r['reportType']==typ]
        saved=[];coverage=set();all_ready=True
        for meta in selected:
            dates=catalog.days(str(meta['dateFrom'])[:10],str(meta['dateTo'])[:10])
            if job['period']=='daily' and dates<=weekly.get((typ,meta['currency']),set()):
                coverage.update(dates);continue
            retained=capture_report(job,sender,meta,index);saved.append(retained)
            if retained:coverage.update(catalog.days(retained['from'],retained['to']))
            else:all_ready=False
        if not selected and job['period']=='daily':
            # A previously verified weekly source closes its actual dates; no
            # fabricated empty daily document is created.
            coverage=set().union(*(v for (t,currency),v in weekly.items() if t==typ)) if any(t==typ for t,currency in weekly) else set()
        ready=all_ready and (bool(selected) if job['bootstrap'] else catalog.days(job['date_from'],job['date_to'])<=coverage)
        parts.append({'type':typ,'status':'VERIFIED' if ready else 'WAITING_DATA','report_ids':[str(r['reportId']) for r in selected]})
    pin=catalog.publish(index,ARCHIVE)
    # Independent reader consumes the selected effective view fully, checking all
    # source hashes/raw values/rows, with bounded row memory.
    for typ in (1,2):
        snap=catalog.snapshot(job['cabinet'],typ,None,ARCHIVE)
        for _ in catalog.iter_view(snap):pass
    return {'status':'VERIFIED' if all(p['status']=='VERIFIED' for p in parts) else 'WAITING_DATA','cabinet':job['cabinet'],'marketplace':'wb','period':job['period'],'date_from':job['date_from'],'date_to':job['date_to'],'nonce':job['nonce'],'cycle_id':job['cycle_id'],'attempt':job['attempt'],'parts':parts,'view_generation':pin['generation'],'view_sha256':pin['sha256'],'send_entries':len(list(state.glob('*.entry.json'))),'source_verified':True}

if __name__=='__main__':
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    job=read_job();state=state_dir(job)
    try:result=execute(job,state)
    except Paused:raise SystemExit(75)
    except Exception as exc:result={'status':'HOLD','cabinet':job['cabinet'],'period':job['period'],'date_from':job['date_from'],'date_to':job['date_to'],'error_type':type(exc).__name__,'frames':[{'file':Path(f.filename).name,'function':f.name,'line':f.lineno} for f in traceback.extract_tb(exc.__traceback__)[-6:]]}
    catalog.save(state/'result.json',catalog.doc(result))
