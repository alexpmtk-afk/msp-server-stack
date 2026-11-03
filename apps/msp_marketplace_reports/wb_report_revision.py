"""Opt-in offline publication of a terminal WB report revision.

Does not fetch, reset accepted page/budget state or change PR104's importer.
Uses its immutable generation/CAS publication. Changed rows and removed rows of
one report are replaced together; all other reports and old generations remain.
"""
from __future__ import annotations
import json
import re
import tempfile
from pathlib import Path
from .archive import DATASETS, _encode, _rows, _lock, _sha
from .generation_store import GenerationError, read_active, publish_batch
from .versioned_archive import _assert_no_legacy, _pair
from .wb_worker_adapter import _dataset, _stage_record, _stream_csv


def revision_root(root, revision):
    if not isinstance(revision,str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}',revision):
        raise ValueError('explicit safe revision identity required')
    return Path(root)/'.wb-revisions'/revision


def publish_revision(root, *, cabinet, year, report_id, report_type,
                     revision, expected_generation, checked_at, report_metadata=None):
    """Publish ONLY already-terminal verified pages; no network or budget reset.

    revision is a separately approved refresh run identifier, never a token.
    Caller stages with accepted step_wb_detail at revision_root, through the
    same approved single sender/budget. No automatic live CLI is provided.
    """
    from datetime import datetime
    if type(checked_at) is not str or datetime.fromisoformat(checked_at).tzinfo is None:
        raise ValueError('timezone-aware verification time required')
    metadata_digest=None
    if report_metadata is not None:
        from .backfill_plan import _inventory
        from .finance_refresh_plan import digest
        _inventory({'cabinet':cabinet,'year':year,'status':'DISCOVERED_NOT_DOWNLOADED','items':[report_metadata]},cabinet,year)
        if report_metadata['reportId']!=report_id or report_metadata['reportType']!=report_type:raise ValueError('revision discovery identity mismatch')
        metadata_digest=digest(report_metadata)
    root=Path(root);dataset=_dataset(report_type);period=str(year)
    staged=revision_root(root,revision)
    folder,state=_stage_record(staged,cabinet,year,report_id,report_type)
    with tempfile.TemporaryDirectory(prefix='.revision-csv-',dir=folder) as td:
        source=Path(td)/'report.csv'
        count=_stream_csv(staged,cabinet,year,report_id,report_type,source)
        raw=source.read_bytes();fields,incoming=_rows(raw,DATASETS[dataset][1])
        if any(row['reportId']!=str(report_id) or row['reportType']!=str(report_type)
               for row in incoming.values()):raise GenerationError('revision report identity mismatch')
        if any((row.get('dateTo') or row.get('date_to') or '')[:4] not in ('',period)
               for row in incoming.values()):raise GenerationError('revision year mismatch')
        with _lock(root,cabinet,dataset):
            _assert_no_legacy(root,dataset,cabinet,period)
            active=read_active(root,dataset,cabinet,period)
            parent=active['generation'] if active else None
            if parent!=expected_generation:raise GenerationError('stale revision generation')
            candidate=dict(active['files']) if active else {}
            old_fields,old_rows=_rows(candidate['data.csv'],DATASETS[dataset][1]) if active else ([],{})
            kept={k:v for k,v in old_rows.items() if k[0]!=str(report_id)}
            kept.update(incoming)
            payload=_encode(list(dict.fromkeys([*old_fields,*fields])),kept)
            _pair(candidate,'data.csv',payload,dataset,cabinet,period,DATASETS[dataset][1])
            content_changed=not active or active['files']['data.csv']!=payload
            # Evidence commits atomically with its candidate, not as a false side receipt.
            evidence={'schema':1,'cabinet':cabinet,'year':year,'report_id':report_id,
                      'report_type':report_type,'revision':revision,'checked_at':checked_at,
                      'terminal_http_status':204,'terminal_cursor':state['current_rrd_id'],
                      'page_hashes':[p['sha256'] for p in state['pages']],
                      'report_csv_sha256':_sha(raw),'rows':count,
                      'provider_coverage_proven':False,'source_metadata_sha256':metadata_digest}
            meta=json.loads(candidate['data.csv.meta.json'])
            previous_checks=(json.loads(active['files']['data.csv.meta.json']).get('wb_report_checks',{}) if active else {})
            meta['wb_report_checks']={**previous_checks,str(report_id):evidence}
            candidate['data.csv.meta.json']=(json.dumps(meta,sort_keys=True,separators=(',',':'))+'\n').encode()
            receipt=publish_batch(root,dataset,cabinet,period,candidate,expected_generation=parent)
            # Publish_batch has verified CURRENT binding; read back business rows too.
            actual=read_active(root,dataset,cabinet,period)
            _,actual_rows=_rows(actual['files']['data.csv'],DATASETS[dataset][1])
            selected={k:v for k,v in actual_rows.items() if k[0]==str(report_id)}
            if len(selected)!=len(incoming) or any(any(selected[k].get(f,'')!=v for f,v in row.items()) for k,row in incoming.items()):
                raise GenerationError('published revision differs from staged rows')
            return {**receipt,'report_content_changed':content_changed,'report_id':report_id,
                    'rows':count,'terminal_http_status':204,'provider_coverage_proven':False}
