"""Independent source/page/CSV/publication verifier, no API or state rewrites."""
from pathlib import Path
import sys,json,csv,io,hashlib,calendar,stat
sys.path.insert(0,str(Path(__file__).resolve().parent))
from apps.msp_marketplace_reports.versioned_archive import read_csv_versioned
from decimal import Decimal
ARCHIVE=Path('/opt/mcp/data/msp-marketplace-reports')
HISTORY=ARCHIVE/'ozon-dmitrieva-accruals-2026'
PUBLIC=Path('/var/lib/msp-finance-control/results/ozon-dmitrieva-accruals-2026.json')
CABINET='ozon_dmitrieva'
JAN_SHA='7089e1dca18b155e8f9e5e4155d8bbd9c86849f18e391cab1db6f2c6ae42d68e'
sha=lambda b:hashlib.sha256(b).hexdigest()

def read(path):
    st=path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_nlink!=1 or st.st_uid not in (0,995) or st.st_mode&0o022:raise ValueError('source inode trust')
    return path.read_bytes()

def objects(raw):
    out={}
    for row in csv.DictReader(io.StringIO(raw.decode('utf-8-sig')),delimiter=';'):
        key=(row['date'],row['accrual_id'])
        if key in out or row['cabinet']!=CABINET:raise ValueError('row identity')
        out[key]=row
    return out

def verify_months(doc,*,check_inodes=True):
    read_bytes=read if check_inodes else lambda p:p.read_bytes()
    if doc.get('cabinet')!=CABINET or (doc.get('from_month'),doc.get('to_month'))!=(1,10):raise ValueError('year scope')
    months=doc['months']
    if len(months)!=10 or [x['period'] for x in months]!=[f'2026-{m:02d}' for m in range(1,11)]:raise ValueError('missing/duplicate month')
    allrows={};daycount=0;sendcount=0
    for m,result in enumerate(months,1):
        period=f'2026-{m:02d}';state=HISTORY/period;raw=read_bytes(state/'month.csv');rows=objects(raw)
        if any(not day.startswith(period+'-') for day,_ in rows):raise ValueError('foreign row date')
        if m==1:
            if sha(raw)!=JAN_SHA or len(rows)!=728 or result['send_entries']!=0:raise ValueError('accepted January drift')
        else:
            cover=json.loads(read_bytes(state/'coverage.json'));days=cover['days'];expected=[f'{period}-{n:02d}' for n in range(1,calendar.monthrange(2026,m)[1]+1)]
            if [x['date'] for x in days]!=expected:raise ValueError('day coverage')
            source={}
            for day in days:
                cursor='';seen_cursors=set();day_source={}
                if not day['pages']:raise ValueError('no day response')
                for idx,page in enumerate(day['pages'],1):
                    stem=state/day['date']/f'{idx:03d}'
                    b=read_bytes(stem.with_suffix('.response.json'));meta=json.loads(read_bytes(stem.with_suffix('.meta.json')));entry=json.loads(read_bytes(stem.with_suffix('.entry.json')))
                    if meta['status']!=200 or meta['sha256']!=sha(b) or meta['bytes']!=len(b) or meta['truncated'] or page['sha256']!=sha(b):raise ValueError('raw response integrity')
                    if entry['cabinet']!=CABINET or entry['method']!='/v1/finance/accrual/by-day' or entry['body']!={'date':day['date'],'last_id':cursor}:raise ValueError('sender scope')
                    reply=json.loads(b)
                    if type(reply['last_id']) is not str:raise ValueError('missing cursor')
                    for row in reply['accruals']:
                        key=(row['date'],str(row['accrual_id']))
                        if row['date']!=day['date'] or (key in day_source and day_source[key]!=row):raise ValueError('foreign/conflicting row')
                        day_source[key]=row
                    cursor=reply['last_id']
                    if cursor:
                        if cursor in seen_cursors or idx==len(day['pages']):raise ValueError('cursor cycle/truncated day')
                        seen_cursors.add(cursor)
                    elif idx!=len(day['pages']):raise ValueError('pages after cursor exhaustion')
                    sendcount+=1
                if cursor or len(day_source)!=day['rows']:raise ValueError('day row count')
                source.update(day_source)
            if source!={key:json.loads(row['_raw_json']) for key,row in rows.items()}:raise ValueError('source values lost or changed')
            totals={}
            for row in source.values():
                money=row['total_amount'];curr=money['currency'];totals[curr]=totals.get(curr,Decimal(0))+Decimal(money['amount'])
            if {k:str(v) for k,v in totals.items()}!=cover['net_total_amount_by_currency'] or sha(raw)!=cover['csv_sha256']:raise ValueError('month totals/hash')
            entries=list(state.glob('*/*.entry.json'))
            if len(entries)!=result['send_entries'] or not 0<len(entries)<=128:raise ValueError('budget mismatch')
        published,pinned=read_csv_versioned(ARCHIVE,'ozon_financial_accruals',CABINET,period,pinned_generation=result['generation'],expected_digest=result['manifest_sha256'])
        if objects(published)!=rows or pinned['sha256']!=result['published_sha256']:raise ValueError('published values mismatch')
        if result['rows']!=len(rows) or result['days_collected']!=calendar.monthrange(2026,m)[1]:raise ValueError('receipt row/day count')
        if set(allrows)&set(rows):raise ValueError('year duplicate')
        allrows.update(rows);daycount+=result['days_collected']
    if daycount!=304 or sendcount>1152:raise ValueError('calendar/cumulative budget')
    return {'verified_days':daycount,'verified_rows':len(allrows),'verified_new_send_entries':sendcount,'all_monthly_source_and_published_values_match':True,'january_external_reconciliation_complete':True,'later_months_external_reconciliation_complete':False}

def main():
    doc=json.loads(read(PUBLIC))
    if doc['status']!='SOURCE_COLLECTION_COMPLETE' or doc.get('activation_policy_removed') is not True or doc.get('temporary_activation_removed') is not True:raise ValueError('collection/cleanup not terminal')
    result=verify_months(doc)
    import subprocess
    p=subprocess.run(['/usr/bin/systemctl','show','msp-wb-pilot.service','-p','ActiveState','-p','PrivateNetwork','-p','DropInPaths'],capture_output=True,text=True,check=True)
    unit=dict(line.split('=',1) for line in p.stdout.splitlines() if '=' in line)
    if unit['ActiveState'] not in ('inactive','failed') or unit['PrivateNetwork']!='yes' or unit['DropInPaths']:raise ValueError('worker isolation not restored')
    print(json.dumps({'verification':'PASS',**result}))
if __name__=='__main__':main()
