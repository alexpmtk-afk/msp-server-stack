"""Read-only report catalog from existing cursor/budget and pinned archive state.

No initialization, repair, resealing, network, credential access or provider
completeness claims. Invalid local evidence is a HOLD, never a fresh download.
"""
import json,csv,io,zlib
from pathlib import Path
from .archive import DATASETS,_rows,_sha,_scan_rows
from .generation_store import read_active,GenerationError
from .wb_worker_adapter import _dataset
from .wb_page_resume import _dir,_read_json,_validate_state,_verify_pages,_validate_page,_unique_rows
from .wb_report_revision import revision_root
from .ingest import _cell
from .standalone_wb import _digest
from .backfill_plan import _inventory


def _completed_pages_readonly(root,cabinet,year,rid,kind):
    """No O_CREAT/O_RDWR lock: admin controller is ProtectSystem=strict.

    The caller serializes executor admission. Page bytes are pinned to the
    captured validated cursor chain and rehashed on the actual read, so this
    read-only path neither modifies evidence nor trusts mutable reread bytes.
    """
    folder=_dir(root,cabinet,year,rid,kind)
    state=_read_json(folder/'state.json',required=True)
    _validate_state(state,cabinet,year,rid,kind)
    if state['status']!='STAGED_COMPLETE':raise GenerationError('report not terminal')
    _verify_pages(folder,state,rid,kind)
    seen={}
    for entry in state['pages']:
        page,raw=_read_json(folder/('page-'+str(entry['cursor'])+'.json'),required=True,with_bytes=True)
        if _sha(raw)!=entry['sha256'] or _validate_page(page,rid,kind,entry['cursor'])!=entry['next_rrd_id']:
            raise GenerationError('read-only page changed during verification')
        yield _unique_rows(page,seen)


def _compressed_report_index(data, keys):
    """Keep compressed CSV per report, not millions of annual field objects."""
    fields, records = _scan_rows(data, keys)
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, delimiter=';', lineterminator='\n')
    writer.writerow(fields)
    header = ('\ufeff'+stream.getvalue()).encode('utf-8')
    buckets = {}
    for key, values in records:
        if key[0] not in buckets:
            buckets[key[0]]=(zlib.compressobj(1), bytearray())
        encoder, output = buckets[key[0]]
        stream.seek(0); stream.truncate(0); writer.writerow(values)
        output.extend(encoder.compress(stream.getvalue().encode('utf-8')))
    return header, {rid: bytes(output+encoder.flush()) for rid,(encoder,output) in buckets.items()}


def _selected_rows(data, keys, rid):
    fields, records = _scan_rows(data, keys)
    return {key:dict(zip(fields,values)) for key,values in records if key[0]==str(rid)}


