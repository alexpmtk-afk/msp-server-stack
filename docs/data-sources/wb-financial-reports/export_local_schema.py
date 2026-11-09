"""Fixed root-only local CSV schema audit. No HTTP, tokens, data or mode changes."""
import collections,csv,datetime,fcntl,hashlib,io,json,os,re,stat,sys,uuid
from decimal import Decimal,InvalidOperation
from pathlib import Path
ARCHIVE=Path('/opt/mcp/data/msp-marketplace-reports')
CONTROL=Path('/var/lib/msp-finance-control')
CABINETS=('wb_laser_master','wb_novokshenov','wb_dmitrieva')
DATASETS=('wb_weekly_finance_main','wb_weekly_finance_buyout')
RESULT='wb-local-columns-20261109.json'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def strict(pairs):
 d={}
 for k,v in pairs:
  if k in d:raise ValueError('duplicate JSON key')
  d[k]=v
 return d
def json_bytes(raw):return json.loads(raw,object_pairs_hook=strict,parse_float=Decimal)
def plain(path,*,owners=(0,995),directory=False):
 for p in [path,*path.parents]:
  st=p.lstat()
  if stat.S_ISLNK(st.st_mode) or st.st_uid not in owners or st.st_mode&0o022:raise ValueError('unsafe path')
 st=path.lstat()
 if directory:
  if not stat.S_ISDIR(st.st_mode):raise ValueError('directory required')
 elif not stat.S_ISREG(st.st_mode) or st.st_nlink!=1:raise ValueError('regular file required')
def read(path,limit=2*1024*1024):
 plain(path)
 with path.open('rb') as f:raw=f.read(limit+1)
 if len(raw)>limit:raise ValueError('oversized metadata')
 return raw
def file_digest(path):
 plain(path);h=hashlib.sha256();size=0
 with path.open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block);size+=len(block)
 return h.hexdigest(),size
def cell(x):
 if x is None:return ''
 if isinstance(x,(dict,list)):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
 return str(x)
def keynorm(k):return re.sub('[^a-z0-9]','',k.lower())
def profile_csv(path,*,expected_rows,report_type=None):
 """Public output is names/types/counts only; never row values or amounts."""
 counts={};types=collections.defaultdict(collections.Counter);categories=collections.defaultdict(collections.Counter);bad=collections.Counter();names=set();n=0;seen=set()
 checks={'item_payout':{'tested':0,'nonzero_tested':0,'matches_within_0_02':0},'kvv_final':{'tested':0,'nonzero_tested':0,'matches_within_0_000001':0}}
 allowed_categories={'doctype','doctypename','supplieropername'}
 with path.open(encoding='utf-8-sig',newline='') as stream:
  reader=csv.reader(stream,delimiter=';');header=next(reader)
  if len(header)!=len(set(header)) or not {'reportId','reportType','rrdId','_raw_json'}<=set(header):raise ValueError('header mismatch')
  counts={k:{'nonblank':0,'blank':0} for k in header}
  indexes={k:i for i,k in enumerate(header)}
  raw_index=header.index('_raw_json');id_index=[header.index(k) for k in ('reportId','rrdId')]
  normalized={}
  for k in header:
   norm=keynorm(k)
   normalized.setdefault(norm,[]).append(k)
  for row in reader:
   if len(row)!=len(header):raise ValueError('row width mismatch')
   n+=1;ident=tuple(row[i] for i in id_index)
   if report_type is not None and row[indexes['reportType']]!=str(report_type):raise ValueError('report type mismatch')
   if not all(ident) or ident in seen:raise ValueError('duplicate/empty identity')
   seen.add(ident)
   obj=json.loads(row[raw_index],object_pairs_hook=strict)
   if type(obj) is not dict:raise ValueError('raw JSON must be object')
   for k,v in zip(header,row):counts[k]['nonblank' if v!='' else 'blank']+=1
   for k,v in obj.items():
    names.add(k);types[k][type(v).__name__]+=1
    if k not in counts:bad[k]+=1
    elif cell(v)!=row[indexes[k]]:bad[k]+=1
    if keynorm(k) in allowed_categories and isinstance(v,str):
     if len(v)>180 or (v not in categories[k] and len(categories[k])>=128):raise ValueError('unexpected categorical scope')
     categories[k][v]+=1
   # Diagnostic arithmetic, not an assertion that every version uses this formula.
   def dec(norm):
    keys=normalized.get(norm,[])
    if len(keys)!=1:raise ValueError()
    key=keys[0]
    if row[indexes[key]]=='':raise ValueError()
    x=Decimal(row[indexes[key]])
    if not x.is_finite():raise ValueError()
    return x
   try:
    price=dec('retailpricewithdisc');rate=dec('commissionpercent');fee=dec('acquiringfee');paid=dec('ppvzforpay');check=checks['item_payout'];check['tested']+=1
    if price or fee or paid:check['nonzero_tested']+=1
    if abs(price*(1-rate/100)-fee-paid)<=Decimal('0.02'):check['matches_within_0_02']+=1
   except (InvalidOperation,ValueError):pass
   try:
    base=dec('ppvzkvwprcbase');discount=dec('ppvzsppprc');final=dec('ppvzkvwprc');check=checks['kvv_final'];check['tested']+=1
    if base or discount or final:check['nonzero_tested']+=1
    if abs(base-discount-final)<=Decimal('0.000001'):check['matches_within_0_000001']+=1
   except (InvalidOperation,ValueError):pass
 if n!=expected_rows:raise ValueError('row total mismatch')
 if bad:raise ValueError('CSV/raw JSON disagreement')
 return {'rows':n,'headers':header,'column_presence':counts,'raw_json_keys':sorted(names),'raw_types':{k:dict(v) for k,v in types.items()},'operation_categories':{k:dict(v) for k,v in categories.items()},'formula_diagnostics':checks,'normalized_name_collisions':{k:v for k,v in normalized.items() if len(v)>1},'raw_json_matches_csv':True}
