"""Bounded WB list pagination using the EXISTING executor lock and sender.

No standalone HTTP CLI/scheduler or Redis job queue. Factory is supplied only
by an authorized supervisor. Every entry is synced before factory/Redis/HTTP.
A separately admitted discovery budget never consumes/resets fixed-report pilot.
"""
from __future__ import annotations
from datetime import datetime,timezone,date,timedelta
import json
from pathlib import Path
from .archive import _lock,_safe_write
from .generation_store import GenerationError,_ensure_scope_durable
from .standalone_wb import _digest,_encode,_resync,validate_authorization,PilotBlocked
from .wb_page_resume import _read_json,_checked
from .quota import QuotaBusy
from .runtime import TransportUnavailable
from .providers import Request,WB_LIST,ProviderError
from .backfill_plan import _inventory


def validate(plan):
    keys={'schema','kind','cabinet','year','date_from','date_to','limit','max_send_entries'}
    if type(plan) is not dict or set(plan)!=keys or plan.get('kind')!='wb-discovery':raise PilotBlocked('explicit discovery plan required')
    if any(type(plan[k]) is not int for k in ('schema','year','limit','max_send_entries')):raise PilotBlocked('strict discovery integers required')
    if plan['schema']!=1 or plan['year']!=2026 or not 1<=plan['limit']<=1000 or not 1<=plan['max_send_entries']<=100:raise PilotBlocked('bounded discovery required')
    start=date.fromisoformat(plan['date_from']);end=date.fromisoformat(plan['date_to'])
    first=date(2026,1,1);boundary_start=first-timedelta(days=first.weekday())
    boundary=(start==boundary_start and end==boundary_start+timedelta(days=6))
    if start>end or (not boundary and (start.year!=2026 or end.year!=2026)):raise PilotBlocked('2026 range or exact crossing week required')
    _inventory({'cabinet':plan['cabinet'],'year':2026,'status':'DISCOVERED_NOT_DOWNLOADED','items':[]},plan['cabinet'],2026)
    from .archive import CABINETS
    if plan['cabinet'] not in CABINETS['wb']:raise PilotBlocked('unknown cabinet')


