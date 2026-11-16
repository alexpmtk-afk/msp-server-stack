"""Streaming, immutable WB effective view: weekly replaces covered daily sources.

No provider calls. Source rows are not edited, copied into history twice, or
physically deleted. Only the atomically selected active-source manifest changes.
"""
import csv,datetime,hashlib,json,os,stat,uuid
from pathlib import Path

CABINETS=('wb_dmitrieva','wb_laser_master','wb_novokshenov')
ARCHIVE=Path('/opt/mcp/data/msp-marketplace-reports')
def digest(raw):return hashlib.sha256(raw).hexdigest()
def doc(value):return (json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n').encode()
def sync(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)
def save(path,raw,mode=0o644):
    path=Path(path);tmp=path.with_name('.'+path.name+'.'+uuid.uuid4().hex+'.partial')
    fd=os.open(tmp,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,mode)
    try:
        with os.fdopen(fd,'wb',closefd=False) as out:out.write(raw);out.flush()
        os.fchmod(fd,mode);os.fsync(fd)
    finally:os.close(fd)
    os.replace(tmp,path);sync(path.parent)
def mkdir(path):
    if not path.exists():path.mkdir(mode=0o755);os.chmod(path,0o755);sync(path.parent)
    safe(path,directory=True)
def safe(path,directory=False):
    path=Path(path)
    for p in (path,*path.parents):
        st=p.lstat()
        if stat.S_ISLNK(st.st_mode) or st.st_mode&0o022:raise ValueError('unsafe source path')
    st=path.lstat()
    if directory:
        if not stat.S_ISDIR(st.st_mode):raise ValueError('not a directory')
    elif not stat.S_ISREG(st.st_mode) or st.st_nlink!=1:raise ValueError('not a plain file')
    return path
def filehash(path):
    safe(path);h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''):h.update(block)
    return h.hexdigest()
def date(value):return datetime.date.fromisoformat(str(value)[:10])
def days(start,end):
    start=date(start);end=date(end)
    if start>end:raise ValueError('reversed report period')
    return {(start+datetime.timedelta(days=i)).isoformat() for i in range((end-start).days+1)}
def root(cabinet,archive=ARCHIVE):
    if cabinet not in CABINETS:raise ValueError('cabinet')
    return Path(archive)/'wb-current-catalog'/cabinet
def load_index(cabinet,archive=ARCHIVE):
    p=root(cabinet,archive)/'sources.json'
    return json.loads(safe(p).read_bytes()) if p.exists() else {'schema':1,'cabinet':cabinet,'reports':{}}
def store_index(index,archive=ARCHIVE):save(root(index['cabinet'],archive)/'sources.json',doc(index))
def metadata(rows):
    result={}
    for row in rows:
        key=str(row['reportId']);typ=int(row['reportType']);start=str(row['dateFrom'])[:10];end=str(row['dateTo'])[:10];currency=row['currency']
        if typ not in (1,2) or not currency:raise ValueError('report type/currency')
        if key not in result:days(start,end)
        identity={'report_id':key,'report_type':typ,'from':start,'to':end,'currency':currency}
        if key in result and any(result[key][k]!=v for k,v in identity.items()):raise ValueError('conflicting document period')
        if key not in result:result[key]=dict(identity,rows=0)
        result[key]['rows']+=1
    return result
def seed_baseline(cabinet,reader,archive=ARCHIVE):
    base=Path(archive)/'wb-current-catalog';mkdir(base);mkdir(root(cabinet,archive));mkdir(root(cabinet,archive)/'generations')
    index=load_index(cabinet,archive)
    if index.get('baseline_seeded'):return index
    for typ in (1,2):
        snapshot=reader.resolve(cabinet,typ,2026,root=archive)
        groups=metadata(reader.iter_rows(snapshot)) # Full iterator verifies counts/hashes.
        for report_id,info in groups.items():
            key='weekly|'+str(typ)+'|'+report_id
            index['reports'][key]=dict(info,period='weekly',csv=snapshot['csv'],sha256=snapshot['sha256'],baseline=True)
    index['baseline_seeded']=True;store_index(index,archive);publish(index,archive);return index
def active_reports(index):
    reports=list(index['reports'].values());weekly=[r for r in reports if r['period']=='weekly'];coverage={}
    for r in weekly:coverage.setdefault((r['report_type'],r['currency']),set()).update(days(r['from'],r['to']))
    active=list(weekly);superseded=[]
    for r in reports:
        if r['period']!='daily':continue
        dates=days(r['from'],r['to']);covered=coverage.get((r['report_type'],r['currency']),set())
        if dates<=covered:superseded.append(r)
        elif dates&covered:raise ValueError('daily report partially covered; no partial-row deletion')
        else:active.append(r)
    return sorted(active,key=lambda r:(r['report_type'],r['from'],r['period'],int(r['report_id']))),superseded
