"""Deterministic bounded financial refresh manifest, NOT a second queue/sender.

Consumes separately authorized discovery and verified local evidence. No HTTP,
credentials, Redis reservations, service edits or hidden state initialization.
The existing sole executor/supervisor must admit every selected action.
"""
from __future__ import annotations
import argparse
import calendar
from datetime import date, datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
from .archive import CABINETS
from .backfill_plan import _inventory


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def discovery_windows(year,as_of):
    """Month-bounded discovery with overlap retained by reportId/type dedup."""
    if type(year) is not int or year!=2026 or type(as_of) is not date or as_of.year<year:
        raise ValueError('2026/as_of required')
    end=min(as_of,date(year,12,31));out=[]
    for month in range(1,end.month+1):
        last=date(year,month,calendar.monthrange(year,month)[1])
        out.append({'dateFrom':date(year,month,1).isoformat(),'dateTo':min(last,end).isoformat(),
                    'period':'weekly','limit':1000,'offset':0})
    # Keep every existing monthly plan byte-identical: budgets are keyed by it.
    # Separately discover the complete weekly period crossing New Year.
    first=date(year,1,1);monday=first-timedelta(days=first.weekday())
    sunday=monday+timedelta(days=6)
    if monday<first and as_of>=sunday:
        out.append({'dateFrom':monday.isoformat(),'dateTo':sunday.isoformat(),
                    'period':'weekly','limit':1000,'offset':0})
    return out