def step(root,plan,authorization,factory,*,now,fault=None):
    """<=1 list HTTP attempt. Writes only durable report discovery evidence."""
    validate(plan);validate_authorization(authorization,plan,root,now)
    root=Path(root);ident=_digest(plan)
    with _lock(root,'standalone','wb_executor'):
        folder=_checked(root/'.wb-executor');_ensure_scope_durable(folder)
        path=folder/('discovery-'+ident+'.json')
        state=_read_json(path)
        if state is None:state={'schema':1,'plan_sha256':ident,'offset':0,'entries':0,'items':[],
                                'status':'READY','not_before_epoch':0,'last_error':None}
        else:
            seal=state.pop('state_sha256',None)
            if seal!=_digest(state):raise GenerationError('discovery journal checksum mismatch')
            if (type(state.get('schema')) is not int or state['schema']!=1 or state.get('plan_sha256')!=ident
                or type(state.get('entries')) is not int or not 0<=state['entries']<=plan['max_send_entries']
                or type(state.get('offset')) is not int or state['offset']<0
                or state.get('status') not in ('READY','DISPATCH_UNCERTAIN','WAITING','COMPLETE','PAUSED_BUDGET','HOLD_ERROR')):
                raise GenerationError('invalid discovery journal')
            _inventory({'cabinet':plan['cabinet'],'year':2026,'status':'DISCOVERED_NOT_DOWNLOADED','items':state['items']},plan['cabinet'],2026)
            _resync(path)
        def save():_safe_write(path,_encode({**state,'state_sha256':_digest(state)}))
        def result():return {**state,'cabinet':plan['cabinet'],'year':2026,'provider_coverage_proven':False}
        # Durable page replay precedes budget check: lost acknowledgement never causes refetch.
        page_path=folder/('discovery-'+ident+'-offset-'+str(state['offset'])+'.json')
        pending=_read_json(page_path)
        if pending:
            digest=pending.pop('page_sha256',None)
            if digest!=_digest(pending) or pending.get('plan_sha256')!=ident or type(pending.get('offset')) is not int or pending['offset']!=state['offset']:
                raise GenerationError('discovery pending page mismatch')
            if (type(pending.get('source_count')) is not int or not 0<=pending['source_count']<=plan['limit']
                or type(pending.get('terminal')) is not bool or type(pending.get('items')) is not list
                or len(pending['items'])!=pending['source_count']):raise GenerationError('invalid discovery page receipt')
            _inventory({'cabinet':plan['cabinet'],'year':2026,'status':'DISCOVERED_NOT_DOWNLOADED','items':pending['items']},plan['cabinet'],2026)
            page=pending['items'];combined={r['reportId']:r for r in state['items']}
            for row in page:
                if row['reportId'] in combined and combined[row['reportId']]!=row:raise GenerationError('discovery metadata conflict')
                combined[row['reportId']]=row
            state['items']=list(combined.values());state['offset']+=pending['source_count']
            state['status']='COMPLETE' if pending['terminal'] else 'READY'
            state['last_checked_at']=pending['checked_at'];save();return result()
        if state['status'] in ('COMPLETE','HOLD_ERROR','PAUSED_BUDGET') or state['not_before_epoch']>now:return result()
        if state['entries']>=plan['max_send_entries']:
            state['status']='PAUSED_BUDGET';save();return result()
        state['entries']+=1;state['status']='DISPATCH_UNCERTAIN';save()
        if fault:fault('after_budget_before_factory')
        req=Request('wb',WB_LIST,{'dateFrom':plan['date_from'],'dateTo':plan['date_to'],
                                'period':'weekly','limit':plan['limit'],'offset':state['offset']})
        try:status,rows=factory()(req)
        except (QuotaBusy,TransportUnavailable) as exc:
            state.update(status='WAITING',not_before_epoch=now+max(66,getattr(exc,'retry_after_seconds',66)),last_error=type(exc).__name__);save();return result()
        except (ProviderError,OSError):
            state.update(status='HOLD_ERROR',last_error='PROVIDER_OR_STORAGE_ERROR');save();return result()
        if status==429:
            state.update(status='WAITING',not_before_epoch=now+66,last_error='RATE_LIMIT');save();return result()
        if status not in (200,204) or (status==200 and type(rows) is not list):
            state.update(status='HOLD_ERROR',last_error='INVALID_DISCOVERY_RESPONSE');save();return result()
        rows=[] if status==204 else rows
        # Metadata-only receipt; do not persist financial amounts from the list.
        try:
            if len(rows)>plan['limit']:raise ValueError('oversized list page')
            page=[{k:r[k] for k in ('reportId','reportType','dateFrom','dateTo')} for r in rows]
            _inventory({'cabinet':plan['cabinet'],'year':2026,'status':'DISCOVERED_NOT_DOWNLOADED','items':page},plan['cabinet'],2026)
        except (TypeError,ValueError,KeyError):
            state.update(status='HOLD_ERROR',last_error='INVALID_DISCOVERY_METADATA');save();return result()
        pending={'schema':1,'plan_sha256':ident,'offset':state['offset'],'items':page,'source_count':len(rows),
                 'terminal':status==204 or len(rows)<plan['limit'],
                 'checked_at':datetime.fromtimestamp(now,timezone.utc).isoformat()}
        _safe_write(page_path,_encode({**pending,'page_sha256':_digest(pending)}))
        if fault:fault('after_page_before_state')
        # Reconcile by the same verified path, never recursively send another request.
        return {**result(),'status':'PAGE_STAGED_RECONCILE','provider_calls':1}


def read_inventory(root,plans):
    """Read verified COMPLETE monthly journals, deduplicate overlapping reports.

    Missing/partial window is UNKNOWN, never an empty annual discovery. No reads
    of original credentials or initialization writes. No yearly completeness claim.
    """
    if type(plans) is not list or not plans:raise ValueError('explicit discovery windows required')
    cabinet=None;items={};checked=[]
    for plan in plans:
        validate(plan)
        if cabinet is not None and plan['cabinet']!=cabinet:raise GenerationError('mixed discovery cabinet')
        cabinet=plan['cabinet'];ident=_digest(plan)
        state=_read_json(Path(root)/'.wb-executor'/('discovery-'+ident+'.json'),required=True)
        seal=state.pop('state_sha256',None)
        if seal!=_digest(state) or state.get('plan_sha256')!=ident or state.get('status')!='COMPLETE':
            raise GenerationError('discovery window not verified complete')
        if type(state.get('entries')) is not int or not 1<=state['entries']<=plan['max_send_entries']:
            raise GenerationError('discovery budget evidence invalid')
        _inventory({'cabinet':cabinet,'year':2026,'status':'DISCOVERED_NOT_DOWNLOADED','items':state['items']},cabinet,2026)
        for row in state['items']:
            rid=row['reportId']
            if rid in items and items[rid]!=row:raise GenerationError('conflicting overlapping discovery metadata')
            items[rid]=row
        checked.append(state.get('last_checked_at'))
    return {'cabinet':cabinet,'year':2026,'status':'DISCOVERED_NOT_DOWNLOADED',
            'items':sorted(items.values(),key=lambda x:x['reportId']),
            'window_count':len(plans),'checked_at_per_window':checked,'provider_coverage_proven':False}