def publish(index,archive=ARCHIVE):
    active,superseded=active_reports(index);base=root(index['cabinet'],archive);pointer=base/'CURRENT.json'
    view={'schema':1,'cabinet':index['cabinet'],'sources':active,'superseded_daily':[{'report_id':r['report_id'],'report_type':r['report_type'],'from':r['from'],'to':r['to']} for r in superseded]}
    raw=doc(view);previous=None
    if pointer.exists():
        previous=json.loads(safe(pointer).read_bytes());p=base/'generations'/previous['generation']/'view.json'
        old=safe(p).read_bytes()
        if digest(old)!=previous['sha256']:raise ValueError('active view digest mismatch')
        if old==raw:return dict(previous,changed=False)
    ident=uuid.uuid4().hex;folder=base/'generations'/ident;mkdir(folder)
    save(folder/'view.json',raw)
    # Retain the old selected manifest as evidence; no source files are removed.
    save(folder/'parent.json',doc(previous))
    current={'schema':1,'generation':ident,'sha256':digest(raw)};save(pointer,doc(current));return dict(current,changed=True)
def snapshot(cabinet,typ,year,archive=ARCHIVE,*,allow_empty=False):
    base=root(cabinet,archive);pointer=safe(base/'CURRENT.json');pin=pointer.read_bytes();p=json.loads(pin)
    if p.get('schema')!=1 or not __import__('re').fullmatch('[0-9a-f]{32}',p.get('generation','')):raise ValueError('view identity')
    raw=safe(base/'generations'/p['generation']/'view.json').read_bytes()
    if digest(raw)!=p['sha256']:raise ValueError('view integrity')
    view=json.loads(raw)
    if view['cabinet']!=cabinet:raise ValueError('foreign view')
    chosen=[r for r in view['sources'] if r['report_type']==typ and (year is None or date(r['from']).year<=year<=date(r['to']).year)]
    if not chosen and not allow_empty:raise ValueError('no verified sources for year/type')
    # Metadata controls report selection, never a guessed sale/order-date filter.
    for r in chosen:
        path=Path(r['csv'])
        if not path.is_relative_to(Path(archive)):raise ValueError('source outside archive')
    return {'cabinet':cabinet,'report_type':typ,'year':year,'dataset':'wb_effective_finance_'+('main' if typ==1 else 'buyout'),'generation':p['generation'],'manifest_sha256':p['sha256'],'rows':sum(r['rows'] for r in chosen),'csv':None,'source_files':sorted({r['csv'] for r in chosen}),'sources':chosen,'pointer':str(pointer),'pointer_bytes':pin,'_effective_view':True}
def iter_view(snapshot):
    csv.field_size_limit(16*1024*1024);groups={};seen=set();count=0
    for r in snapshot['sources']:
        g=groups.setdefault(r['csv'],{'sha256':r['sha256'],'reports':{}})
        if g['sha256']!=r['sha256']:raise ValueError('conflicting source hash')
        g['reports'][r['report_id']]=r
    for path,group in groups.items():
        if filehash(path)!=group['sha256']:raise ValueError('source file integrity')
        counts={k:0 for k in group['reports']}
        with safe(path).open(encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f,delimiter=';')
            if not reader.fieldnames or len(reader.fieldnames)!=len(set(reader.fieldnames)) or not {'reportId','rrdId','reportType','_raw_json'}<=set(reader.fieldnames):raise ValueError('source headers')
            for row in reader:
                if None in row or any(v is None for v in row.values()):raise ValueError('malformed CSV row')
                report=row.get('reportId')
                if report not in group['reports']:continue
                key=(report,row.get('rrdId'));info=group['reports'][report]
                if not all(key) or key in seen or row.get('reportType')!=str(info['report_type']):raise ValueError('duplicate/foreign row')
                if (row.get('dateFrom','')[:10],row.get('dateTo','')[:10],row.get('currency'))!=(info['from'],info['to'],info['currency']):raise ValueError('row outside selected report period')
                source=json.loads(row['_raw_json'])
                def cell(v):return '' if v is None else (json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')) if isinstance(v,(bool,dict,list)) else str(v))
                if any(k not in row or row[k]!=cell(v) for k,v in source.items()) or any(row[k]!='' for k in set(row)-set(source)-{'_raw_json'}):raise ValueError('CSV/source mismatch')
                seen.add(key);counts[report]+=1;count+=1;yield row
        if any(counts[k]!=r['rows'] for k,r in group['reports'].items()) or filehash(path)!=group['sha256']:raise ValueError('source changed/incomplete')
    if count!=snapshot['rows'] or Path(snapshot['pointer']).read_bytes()!=snapshot['pointer_bytes']:raise ValueError('active catalog changed while reading')
