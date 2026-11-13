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
ROOT=Path(__file__).resolve().parent
STATE=Path('/opt/mcp/data/msp-marketplace-reports/ozon-accrual-pilot-20261111')
CABINET='ozon_dmitrieva'
DAY='2026-01-15'
CALLS=(('/v1/finance/accrual/types',{},'types'),('/v1/finance/accrual/by-day',{'date':DAY,'last_id':''},'day-first-page'))
LIMIT=32*1024*1024

class CaptureQuota(q.SharedQuota):
    def reserve(self,request):
        if request.marketplace!='ozon' or (request.path,request.body) not in [(p,b) for p,b,_ in CALLS]:
            raise ValueError('outside fixed two-call capture')
        url=self._approved_url();owner=q.stable_owner_key('ozon',self.credentials)
        rules=build_rules(service='ozon',cabinet_key=owner,host='api-seller.ozon.ru',operation_id='ozon_finance',scope='finance')
        rules.append(RateRule(key_prefix('ozon',owner)+':msp-finance-safety',60.0))
        async def work(ctl):return await ctl.try_acquire(rules)
        granted,wait=asyncio.run(q._with_controller(url,work))
        if not granted:raise q.QuotaBusy(wait)
        return rules

def check_job():
    import stat,re
    p=ROOT/'job.json';st=p.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid!=0 or st.st_mode&0o022 or st.st_nlink!=1:raise ValueError('job trust')
    job=strict_json(p.read_bytes())
    if set(job)!={'cabinet','date','max_send_entries','nonce','expires_epoch'} or job['cabinet']!=CABINET or job['date']!=DAY or type(job['max_send_entries']) is not int or job['max_send_entries']!=2 or not re.fullmatch('[0-9a-f]{32}',job['nonce']) or not time.time()<job['expires_epoch']<=time.time()+600:
        raise ValueError('job scope/expiry')
    return job

def capture_one(index,path,body,label,cred,*,factory=None):
    base=STATE/label
    # No overwrite, no retry, no implicit adoption of an old sender entry.
    if any((STATE/(label+suffix)).exists() for suffix in ('.entry.json','.response.json','.meta.json')):
        raise ValueError('existing attempt requires reconciliation')
    gate=CaptureQuota('ozon',cred);request=Request('ozon',path,body)
    rules=gate.reserve(request)
    save(STATE/(label+'.entry.json'),doc({'index':index,'cabinet':CABINET,'path':path,'body':body}),0o644)
    opener=factory() if factory else urllib.request.build_opener(urllib.request.ProxyHandler({}),_NoRedirect())
    req=urllib.request.Request('https://api-seller.ozon.ru'+path,data=doc(body),headers=_headers('ozon',cred),method='POST')
    try:
        with opener.open(req,timeout=60) as response:
            status=int(response.status);raw=response.read(LIMIT+1)
    except urllib.error.HTTPError as exc:
        raw=exc.read(LIMIT+1);status=exc.code
        if status==429:gate.cooldown(rules,exc.headers)
    # Durable raw response BEFORE JSON or business validation, including HTTP errors.
    save(STATE/(label+'.response.json'),raw,0o644)
    save(STATE/(label+'.meta.json'),doc({'status':status,'sha256':sha(raw),'bytes':len(raw),'truncated':len(raw)>LIMIT}),0o644)
    if status!=200 or len(raw)>LIMIT:raise ValueError('HTTP or size HOLD; no retry')
    return raw

def execute():
    job=check_job()
    credentials=load_credentials(Path(os.environ['CREDENTIALS_DIRECTORY'])/'cabinets.json')
    if set(credentials)!={CABINET}:raise ValueError('credential cabinet mismatch')
    results=[];catalog=None
    for index,(path,body,label) in enumerate(CALLS,1):
        check_job()
        raw=capture_one(index,path,body,label,credentials[CABINET])
        if label=='types':
            catalog=types_catalog(strict_json(raw));results.append({'label':label,'types':len(catalog),'response_sha256':sha(raw)})
        else:
            page=inspect_page(raw,DAY)
            rows=page['rows'];cats={}
            for row in rows:cats[row.get('accrued_category','MISSING')]=cats.get(row.get('accrued_category','MISSING'),0)+1
            results.append({'label':label,'rows':len(rows),'categories':cats,'next_page_required':bool(page['last_id']),'response_sha256':sha(raw),'warnings':page['warnings']})
        if index<2:time.sleep(65) # Same existing shared quota plus conservative local pacing.
    return {'status':'CAPTURED_NOT_RECONCILED','cabinet':CABINET,'date':DAY,'calls':results,'max_send_entries':2,'provider_coverage_verified':False,'full_day_complete':False,'full_month_complete':False,'nonce':job['nonce']}

if __name__=='__main__':
    try:result=execute()
    except Exception as exc:
        result={'status':'HOLD','error_type':type(exc).__name__,'frames':[{'file':Path(f.filename).name,'function':f.name,'line':f.lineno} for f in traceback.extract_tb(exc.__traceback__)[-6:]],'entry_files':len(list(STATE.glob('*.entry.json'))),'response_files':len(list(STATE.glob('*.response.json'))),'provider_coverage_verified':False}
    save(STATE/'worker-result.json',doc(result),0o644)
