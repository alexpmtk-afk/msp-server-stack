import asyncio,hashlib,json,os,time,traceback,sys,urllib.request,urllib.error
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from apps.msp_marketplace_reports import quota as q
from apps.msp_marketplace_reports.providers import Request
from apps.msp_marketplace_reports.runtime import load_credentials,_headers,_NoRedirect
from apps.msp_marketplace_reports.shared_rate_limit import build_rules,RateRule,key_prefix
from apps.msp_marketplace_reports.ozon_accruals import inspect_page,types_catalog,strict_json
def sha(raw):
    return hashlib.sha256(raw).hexdigest()
def syncdir(path):
    fd = os.open(path, os.O_DIRECTORY | os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
def save(path, raw, mode=0o600):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            stream.write(raw)
            stream.flush()
        os.fchmod(fd, mode)
        os.fsync(fd)
    finally:
        os.close(fd)
    syncdir(path.parent)
def doc(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False) + '\n').encode()
import calendar,csv,io,re,stat
from decimal import Decimal
from apps.msp_marketplace_reports.ozon_accruals import next_request,money_leaves,digest,request_body
ROOT=Path(__file__).resolve().parent
STATE=Path('/opt/mcp/data/msp-marketplace-reports/ozon-accrual-month-pilot-20261111')
CABINET='ozon_dmitrieva'
PERIOD='2026-01'
PATH='/v1/finance/accrual/by-day'
BUDGET=128
PAGE_LIMIT=10
LIMIT=32*1024*1024
SEEDS={'types':'1d96c2089b339c9d8dbab370e671d6668cb93a2be3345ac17cde76543eab16ea','day-first-page':'519e96177e0786d2d49f6eedc53fe0d10e0d0f7c4c90c72e9fc42a66c2ddf747'}

def check_job():
    p=ROOT/'job.json';st=p.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid!=0 or st.st_mode&0o022 or st.st_nlink!=1:raise ValueError('job trust')
    job=strict_json(p.read_bytes())
    if set(job)!={'cabinet','period','max_send_entries','nonce','expires_epoch'} or job['cabinet']!=CABINET or job['period']!=PERIOD or type(job['max_send_entries']) is not int or job['max_send_entries']!=BUDGET or not re.fullmatch('[0-9a-f]{32}',job['nonce']) or not time.time()<job['expires_epoch']<=time.time()+10800:
        raise ValueError('job scope/expiry')
    return job

class MonthQuota(q.SharedQuota):
    def reserve(self,request):
        body=request.body
        if request.marketplace!='ozon' or request.path!=PATH or set(body)!={'date','last_id'} or not body['date'].startswith(PERIOD+'-') or request_body(body['date'],body['last_id'])!=body:
            raise ValueError('outside fixed January scope')
        url=self._approved_url();owner=q.stable_owner_key('ozon',self.credentials)
        rules=build_rules(service='ozon',cabinet_key=owner,host='api-seller.ozon.ru',operation_id='ozon_finance',scope='finance')
        rules.append(RateRule(key_prefix('ozon',owner)+':msp-finance-safety',60.0))
        async def work(ctl):return await ctl.try_acquire(rules)
        granted,wait=asyncio.run(q._with_controller(url,work))
        if not granted:raise q.QuotaBusy(wait)
        return rules

def seed(label):
    p=STATE/(label+'.seed.json');raw=p.read_bytes()
    if sha(raw)!=SEEDS[label]:raise ValueError('seed digest')
    return raw

def fetch_day_page(day,index,cursor,cred,*,factory=None,cursor_issued=None):
    check_job();daydir=STATE/day
    if not daydir.exists():daydir.mkdir(mode=0o755);os.chmod(daydir,0o755);syncdir(STATE)
    prefix=f'{index:03d}'
    if any((daydir/(prefix+s)).exists() for s in ('.entry.json','.response.json','.meta.json')):raise ValueError('prior entry; no automatic retry/reset')
    if len(list(STATE.glob('*/*.entry.json')))>=BUDGET:raise ValueError('cumulative month budget exhausted')
    body=request_body(day,cursor);gate=MonthQuota('ozon',cred);request=Request('ozon',PATH,body)
    for attempt in range(11):
        check_job()
        if cursor_issued is not None and time.time()-cursor_issued>=840:raise ValueError('cursor expired during quota wait; no silent restart')
        try:rules=gate.reserve(request);break
        except q.QuotaBusy as exc:
            if attempt==10:raise
            time.sleep(min(60,max(1,exc.retry_after_seconds)))
    save(daydir/(prefix+'.entry.json'),doc({'cabinet':CABINET,'method':PATH,'body':body,'send_entry_number':len(list(STATE.glob('*/*.entry.json')))+1}),0o644)
    opener=factory() if factory else urllib.request.build_opener(urllib.request.ProxyHandler({}),_NoRedirect())
    req=urllib.request.Request('https://api-seller.ozon.ru'+PATH,data=doc(body),headers=_headers('ozon',cred),method='POST')
    try:
        with opener.open(req,timeout=60) as response:status=int(response.status);raw=response.read(LIMIT+1)
    except urllib.error.HTTPError as exc:
        raw=exc.read(LIMIT+1);status=exc.code
        if status==429:gate.cooldown(rules,exc.headers)
    issued=time.time()
    save(daydir/(prefix+'.response.json'),raw,0o644)
    save(daydir/(prefix+'.meta.json'),doc({'status':status,'sha256':sha(raw),'bytes':len(raw),'truncated':len(raw)>LIMIT,'received_epoch':issued}),0o644)
    if status!=200 or len(raw)>LIMIT:raise ValueError('HTTP/size HOLD; no retry')
    return raw,issued

