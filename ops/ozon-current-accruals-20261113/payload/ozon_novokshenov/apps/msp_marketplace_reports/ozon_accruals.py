"""Lossless candidate accrual reader; NO network, credential or approval changes.

Primary Ozon notice confirms endpoint purpose. Detailed shape is attributed to
an external schema snapshot until actual capture/reconciliation. Empty last_id
means only candidate exhaustion, never verified financial coverage on its own.
"""
from __future__ import annotations
import calendar
import hashlib
import json
import re
from datetime import date, timedelta
from decimal import Decimal

PATH = '/v1/finance/accrual/by-day'
TYPES_PATH = '/v1/finance/accrual/types'
DATASET = 'ozon_current_accruals'
CABINETS = ('ozon_dmitrieva', 'ozon_laser_master', 'ozon_novokshenov')
CATEGORIES = {'POSTING', 'ITEM', 'NON_ITEM', 'CONTAINER_FEES'}
CURRENCY_AMOUNT = re.compile(r'^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$')

class AccrualError(ValueError):
    pass

def strict_json(raw):
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out: raise AccrualError('duplicate JSON key')
            out[k] = v
        return out
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(AccrualError('nonfinite JSON')))

def digest(value):
    raw=json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(',', ':')).encode()
    return hashlib.sha256(raw).hexdigest()

def closed_history(as_of):
    if type(as_of) is not date or as_of < date(2026,11,1):
        raise AccrualError('approved closed Jan-Oct2026 scope required')
    jobs=[]
    for cabinet in CABINETS:
        for month in range(1,11):
            days=[date(2026,month,d).isoformat() for d in range(1,calendar.monthrange(2026,month)[1]+1)]
            jobs.append({'cabinet':cabinet,'month':f'2026-{month:02}', 'days':days,
                         'dataset':DATASET,'method':PATH,'status':'NOT_FETCHED',
                         'retention':'permanent; no realization replacement',
                         'include_non_item':True,'include_container_fees':True})
    return jobs

def request_body(day, cursor=''):
    if type(day) is not str or date.fromisoformat(day).isoformat()!=day or not '2026-11-01'<=day<='2026-11-13':
        raise AccrualError('outside bounded current snapshot')
    if type(cursor) is not str:raise AccrualError('cursor must be opaque string')
    return {'date':day,'last_id':cursor}

def identity(value):
    if type(value) is int and value>0:return str(value)
    if type(value) is str and re.fullmatch('[1-9][0-9]*',value):return value
    raise AccrualError('invalid accrual_id')

def money(value):
    if not isinstance(value,dict) or type(value.get('amount')) is not str or not CURRENCY_AMOUNT.fullmatch(value['amount']):
        raise AccrualError('invalid monetary representation')
    if type(value.get('currency')) is not str or not value['currency'].strip():
        raise AccrualError('currency missing')
    return Decimal(value['amount']),value['currency']

def types_catalog(payload):
    if not isinstance(payload,dict) or not isinstance(payload.get('accrual_types'),list):
        raise AccrualError('types envelope')
    out={}
    for entry in payload['accrual_types']:
        if not isinstance(entry,dict) or type(entry.get('id')) is not int or entry['id']<0:
            raise AccrualError('type identifier')
        if entry['id'] in out or type(entry.get('name')) is not str or type(entry.get('description')) is not str:
            raise AccrualError('duplicate or malformed type')
        out[entry['id']]=entry
    if not out:raise AccrualError('empty type catalogue is not accepted')
    return out

def inspect_page(raw, day, *, input_cursor='', prior_cursors=(), seen=None):
    request_body(day,input_cursor)
    payload=strict_json(raw)
    if not isinstance(payload,dict) or type(payload.get('last_id')) is not str or not isinstance(payload.get('accruals'),list):
        raise AccrualError('missing accruals/explicit string last_id')
    cursor=payload['last_id'];seen=dict(seen or {});rows=[];duplicates=0;warnings=[]
    for row in payload['accruals']:
        if not isinstance(row,dict):raise AccrualError('accrual object required')
        key=identity(row.get('accrual_id'))
        if row.get('date')!=day:raise AccrualError('foreign day')
        if row.get('accrued_category') not in CATEGORIES:warnings.append('UNKNOWN_CATEGORY_RETAINED')
        if 'total_amount' in row and row['total_amount'] is not None:money(row['total_amount'])
        sha=digest(row)
        if key in seen:
            if seen[key]!=sha:raise AccrualError('conflicting accrual identity')
            duplicates+=1;continue
        seen[key]=sha;rows.append(row)
    if cursor:
        if cursor==input_cursor or cursor in prior_cursors:raise AccrualError('cursor cycle')
        status='NEXT_PAGE_REQUIRED'
        if not payload['accruals']:warnings.append('EMPTY_PAGE_WITH_CURSOR_REQUIRES_RECONCILIATION')
    else:status='CURSOR_EXHAUSTED_UNRECONCILED'
    return {'status':status,'rows':rows,'last_id':cursor,'seen':seen,'identical_duplicates':duplicates,
            'warnings':sorted(set(warnings)),'provider_coverage_verified':False,
            'raw_sha256':hashlib.sha256(raw).hexdigest()}

def next_request(page,day,*,age_seconds):
    if page['status']!='NEXT_PAGE_REQUIRED':raise AccrualError('no proven continuation requested')
    # 15 min is candidate schema TTL; never restart silently after expiry.
    if not 0<=age_seconds<840:raise AccrualError('cursor expiry requires explicit reconciliation')
    if 'EMPTY_PAGE_WITH_CURSOR_REQUIRES_RECONCILIATION' in page['warnings']:
        raise AccrualError('ambiguous empty page')
    return request_body(day,page['last_id'])

def money_leaves(row,catalog):
    """Audit every monetary leaf, including unknown branches; NOT additive ledger.

    Totals, prices, commission components overlap; never sum this table wholesale.
    Every source path and sign is retained. No guessed type/category substitution.
    """
    out=[]
    def walk(v,path,nearest_type=None):
        if isinstance(v,dict):
            nearest_type=v.get('type_id',nearest_type)
            if 'amount' in v and 'currency' in v:
                amount,currency=money(v)
                out.append({'json_path':path,'amount':str(amount),'currency':currency,
                            'type_id':nearest_type,'type_description':catalog.get(nearest_type,{}).get('description'),
                            'type_known':nearest_type is None or nearest_type in catalog,
                            'aggregation':'DO_NOT_SUM_WITHOUT_ROLE_MAPPING'})
            for k,x in v.items():walk(x,path+'.'+k,nearest_type)
        elif isinstance(v,list):
            for i,x in enumerate(v):walk(x,f'{path}[{i}]',nearest_type)
    walk(row,'$')
    return out