def build_refresh_plan(*,as_of,discoveries=None,evidence=None,max_actions=12,mode='backfill'):
    if type(max_actions) is not int or not 1<=max_actions<=100 or mode not in ('backfill','daily'):
        raise ValueError('bounded mode/actions required')
    windows=discovery_windows(2026,as_of);discoveries=discoveries or {};evidence=evidence or {}
    if set(discoveries)-set(CABINETS['wb']):raise ValueError('unknown WB cabinet')
    candidates=[];gaps=[]
    def add(item,reason):
        value={**item,'reason':reason};value['unit_id']=digest(item)
        candidates.append(value)
    for cabinet in CABINETS['wb']:
        inv=_inventory(discoveries.get(cabinet),cabinet,2026)
        if inv is None:
            gaps.append({'cabinet':cabinet,'status':'DISCOVERY_REQUIRED'})
            # Full bounded discovery is separate from fixed-report pilot budget.
            for body in windows:
                list_key=f"list:{cabinet}:{body['dateFrom']}:{body['dateTo']}"
                if evidence.get(list_key,{}).get('checked_on')!=as_of.isoformat():
                    add({'marketplace':'wb','cabinet':cabinet,'action':'DISCOVER_REPORTS','body':body},'missing_inventory')
            continue
        # Daily rediscovery is explicit; fresh month receipts suppress duplicate list work.
        if mode=='daily':
            for body in windows:
                list_key=f"list:{cabinet}:{body['dateFrom']}:{body['dateTo']}"
                if evidence.get(list_key,{}).get('checked_on')!=as_of.isoformat():
                    add({'marketplace':'wb','cabinet':cabinet,'action':'DISCOVER_REPORTS','body':body},'daily_discovery_due')
        for rid,(kind,start,end) in inv:
            scope={'marketplace':'wb','cabinet':cabinet,'year':2026,'report_id':rid,'report_type':kind,
                   'date_from':start.isoformat(),'date_to':end.isoformat()}
            key=f'{cabinet}:{rid}:{kind}';local=evidence.get(key)
            # Caller must supply actual verified receipt, not row count or untrusted id alone.
            if local and local.get('status')=='HOLD_INVALID_LOCAL_EVIDENCE':
                add({**scope,'action':'REVIEW_LOCAL_EVIDENCE'},'invalid_local_integrity');continue
            if local is None or local.get('verified') is not True:
                add({**scope,'action':'RESUME_OR_DOWNLOAD'},'missing_or_unverified')
                continue
            required={'terminal_http_status':204,'page_hashes_verified':True,'publication_verified':True}
            if any(type(local.get(k)) is not type(v) or local[k]!=v for k,v in required.items()):
                add({**scope,'action':'REVIEW_LOCAL_EVIDENCE'},'incomplete_terminal_evidence');continue
            if mode=='backfill':continue
            # A metadata signature alone cannot detect same-id amount corrections.
            checked=local.get('last_checked_at')
            try:
                when=datetime.fromisoformat(checked)
                if when.tzinfo is None:raise ValueError()
                age=(as_of-when.astimezone(timezone.utc).date()).days
                if age<0:raise ValueError()
            except (TypeError,ValueError):
                add({**scope,'action':'REFETCH_REVISION'},'unknown_last_check_time');continue
            metadata=digest({'reportId':rid,'reportType':kind,'dateFrom':start.isoformat(),'dateTo':end.isoformat()})
            recent=(as_of-end).days<=35
            if mode=='daily' and (metadata!=local.get('metadata_sha256') or age>=(1 if recent else 30)):
                add({**scope,'action':'REFETCH_REVISION'},'metadata_changed_or_revalidation_due')
        if not inv:gaps.append({'cabinet':cabinet,'status':'EMPTY_INVENTORY_NOT_PROVEN_COMPLETE'})
    # Ozon remains separately gated; FINAL is never replaced by CURRENT orders.
    ozon=[]
    for cabinet in CABINETS['ozon']:
        last=min(12,as_of.month-1) if as_of.year==2026 else 12
        for month in range(1,last+1):
            ozon.append({'cabinet':cabinet,'dataset':'ozon_final_realization','period':f'2026-{month:02}',
                         'action':'FETCH_OR_REVALIDATE_CLOSED_MONTH','gate':'OZON_METHOD_ACCEPTANCE_REQUIRED'})
        if as_of.year==2026:
            for dataset in ('ozon_current_orders_fbo','ozon_current_orders_fbs','ozon_current_accruals'):
                ozon.append({'cabinet':cabinet,'dataset':dataset,'period':as_of.strftime('%Y-%m'),
                             'action':'REPLACE_OPEN_MONTH_SNAPSHOT','gate':'OZON_METHOD_ACCEPTANCE_REQUIRED'})
    # Deterministic ordering and unit identity prevent duplicate admission by one supervisor.
    # Daily oldest-due checks first: bounded truncation must not starve old corrections.
    candidates.sort(key=lambda x:(evidence.get(f"{x['cabinet']}:{x.get('report_id')}:{x.get('report_type')}",{}).get('last_checked_at') or '',x['unit_id']))
    unique={x['unit_id']:x for x in candidates};ordered=list(unique.values())
    return {'schema':1,'mode':mode,'as_of':as_of.isoformat(),'year':2026,'network_calls':0,
            'actions':ordered[:max_actions],'remaining_actions':len(ordered[max_actions:]),
            'gaps':gaps,'ozon_separate_plan':ozon,'cabinet_count':6,
            'approval_required':True,'provider_coverage_proven':False,'executable_without_admission':False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    when=p.add_mutually_exclusive_group(required=True)
    when.add_argument('--as-of',type=date.fromisoformat)
    when.add_argument('--today-moscow',action='store_true')
    p.add_argument('--discoveries',type=Path);p.add_argument('--evidence',type=Path)
    p.add_argument('--archive-root',type=Path,help='independently validate actual local page/budget/publication receipts')
    p.add_argument('--mode',choices=('backfill','daily'),default='backfill');p.add_argument('--max-actions',type=int,default=12)
    a=p.parse_args(argv)
    read=lambda f:json.loads(f.read_text()) if f else None
    from zoneinfo import ZoneInfo
    as_of=datetime.now(ZoneInfo('Europe/Moscow')).date() if a.today_moscow else a.as_of
    discoveries=read(a.discoveries)
    evidence=read(a.evidence) or {}
    if a.archive_root:
        from .finance_receipts import collect
        evidence.update(collect(a.archive_root,discoveries or {}))
    print(json.dumps(build_refresh_plan(as_of=as_of,discoveries=discoveries,evidence=evidence,mode=a.mode,max_actions=a.max_actions),indent=2,sort_keys=True))
    return 0

if __name__=='__main__':raise SystemExit(main())