def report_receipt(root,cabinet,year,rid,kind,*,snapshot=None):
    root=Path(root);dataset=_dataset(kind)
    out={'verified':False,'cabinet':cabinet,'year':year,'report_id':rid,'report_type':kind,
         'cursor':None,'page_hashes':[],'budget_entries':None,'last_error':None,
         'not_before_epoch':None,'last_checked_at':None,'provider_coverage_proven':False}
    try:
        # Snapshot is scoped to ONE serialized root selection, never global.
        key=(str(root),dataset,cabinet,str(year))
        if snapshot is None or key not in snapshot:
            active=read_active(root,dataset,cabinet,str(year))
            if snapshot is not None:snapshot[key]={'active':active}
        else:active=snapshot[key]['active']
        check=None
        if active:
            meta=json.loads(active['files']['data.csv.meta.json'])
            check=meta.get('wb_report_checks',{}).get(str(rid))
        staged=revision_root(root,check['revision']) if check else root
        folder=_dir(staged,cabinet,year,rid,kind);state=_read_json(folder/'state.json')
        if state is None:return {**out,'status':'MISSING'}
        _validate_state(state,cabinet,year,rid,kind);_verify_pages(folder,state,rid,kind)
        out.update(status=state['status'],cursor=state['current_rrd_id'],page_hashes=[p['sha256'] for p in state['pages']])
        plan={'schema':1,'cabinet':cabinet,'year':year,'report_id':rid,'report_type':kind,'max_send_entries':3}
        budget=_read_json(staged/'.wb-executor'/(_digest(plan)+'.json'))
        if budget is not None:
            seal=budget.pop('state_sha256',None)
            if seal!=_digest(budget) or budget.get('plan_sha256')!=_digest(plan) or type(budget.get('schema')) is not int or budget['schema']!=1 or type(budget.get('send_entries')) is not int or type(budget.get('approved_total_entries',3)) is not int or not 3<=budget.get('approved_total_entries',3)<=1000 or not 0<=budget['send_entries']<=budget.get('approved_total_entries',3):
                raise GenerationError('budget receipt mismatch')
            out.update(budget_entries=budget['send_entries'],last_error=budget.get('error_type'),not_before_epoch=budget.get('not_before_epoch'))
        if state['status']!='STAGED_COMPLETE':return out
        if not active:
            if budget is not None and budget.get('status')!='DONE':return {**out,'status':'STAGED_PUBLICATION_PENDING'}
            raise GenerationError('terminal report missing publication')
        if snapshot is None:
            selected=_selected_rows(active['files']['data.csv'],DATASETS[dataset][1],rid)
        else:
            if 'partitions' not in snapshot[key]:
                snapshot[key]['partitions']=_compressed_report_index(active['files']['data.csv'],DATASETS[dataset][1])
            header,buckets=snapshot[key]['partitions']
            packed=buckets.get(str(rid))
            selected={} if packed is None else _rows(header+zlib.decompress(packed),DATASETS[dataset][1])[1]
        if not selected and check is None and budget is not None and budget.get('status')!='DONE':
            return {**out,'status':'STAGED_PUBLICATION_PENDING'}
        fields=set(DATASETS[dataset][1])|{'reportType'}
        for page in _completed_pages_readonly(staged,cabinet,year,rid,kind):
            for row in page:fields.update(row)
        fields.discard('_raw_json');count=0
        for page in _completed_pages_readonly(staged,cabinet,year,rid,kind):
            for row in page:
                expected={f:_cell(row.get(f)) for f in fields}
                expected['_raw_json']=json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(',',':'))
                key=tuple(expected[f] for f in DATASETS[dataset][1])
                if key not in selected or any(selected[key].get(f,'')!=v for f,v in expected.items()):raise GenerationError('published report mismatch')
                count+=1
        if count!=len(selected):raise GenerationError('published report row count differs')
        if check:
            if (check.get('page_hashes')!=out['page_hashes'] or check.get('terminal_http_status')!=204 or check.get('rows')!=count):
                raise GenerationError('revision check receipt mismatch')
            out.update(last_checked_at=check.get('checked_at'),metadata_sha256=check.get('source_metadata_sha256'))
        out.update(verified=True,status='TERMINAL_LOCAL_VERIFIED',terminal_http_status=204,
                   page_hashes_verified=True,publication_verified=True,rows=count,
                   generation=active['generation'],manifest_sha256=active['manifest_sha256'])
        return out
    except (OSError,ValueError,KeyError,TypeError) as exc:
        from .standalone_wb import failure_location
        return {**out,'verified':False,'status':'HOLD_INVALID_LOCAL_EVIDENCE','last_error':type(exc).__name__,'failure':failure_location(exc)}


def collect(root,discoveries):
    out={}
    from .archive import CABINETS
    if type(discoveries) is not dict or set(discoveries)-set(CABINETS['wb']):raise ValueError('known discovery cabinets required')
    for cabinet,inventory in discoveries.items():
        for rid,(kind,start,end) in _inventory(inventory,cabinet,2026):
            out[f'{cabinet}:{rid}:{kind}']=report_receipt(root,cabinet,2026,rid,kind)
    return out
