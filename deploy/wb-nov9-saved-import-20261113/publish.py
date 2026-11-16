"""One saved full-detail document into the normal WB catalog, no transport."""
import csv,hashlib,io,json,os,sys
from pathlib import Path
CAB='wb_novokshenov'
RID=str(json.loads((Path(__file__).resolve().parent/'baseline.json').read_text())['report_id'])
DAY='2026-11-09'
KEY='daily|1|'+RID
def digest(raw):return hashlib.sha256(raw).hexdigest()
def select(capture):
 if capture['status']!=200 or capture['request_cursor']!=0 or not isinstance(capture['rows'],list):raise ValueError('capture envelope')
 rows=[r for r in capture['rows'] if str(r.get('reportId'))==RID]
 if len(rows)!=92:raise ValueError('exact document count')
 seen=set()
 for r in rows:
  if type(r['reportId']) is not int or type(r['reportType']) is not int or r['reportType']!=1 or r['dateFrom'][:10]!=DAY or r['dateTo'][:10]!=DAY or r['currency']!='RUB' or type(r['rrdId']) is not int or r['rrdId']<=0 or r['rrdId'] in seen:raise ValueError('document scope/duplicate')
  seen.add(r['rrdId'])
 return rows
def csv_bytes(rows):
 headers=['reportId','rrdId','reportType']+sorted(set().union(*(r.keys() for r in rows))-{'reportId','rrdId','reportType','_raw_json'})+['_raw_json']
 def cell(v):return '' if v is None else (json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')) if isinstance(v,(bool,dict,list)) else str(v))
 out=io.StringIO(newline='');w=csv.DictWriter(out,fieldnames=headers,delimiter=';',lineterminator='\n');w.writeheader()
 for r in rows:
  values={k:cell(r.get(k)) for k in headers};values['_raw_json']=json.dumps(r,ensure_ascii=False,sort_keys=True,separators=(',',':'));w.writerow(values)
 return ('\ufeff'+out.getvalue()).encode('utf-8')
def publish(rows,catalog,archive,capture_hash):
 root=catalog.root(CAB,archive);index=catalog.load_index(CAB,archive)
 if index.get('cabinet')!=CAB or index.get('baseline_seeded') is not True:raise ValueError('known seeded cabinet required')
 # Validate all currently selected financial rows before changing the index.
 for typ in (1,2):
  for _ in catalog.iter_view(catalog.snapshot(CAB,typ,None,archive,allow_empty=True)):pass
 target=root/'documents'/('daily-1-'+RID+'.csv');raw=csv_bytes(rows)
 if target.exists():
  if catalog.filehash(target)!=digest(raw):raise ValueError('existing source conflict')
 else:
  if KEY not in index['reports']:
   coverage=set()
   for r in index['reports'].values():
    if r['period']=='weekly' and r['report_type']==1 and r['currency']=='RUB':coverage.update(catalog.days(r['from'],r['to']))
   if DAY in coverage:raise ValueError('already covered by weekly; reconcile without import')
  catalog.save(target,raw)
 entry=dict(report_id=RID,report_type=1,period='daily',currency='RUB',rows=len(rows),csv=str(target),sha256=digest(raw),baseline=False,source_method='SAVED_FULL_PERIOD_DETAIL',source_capture_sha256=capture_hash,summary_header_available=False)
 entry.update({'from':DAY,'to':DAY})
 if KEY in index['reports'] and index['reports'][KEY]!=entry:raise ValueError('existing document metadata conflict')
 index['reports'][KEY]=entry;catalog.store_index(index,archive);pin=catalog.publish(index,archive)
 selected=[]
 for typ in (1,2):
  for row in catalog.iter_view(catalog.snapshot(CAB,typ,None,archive,allow_empty=True)):
   if row['reportId']==RID:selected.append(json.loads(row['_raw_json']))
 if {str(r['rrdId']):r for r in selected}!={str(r['rrdId']):r for r in rows}:raise ValueError('published source differs')
 return dict(status='SOURCE_PUBLISHED',cabinet=CAB,report_id=RID,date=DAY,rows=len(rows),view_generation=pin['generation'],view_sha256=pin['sha256'],csv_sha256=digest(raw),source_method='SAVED_FULL_PERIOD_DETAIL',summary_header_available=False)
if __name__=='__main__':
 if os.geteuid()!=995:raise PermissionError('accepted archive writer only')
 import importlib.util
 stage=Path(__file__).resolve().parent;cfg=json.loads((stage/'baseline.json').read_text());p=Path(cfg['release'])/'catalog.py'
 spec=importlib.util.spec_from_file_location('accepted_catalog',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 rows=json.loads((stage/'selected-rows.json').read_text())
 if select({'status':200,'request_cursor':0,'rows':rows})!=rows:raise ValueError('staged document')
 result=publish(rows,m,m.ARCHIVE,cfg['capture_sha256']);print(json.dumps(result))
