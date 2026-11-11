"""Read-only source/CSV reconciliation; never invokes provider or downloader."""
from pathlib import Path
import json,csv,io,hashlib,collections
from decimal import Decimal
ROOT=Path('/opt/mcp/data/msp-marketplace-reports/ozon-accrual-month-pilot-20261111')
OUT=Path('/home/hermes/workspace/ozon-accrual-month-20261111')
sha=lambda b:hashlib.sha256(b).hexdigest()
def strict(raw):
 def pairs(items):
  out={}
  for k,v in items:
   if k in out:raise ValueError('duplicate JSON key')
   out[k]=v
  return out
 return json.loads(raw,object_pairs_hook=pairs)
coverage=strict((ROOT/'coverage.json').read_bytes())
assert coverage['cabinet']=='ozon_dmitrieva' and coverage['period']=='2026-01'
catalog={x['id']:x for x in strict((ROOT/'types.seed.json').read_bytes())['accrual_types']}
assert sha((ROOT/'types.seed.json').read_bytes())=='1d96c2089b339c9d8dbab370e671d6668cb93a2be3345ac17cde76543eab16ea'
allrows={};http=collections.Counter();cats=collections.Counter();used=collections.Counter();totals={};overlap=0
for n in range(1,32):
 day=f'2026-01-{n:02d}';summary=strict((ROOT/(day+'.summary.json')).read_bytes());seen={};cursor='';dayrows={}
 assert summary['date']==day
 for page_idx,page in enumerate(summary['pages'],1):
  assert page['page']==page_idx
  if day=='2026-01-15':
   assert page_idx==1
   raw=(ROOT/'day-first-page.seed.json').read_bytes();assert sha(raw)=='519e96177e0786d2d49f6eedc53fe0d10e0d0f7c4c90c72e9fc42a66c2ddf747'
  else:
   prefix=ROOT/day/f'{page_idx:03d}';raw=prefix.with_suffix('.response.json').read_bytes();meta=strict(prefix.with_suffix('.meta.json').read_bytes());entry=strict(prefix.with_suffix('.entry.json').read_bytes())
   assert meta['status']==200 and meta['sha256']==sha(raw) and meta['bytes']==len(raw) and not meta['truncated'];http['200']+=1
   assert entry['cabinet']=='ozon_dmitrieva' and entry['method']=='/v1/finance/accrual/by-day' and entry['body']=={'date':day,'last_id':cursor}
  assert page['sha256']==sha(raw)
  reply=strict(raw);assert type(reply['last_id']) is str
  for row in reply['accruals']:
   assert row['date']==day;key=(day,str(row['accrual_id']))
   if key in dayrows:
    assert dayrows[key]==row;overlap+=1
   else:dayrows[key]=row
  if reply['last_id']:
   assert reply['last_id'] not in seen and reply['last_id']!=cursor and page_idx<len(summary['pages'])
   seen[reply['last_id']]=True
  else:assert page_idx==len(summary['pages'])
  cursor=reply['last_id']
 assert cursor=='' and len(dayrows)==summary['rows'] and summary['status']=='CURSOR_EXHAUSTED_UNRECONCILED'
 allrows.update(dayrows)
blob=(ROOT/'month.csv').read_bytes();assert sha(blob)==coverage['csv_sha256']
csvrows={}
for view in csv.DictReader(io.StringIO(blob.decode('utf-8-sig')),delimiter=';'):
 key=(view['date'],view['accrual_id']);assert key not in csvrows
 source=strict(view['_raw_json']);csvrows[key]=source
 assert view['cabinet']=='ozon_dmitrieva' and view['accrued_category']==source['accrued_category'] and view['date']==source['date'] and view['accrual_id']==str(source['accrual_id'])
 assert view['total_amount']==source['total_amount']['amount'] and view['currency']==source['total_amount']['currency'] and view['unit_number']==source.get('unit_number','')
 cats[source['accrued_category']]+=1;money=source['total_amount'];currency=money['currency'];totals[currency]=totals.get(currency,Decimal(0))+Decimal(money['amount'])
 def walk(v):
  if isinstance(v,dict):
   if 'type_id' in v:used[v['type_id']]+=1
   for x in v.values():walk(x)
  elif isinstance(v,list):
   for x in v:walk(x)
 walk(source)
assert allrows==csvrows and len(csvrows)==coverage['rows']==728
assert dict(cats)==coverage['categories']
assert {k:str(v) for k,v in totals.items()}==coverage['net_total_amount_by_currency']
assert set(used).issubset(catalog)
assert len(list(ROOT.glob('*/*.entry.json')))==len(list(ROOT.glob('*/*.response.json')))==30
report={'status':'SOURCE_CSV_VALUES_VERIFIED_EXTERNAL_RECONCILIATION_PENDING','cabinet':'ozon_dmitrieva','period':'2026-01','days':31,'rows':len(csvrows),'categories':dict(cats),'new_http_responses_verified':dict(http),'seed_day_reused':True,'csv_sha256':sha(blob),'all_source_fields_preserved':True,'identical_overlaps':overlap,'fee_types_observed':[{'id':key,'description':catalog[key]['description'],'occurrences':n} for key,n in sorted(used.items())],'unknown_type_ids':[],'net_totals_match_source':True,'cabinet_export_reconciliation_complete':False,'provider_coverage_verified':False,'provider_requests_during_audit':0}
(OUT/'actual-month-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='fee_types_observed'},ensure_ascii=False))
