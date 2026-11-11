from pathlib import Path
import sys,json,hashlib,csv,io,os
from datetime import datetime,timezone
ARCHIVE=Path('/opt/mcp/data/msp-marketplace-reports')
BASE=Path(__file__).parent
sys.path.insert(0,'/opt/mcp/projects/msp-server-stack/docs/data-sources/wb-financial-reports')
import local_reports as wb
progress=json.loads(Path('/var/lib/msp-finance-control/results/ozon-history-2026.json').read_bytes())
release=Path(progress['root_release'])
assert release.stat().st_uid==0 and not release.stat().st_mode&0o022
sys.path.insert(0,str(release))
from apps.msp_marketplace_reports.generation_store import read_active
from apps.msp_marketplace_reports.versioned_archive import read_csv_versioned

def csv_rows(raw):
 return list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig')),delimiter=';'))
def index(rows):
 result={}
 for r in rows:
  k=tuple(r[f] for f in ('report_year','report_month','row_number'))
  assert k not in result
  result[k]=r
 return result

audit={'verified_at':datetime.now(timezone.utc).isoformat(),'uid':os.geteuid(),'provider_calls':0,'source_writes':0,'sample_period':'2026-10-01/2026-10-31','wb':[],'ozon':[]}
for cabinet in ('wb_dmitrieva','wb_laser_master','wb_novokshenov'):
 result={'cabinet':cabinet,'status':'READ_VERIFIED','datasets':[],'october_rows':0}
 for typ in (1,2):
  snap=wb.resolve(cabinet,typ)
  count=selected=0;dates=[];sample_keys=None;columns=None;sample_found=False
  for row in wb.iter_rows(snap):
   count+=1
   value=row.get('rrDate','')[:10]
   if value:dates.append(value)
   if '2026-10-01'<=value<='2026-10-31':
    selected+=1
    if not sample_found:
     sample_found=True;sample_keys={'reportId':row['reportId'],'rrdId':row['rrdId'],'nmId':row.get('nmId'),'rrDate':row.get('rrDate')};columns=sorted(row)
  assert sample_found
  result['october_rows']+=selected
  result['datasets'].append({'type':typ,'rows_read_to_end':count,'october_rows':selected,'date_min':min(dates),'date_max':max(dates),'column_count':len(columns),'sample':sample_keys,'generation':snap['generation'],'sha256':snap['sha256']})
 audit['wb'].append(result)
for cabinet in ('ozon_dmitrieva','ozon_laser_master','ozon_novokshenov'):
 active=read_active(ARCHIVE,'ozon_final_realization',cabinet,'2026')
 annual_rows=csv_rows(active['files']['annual.csv']);annual=index(annual_rows)
 combined={};month_receipts=[];sample=None
 for month in range(1,11):
  period=f'2026-{month:02d}'
  report=next(x for x in progress['reports'] if x['cabinet']==cabinet and x['period']==period)
  assert report['status']=='COMPLETE' and report['provider_http_status']==200
  state=ARCHIVE/'ozon-final-2026'/cabinet/period
  raw=(state/'response.json').read_bytes();stage=(state/'report.csv').read_bytes()
  assert hashlib.sha256(raw).hexdigest()==report['response_sha256']
  assert hashlib.sha256(stage).hexdigest()==report['csv_sha256']
  source=json.loads(raw);header=source['header'];rows=csv_rows(active['files']['monthly/'+period+'.csv']);staged=csv_rows(stage)
  assert header['start_date']==period+'-01' and header['stop_date'][:7]==period
  assert len(rows)==len(source['rows'])==report['rows']
  assert index(rows)==index(staged)
  for row in rows:
   original=json.loads(row['_raw_json'])
   assert original['report_year']==2026 and original['report_month']==period
   for key,value in original.items():
    expected=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')) if isinstance(value,(dict,list)) else ('' if value is None else str(value))
    assert row[key]==expected
  indexed=index(rows);assert not(set(combined)&set(indexed));combined.update(indexed)
  pinned,receipt=read_csv_versioned(ARCHIVE,'ozon_final_realization',cabinet,period,pinned_generation=report['generation'],expected_digest=report['published_manifest_sha256'])
  assert index(csv_rows(pinned))==indexed and receipt['sha256']==report['published_sha256']
  month_receipts.append({'period':period,'rows':len(rows),'raw_hash_verified':True,'published_values_verified':True})
  if month==10:sample={'period':period,'rows':len(rows),'receiver_name':header['receiver_name'],'currency':header['currency_sys_name'],'columns':sorted(rows[0]),'nested_source_fields':sorted(source['rows'][0])}
 assert annual==combined
 audit['ozon'].append({'cabinet':cabinet,'status':'READ_VERIFIED','annual_rows':len(annual),'months':month_receipts,'sample':sample,'generation':active['generation'],'manifest_sha256':active['manifest_sha256']})
assert len(audit['wb'])==len(audit['ozon'])==3
(BASE/'result.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
for r in audit['wb']:print('WB',r['cabinet'],'October',r['october_rows'],'annual_rows',sum(d['rows_read_to_end'] for d in r['datasets']))
for r in audit['ozon']:print('OZON',r['cabinet'],'October',r['sample']['rows'],'annual_rows',r['annual_rows'],'months',len(r['months']))
print('SIX_CABINETS_READ_VERIFIED; all30 Ozon months independently reconciled; no API requests')
