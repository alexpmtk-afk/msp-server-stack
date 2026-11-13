"""Read-only, stdlib-only access to selected weekly WB snapshots and exact bindings.

No network, tokens, SQL, subprocesses, archive writes or automatic downloads.
Use list(iter_rows(...)) or fully consume the iterator before accepting a result:
final row count, stable file hash and CURRENT checks run at exhaustion.
"""
import csv
import hashlib
import json
import os
import re
import stat
from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

BASE = Path(__file__).resolve().parent
ARCHIVE = Path('/opt/mcp/data/msp-marketplace-reports')
CABINETS = ('wb_dmitrieva', 'wb_laser_master', 'wb_novokshenov')
AMOUNTS = ('retailAmount','forPay','deliveryService','paidStorage','paidAcceptance',
           'deduction','penalty','additionalPayment','cashbackAmount',
           'cashbackDiscount','cashbackCommissionChange','acquiringFee',
           'ppvzSalesCommission','ppvzReward','vw','vwNds','rebillLogisticCost',
           'installmentCofinancingAmount','paymentSchedule')

def strict_pairs(pairs):
    out={}
    for key,value in pairs:
        if key in out:
            raise ValueError('Duplicate JSON key: '+key)
        out[key]=value
    return out

def load_json(raw):
    return json.loads(raw,object_pairs_hook=strict_pairs)

def safe_file(path, *, directory=False):
    path=Path(path)
    for item in (path,*path.parents):
        info=item.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_mode & 0o022:
            raise ValueError('Symlink or externally writable archive path')
    info=path.lstat()
    if directory:
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError('Expected directory')
    elif not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:
        raise ValueError('Expected plain report file')
    return path

def digest(path):
    safe_file(path)
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            h.update(block)
    return h.hexdigest()

def decimal(value):
    if value is None or isinstance(value,bool) or value=='':
        raise ValueError('Missing or boolean numeric cell')
    try:out=Decimal(str(value))
    except InvalidOperation as error:raise ValueError('Invalid decimal cell') from error
    if not out.is_finite():
        raise ValueError('Non-finite decimal cell')
    return out

def csv_cell(value):
    # Matches the installed exporter: JSON booleans, not Python True/False.
    if value is None:return ''
    if isinstance(value,bool):return 'true' if value else 'false'
    if isinstance(value,(dict,list)):
        return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    return str(value)

def bindings():
    return load_json((BASE/'field-bindings.json').read_text())

