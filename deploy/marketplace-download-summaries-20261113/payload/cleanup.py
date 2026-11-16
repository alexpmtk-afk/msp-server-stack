"""Remove superseded daily CSVs from working catalog, retain immutable audit gzip."""
import gzip,json,os
from pathlib import Path
import catalog
def prune(index,archive=catalog.ARCHIVE):
 cabinet=index['cabinet'];base=catalog.root(cabinet,archive)
 active,old=catalog.active_reports(index)
 if not old:return {'status':'VERIFIED','superseded_daily_reports':[],'source_journals_deleted':False}
 # Completion acknowledgement is real: consume all currently selected sources.
 for typ in (1,2):
  for _ in catalog.iter_view(catalog.snapshot(cabinet,typ,None,archive,allow_empty=True)):pass
 live={r['csv'] for r in active};changed=False;removed=[]
 for row in old:
  src=Path(row['csv']);expected=base/'documents'/('daily-'+str(row['report_type'])+'-'+row['report_id']+'.csv')
  if src!=expected or row.get('baseline') is not False or row['csv'] in live:raise ValueError('daily cleanup scope conflict')
  folder=Path(archive)/'wb-daily-audit';catalog.mkdir(folder);folder=folder/cabinet;catalog.mkdir(folder)
  packed=folder/(src.name+'.'+row['sha256']+'.gz');tombstone=folder/(src.name+'.'+row['sha256']+'.json')
  if src.exists():
   raw=catalog.safe(src).read_bytes()
   if catalog.digest(raw)!=row['sha256']:raise ValueError('daily bytes changed before cleanup')
   if packed.exists():
    if gzip.decompress(catalog.safe(packed).read_bytes())!=raw:raise ValueError('audit copy conflict')
   else:catalog.save(packed,gzip.compress(raw,mtime=0))
   if catalog.digest(gzip.decompress(catalog.safe(packed).read_bytes()))!=row['sha256']:raise ValueError('audit acknowledgement failed')
  else:
   if not packed.exists() or catalog.digest(gzip.decompress(catalog.safe(packed).read_bytes()))!=row['sha256']:raise ValueError('daily source missing without audit')
  proof=[{'report_id':r['report_id'],'sha256':r['sha256'],'from':r['from'],'to':r['to']} for r in active if r['period']=='weekly' and r['report_type']==row['report_type'] and r['currency']==row['currency'] and catalog.days(r['from'],r['to'])&catalog.days(row['from'],row['to'])]
  mark=dict(schema=1,source=row['csv'],sha256=row['sha256'],rows=row['rows'],report_id=row['report_id'],report_type=row['report_type'],currency=row['currency'],archive=str(packed),replaced_by=proof,reason='VERIFIED_EQUIVALENT_WEEKLY_COVERAGE')
  if tombstone.exists():
   prior=json.loads(catalog.safe(tombstone).read_bytes())
   if any(prior.get(k)!=mark[k] for k in ('source','sha256','rows','archive','report_id','report_type','currency')):raise ValueError('tombstone conflict')
  else:catalog.save(tombstone,catalog.doc(mark))
  if src.exists():
   if catalog.filehash(src)!=row['sha256']:raise ValueError('daily changed after acknowledgement')
   src.unlink();catalog.sync(src.parent)
  cleanup=dict(status='REMOVED_FROM_WORKING_CATALOG',archive=str(packed),tombstone=str(tombstone),sha256=row['sha256'])
  if row.get('cleanup')!=cleanup:row['cleanup']=cleanup;changed=True
  removed.append(row['report_id'])
 if changed:catalog.store_index(index,archive)
 return {'status':'VERIFIED','superseded_daily_reports':removed,'source_journals_deleted':False}