def audit_scope(root,dataset,cabinet,year):
 scope=root/'.b7-generations'/dataset/cabinet/str(year);plain(scope,directory=True)
 pointer_raw=read(scope/'CURRENT.json');ptr=json_bytes(pointer_raw)
 if type(ptr.get('schema')) is not int or ptr['schema']!=2 or not re.fullmatch('[a-f0-9]{32}',ptr.get('generation','')):raise ValueError('invalid CURRENT')
 gen=scope/'generations'/ptr['generation'];descriptor_raw=read(gen/'generation.json');desc=json_bytes(descriptor_raw)
 if sha(descriptor_raw)!=ptr.get('sha256') or desc.get('schema')!=2 or desc.get('generation')!=ptr['generation'] or desc.get('scope')!=str(year):raise ValueError('descriptor mismatch')
 entries={}
 for item in desc['files']:
  if item['path'] not in ('data.csv','data.csv.meta.json') or item['path'] in entries:raise ValueError('invalid file entry')
  entries[item['path']]=item
 if set(entries)!={'data.csv','data.csv.meta.json'}:raise ValueError('file pair required')
 for name,item in entries.items():
  digest,size=file_digest(gen/name)
  if digest!=item['sha256'] or type(item['bytes']) is not int or size!=item['bytes']:raise ValueError('file checksum mismatch')
 meta=json_bytes(read(gen/'data.csv.meta.json'))
 if type(meta.get('schema')) is not int or meta.get('schema')!=1 or any(meta.get(k)!=v for k,v in {'dataset':dataset,'cabinet':cabinet,'period':str(year),'status':'LOCAL_VERIFIED','sha256':entries['data.csv']['sha256'],'bytes':entries['data.csv']['bytes']}.items()) or type(meta.get('rows')) is not int:raise ValueError('CSV manifest mismatch')
 prof=profile_csv(gen/'data.csv',expected_rows=meta['rows'],report_type=1 if dataset.endswith('_main') else 2)
 if read(scope/'CURRENT.json')!=pointer_raw or file_digest(gen/'data.csv')[0]!=entries['data.csv']['sha256']:raise ValueError('snapshot changed during audit')
 return {'dataset':dataset,'cabinet':cabinet,'year':year,'generation':ptr['generation'],'manifest_sha256':ptr['sha256'],'csv_sha256':entries['data.csv']['sha256'],**prof}
def publish(folder,value):
 plain(folder,owners=(0,),directory=True);target=folder/RESULT
 if target.exists():plain(target,owners=(0,))
 raw=(json.dumps(value,ensure_ascii=False,sort_keys=True)+'\n').encode();temp=folder/('.wb-columns-'+uuid.uuid4().hex)
 fd=os.open(temp,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
 try:
  with os.fdopen(fd,'wb',closefd=False) as f:f.write(raw);f.flush();os.fchmod(fd,0o644);os.fsync(fd)
 finally:os.close(fd)
 os.replace(temp,target);fd=os.open(folder,os.O_RDONLY|os.O_DIRECTORY)
 try:os.fsync(fd)
 finally:os.close(fd)
def main():
 if os.geteuid()!=0 or sys.argv[1:]:raise ValueError('root-owned snapshot, no arguments required')
 plain(Path(__file__),owners=(0,));plain(CONTROL/'controller.lock',owners=(0,))
 # Block network and child process creation even if this helper is later extended.
 def guard(event,args):
  if event.startswith('socket.') or event in ('subprocess.Popen','os.system'):raise RuntimeError('network/processes forbidden')
 sys.addaudithook(guard)
 csv.field_size_limit(16*1024*1024)
 lock=os.open(CONTROL/'controller.lock',os.O_RDONLY|os.O_NOFOLLOW)
 try:
  fcntl.flock(lock,fcntl.LOCK_SH|fcntl.LOCK_NB)
  scopes=[]
  for cabinet in CABINETS:
   for dataset in DATASETS:
    p=ARCHIVE/'.b7-generations'/dataset/cabinet/'2026'
    if not p.exists():scopes.append({'cabinet':cabinet,'dataset':dataset,'year':2026,'status':'ABSENT'});continue
    scopes.append({'status':'VERIFIED_LOCAL_SCHEMA',**audit_scope(ARCHIVE,dataset,cabinet,2026)})
  value={'schema':1,'status':'READ_ONLY_SCHEMA_AUDIT','checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'archive_root':str(ARCHIVE),'scopes':scopes,'provider_calls':0,'archive_writes':0,'raw_rows_exported':0,'credentials_read':False}
  publish(CONTROL/'results',value);print(json.dumps({'status':'READ_ONLY_SCHEMA_AUDIT','receipt':str(CONTROL/'results'/RESULT),'scopes':len(scopes),'provider_calls':0,'archive_writes':0}))
 finally:os.close(lock)
if __name__=='__main__':
 try:main()
 except Exception as exc:print(json.dumps({'status':'HOLD','error_type':type(exc).__name__,'provider_calls':0,'archive_writes':0}));raise SystemExit(1)