def collect_day(day,cred,*,fetcher=fetch_day_page,sleeper=time.sleep):
    rows=[];seen={};cursors=[];cursor='';issued=None;pages=[]
    for index in range(1,PAGE_LIMIT+1):
        if day=='2026-01-15' and index==1:
            raw=seed('day-first-page');issued=time.time();origin='verified pilot response reuse; no HTTP'
        else:
            raw,issued=fetcher(day,index,cursor,cred,cursor_issued=issued if cursor else None);origin='new retained response'
        parsed=inspect_page(raw,day,input_cursor=cursor,prior_cursors=cursors,seen=seen)
        rows.extend(parsed['rows']);seen=parsed['seen']
        pages.append({'page':index,'rows':len(parsed['rows']),'sha256':sha(raw),'origin':origin,'warnings':parsed['warnings']})
        if parsed['status']=='CURSOR_EXHAUSTED_UNRECONCILED':
            return {'date':day,'rows':rows,'pages':pages,'status':'CURSOR_EXHAUSTED_UNRECONCILED','provider_coverage_verified':False}
        if index==PAGE_LIMIT:raise ValueError('day page budget exhausted; not complete')
        body=next_request(parsed,day,age_seconds=time.time()-issued)
        cursors.append(cursor);cursor=body['last_id'];sleeper(65)
    raise ValueError('incomplete day')

def write_views(days,catalog):
    rows=[r for day in days for r in day['rows']];keys=set();fees={};unknown=set();categories={};totals={}
    fields=['cabinet','date','accrual_id','accrued_category','total_amount','currency','unit_number','_raw_json']
    text=io.StringIO(newline='');out=csv.DictWriter(text,fieldnames=fields,delimiter=';');out.writeheader()
    for row in rows:
        key=(row['date'],str(row['accrual_id']))
        if key in keys:raise ValueError('duplicate monthly row key')
        keys.add(key);categories[row.get('accrued_category')]=categories.get(row.get('accrued_category'),0)+1
        total=row.get('total_amount')
        if total is None:raise ValueError('monthly total_amount missing; retain raw, no guessed zero')
        currency=total['currency'];totals[currency]=totals.get(currency,Decimal(0))+Decimal(total['amount'])
        for leaf in money_leaves(row,catalog):
            type_id=leaf['type_id']
            if type_id is not None:fees[type_id]=fees.get(type_id,0)+1
            if not leaf['type_known']:unknown.add(type_id)
        out.writerow({'cabinet':CABINET,'date':row['date'],'accrual_id':str(row['accrual_id']),'accrued_category':row.get('accrued_category'),'total_amount':total['amount'],'currency':currency,'unit_number':row.get('unit_number',''),'_raw_json':json.dumps(row,ensure_ascii=False,sort_keys=True,allow_nan=False)})
    csvraw=text.getvalue().encode('utf-8-sig');save(STATE/'month.csv',csvraw,0o644)
    coverage={'cabinet':CABINET,'period':PERIOD,'days':[{'date':x['date'],'rows':len(x['rows']),'pages':x['pages'],'status':x['status']} for x in days],'rows':len(rows),'csv_sha256':sha(csvraw),'categories':categories,'unknown_type_ids':sorted(unknown),'observed_fee_type_ids':sorted(fees),'net_total_amount_by_currency':{k:str(v) for k,v in totals.items()},'status':'MONTH_COLLECTED_NOT_RECONCILED','provider_coverage_verified':False,'cabinet_export_reconciliation_complete':False}
    save(STATE/'coverage.json',doc(coverage),0o644)
    # Net totals stay in financial archive, not the public progress receipt.
    return {k:v for k,v in coverage.items() if k not in ('days','net_total_amount_by_currency','observed_fee_type_ids')}

def execute():
    job=check_job();catalog=types_catalog(strict_json(seed('types')))
    inspect_page(seed('day-first-page'),'2026-01-15')
    credentials=load_credentials(Path(os.environ['CREDENTIALS_DIRECTORY'])/'cabinets.json')
    if set(credentials)!={CABINET}:raise ValueError('credential cabinet mismatch')
    days=[]
    for n in range(1,32):
        day=f'{PERIOD}-{n:02d}';result=collect_day(day,credentials[CABINET]);days.append(result)
        save(STATE/(day+'.summary.json'),doc({'date':day,'rows':len(result['rows']),'pages':result['pages'],'status':result['status'],'provider_coverage_verified':False}),0o644)
        if n<31:time.sleep(65)
    result=write_views(days,catalog)
    return {**result,'days_collected':len(days),'max_send_entries':BUDGET,'send_entries':len(list(STATE.glob('*/*.entry.json'))),'seed_day_reused':True,'nonce':job['nonce'],'full_month_complete':False}

if __name__=='__main__':
    try:result=execute()
    except Exception as exc:
        result={'status':'HOLD','period':PERIOD,'error_type':type(exc).__name__,'frames':[{'file':Path(f.filename).name,'function':f.name,'line':f.lineno} for f in traceback.extract_tb(exc.__traceback__)[-6:]],'send_entries':len(list(STATE.glob('*/*.entry.json'))),'days_collected':len(list(STATE.glob('*.summary.json'))),'provider_coverage_verified':False}
    save(STATE/'worker-result.json',doc(result),0o644)