def resolve(cabinet, report_type, year=2026, *, root=ARCHIVE):
    if cabinet not in CABINETS or type(report_type) is not int or report_type not in (1,2) or type(year) is not int or not 2026<=year<=date.today().year:
        raise ValueError('Known cabinet, report type 1/2 and saved year required')
    current=Path(root)/'wb-current-catalog'/cabinet/'CURRENT.json'
    if current.exists():
        import importlib.util
        spec=importlib.util.spec_from_file_location('msp_wb_effective_reader','/usr/local/libexec/msp-wb-effective-reader.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module.snapshot(cabinet,report_type,year,root)
    dataset='wb_weekly_finance_'+('main' if report_type==1 else 'buyout')
    scope=Path(root)/'.b7-generations'/dataset/cabinet/str(year)
    pointer=safe_file(scope/'CURRENT.json')
    raw=pointer.read_bytes();ptr=load_json(raw)
    if type(ptr.get('schema')) is not int or ptr['schema']!=2 or not re.fullmatch('[a-f0-9]{32}',ptr.get('generation','')):
        raise ValueError('Invalid CURRENT identity')
    folder=scope/'generations'/ptr['generation']
    descriptor=safe_file(folder/'generation.json');data=descriptor.read_bytes()
    if hashlib.sha256(data).hexdigest()!=ptr.get('sha256'):
        raise ValueError('CURRENT descriptor checksum mismatch')
    desc=load_json(data)
    if type(desc.get('schema')) is not int or desc['schema']!=2 or desc.get('generation')!=ptr['generation'] or desc.get('scope')!=str(year):
        raise ValueError('Descriptor identity mismatch')
    files={}
    for entry in desc['files']:
        name=entry['path']
        if name not in ('data.csv','data.csv.meta.json') or name in files:
            raise ValueError('Unexpected or duplicate generation file')
        if type(entry.get('bytes')) is not int or entry['bytes']<0 or not re.fullmatch('[a-f0-9]{64}',entry.get('sha256','')):
            raise ValueError('Invalid file descriptor')
        files[name]=entry
    if set(files)!={'data.csv','data.csv.meta.json'}:
        raise ValueError('Incomplete published file pair')
    for name,entry in files.items():
        path=safe_file(folder/name)
        if path.stat().st_size!=entry['bytes'] or digest(path)!=entry['sha256']:
            raise ValueError('Published payload checksum mismatch')
    meta=load_json((folder/'data.csv.meta.json').read_text())
    expected={'schema':1,'dataset':dataset,'cabinet':cabinet,'period':str(year),
              'status':'LOCAL_VERIFIED','sha256':files['data.csv']['sha256'],'bytes':files['data.csv']['bytes']}
    if any(type(meta.get(k)) is not type(v) or meta[k]!=v for k,v in expected.items()) or type(meta.get('rows')) is not int or meta['rows']<0:
        raise ValueError('Manifest identity mismatch')
    if pointer.read_bytes()!=raw:
        raise ValueError('CURRENT changed while resolving')
    return {'cabinet':cabinet,'dataset':dataset,'report_type':report_type,'year':year,
            'generation':ptr['generation'],'csv':str(folder/'data.csv'),
            'sha256':files['data.csv']['sha256'],'rows':meta['rows'],
            'pointer':str(pointer),'pointer_bytes':raw,'manifest_sha256':ptr['sha256']}

def iter_rows(snapshot):
    if snapshot.get('_effective_view'):
        import importlib.util
        spec=importlib.util.spec_from_file_location('msp_wb_effective_reader','/usr/local/libexec/msp-wb-effective-reader.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        yield from module.iter_view(snapshot)
        return
    csv.field_size_limit(16*1024*1024)
    keys=set();count=0;path=Path(snapshot['csv'])
    with safe_file(path).open(encoding='utf-8-sig',newline='') as stream:
        reader=csv.DictReader(stream,delimiter=';')
        header=reader.fieldnames
        if not header or len(header)!=len(set(header)) or not {'reportId','rrdId','reportType','_raw_json'}<=set(header):
            raise ValueError('Invalid CSV header')
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError('Malformed CSV record')
            key=(row['reportId'],row['rrdId'])
            if not all(key) or key in keys or row['reportType']!=str(snapshot['report_type']):
                raise ValueError('Wrong report identity or duplicate record')
            keys.add(key);count+=1
            raw=load_json(row['_raw_json'])
            if not isinstance(raw,dict) or any(k not in row or csv_cell(v)!=row[k] for k,v in raw.items()):
                raise ValueError('CSV disagrees with its source row')
            if any(row[k]!='' for k in set(row)-set(raw)-{'_raw_json'}):
                raise ValueError('Nonblank CSV cell missing from source row')
            yield row
    if count!=snapshot['rows'] or digest(path)!=snapshot['sha256']:
        raise ValueError('Row total or final payload checksum mismatch')
    if Path(snapshot['pointer']).read_bytes()!=snapshot['pointer_bytes']:
        raise ValueError('CURRENT changed during read; repeat with a new snapshot')

def semantic_value(row, field_id):
    binding=bindings()['fields'].get(field_id)
    if binding is None:raise ValueError('Unknown semantic field')
    column=binding['column']
    if column is None:raise ValueError('UI-only field has no standalone local column')
    if column not in row or row[column]=='':return None
    if binding['kind'] in ('money','rate','count'):return decimal(row[column])
    return row[column]

def exportable_snapshot(snapshot):
    return {k:v for k,v in snapshot.items() if k!='pointer_bytes'}

def summarize(cabinet, types=(1,2), *, start=None, end=None, date_role='report_operation_date',
              nm_id=None, root=ARCHIVE):
    if date_role not in ('report_operation_date','operation_date','order_date'):
        raise ValueError('Explicit date role required')
    if start:date.fromisoformat(start)
    if end:date.fromisoformat(end)
    if start and end and start>end:raise ValueError('Invalid date window')
    date_column=bindings()['fields'][date_role]['column']
    groups={};snapshots=[];selected=0;missing_dates=0
    if len(set(types))!=len(types) or not types:raise ValueError('Duplicate or missing report types')
    for typ in types:
        if (Path(root)/'wb-current-catalog'/cabinet/'CURRENT.json').exists():
            import importlib.util
            spec=importlib.util.spec_from_file_location('msp_wb_effective_reader','/usr/local/libexec/msp-wb-effective-reader.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            snap=module.snapshot(cabinet,typ,None,root)
        else:snap=resolve(cabinet,typ,root=root)
        snapshots.append(exportable_snapshot(snap))
        for row in iter_rows(snap):
            if nm_id is not None and row.get('nmId')!=str(nm_id):continue
            rawdate=row.get(date_column,'')[:10]
            if start or end:
                if not rawdate:missing_dates+=1;continue
                date.fromisoformat(rawdate)
                if start and rawdate<start or end and rawdate>end:continue
            selected+=1
            key=(row['currency'],typ,row['sellerOperName'],row['docTypeName'])
            if key not in groups:
                groups[key]={'rows':0,'without_product_rows':0,'amounts':{k:Decimal(0) for k in AMOUNTS},'blank_numeric_cells':Counter()}
            group=groups[key];group['rows']+=1
            if row.get('nmId') in ('','0'):group['without_product_rows']+=1
            for col in AMOUNTS:
                if row.get(col) in (None,''):
                    group['blank_numeric_cells'][col]+=1
                else:
                    value=decimal(row[col])
                    if row['sellerOperName'] in ('Продажа','Возврат') and col in ('retailAmount','forPay') and value<0:
                        raise ValueError('Negative ordinary sale/return cell needs explicit analysis')
                    group['amounts'][col]+=value
    entries=[];ordinary={}
    for (currency,typ,operation,direction),group in sorted(groups.items()):
        amounts={k:str(v) for k,v in group['amounts'].items()}
        entries.append({'currency':currency,'report_type':typ,'operation':operation,'document_type':direction,
                        'rows':group['rows'],'without_product_rows':group['without_product_rows'],
                        'raw_amount_sums':amounts,'blank_numeric_cells':dict(group['blank_numeric_cells'])})
        if operation in ('Продажа','Возврат'):
            if direction!=operation:raise ValueError('Unexpected sale/return direction')
            if any(group['blank_numeric_cells'][col] for col in ('retailAmount','forPay')):
                raise ValueError('Incomplete ordinary sale/return amounts')
            if any(group['amounts'][col]<0 for col in ('retailAmount','forPay')):
                raise ValueError('Negative ordinary sale/return totals need explicit analysis')
            value=ordinary.setdefault((currency,typ),{'sales':Decimal(0),'returns':Decimal(0),'payout_sales':Decimal(0),'payout_returns':Decimal(0)})
            value['sales' if operation=='Продажа' else 'returns']+=group['amounts']['retailAmount']
            value['payout_sales' if operation=='Продажа' else 'payout_returns']+=group['amounts']['forPay']
    ordinary_out=[]
    for (currency,typ),value in sorted(ordinary.items()):
        ordinary_out.append({'currency':currency,'report_type':typ,**{k:str(v) for k,v in value.items()},
                             'net_sales':str(value['sales']-value['returns']),
                             'net_goods_payout':str(value['payout_sales']-value['payout_returns'])})
    return {'status':'LOCAL_VERIFIED_OPERATION_BREAKDOWN','cabinet':cabinet,'snapshots':snapshots,
            'filters':{'from':start,'to':end,'date_role':date_role,'nm_id':nm_id},
            'selected_rows':selected,'rows_excluded_missing_date':missing_dates,
            'ordinary_sales_returns':ordinary_out,'operation_breakdown':entries,
            'rules':['Operation amounts are raw signed sums, NOT a global settlement formula.',
                     'Ordinary net sales/payout exclude corrections, compensations and other operations shown separately.',
                     'Do not negate expense columns by document type or multiply amounts by quantity.',
                     'Missing cells are reported, not silently interpreted as zeros; no grouping across currencies.',
                     'Without SKU filter shared costs are retained; SKU filter excludes unallocated costs.',
                     'Bank payout, profit and tax base are not established by this report.'],
            'provider_calls':0,'archive_writes':0}
