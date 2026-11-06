"""Bounded deterministic WB one-shot; no daemon, scheduler or Redis job queue.

CLI is blocked without a root-controlled, expiring owner authorization bound to
this code and exact plan. Attestations are NOT discovery of other live clients.
Existing SharedQuota approval is still required; this module never sets gates.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
import stat
import time
from datetime import datetime
from pathlib import Path
from .archive import _lock, _safe_write, _validate
from .generation_store import GenerationError, _ensure_scope_durable, _sync_dir
from .runtime import ReadOnlyHTTP, TransportUnavailable
from .providers import ProviderError
from .wb_page_resume import _checked
from .wb_worker_adapter import run_one_step, _dataset

WB_PAGE_PAUSE_SECONDS = 70.0

class PilotBlocked(GenerationError):
    pass

class BudgetPause(Exception):
    pass

def _strict(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise PilotBlocked('duplicate control JSON key')
        value[key] = item
    return value

def _encode(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))+'\n').encode()

def _digest(value):
    return hashlib.sha256(_encode(value)).hexdigest()

def code_digest():
    root = Path(__file__).parent
    return _digest({p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.glob('*.py'))})

def read_control(path):
    path = _checked(Path(path))
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 16384 or info.st_nlink != 1:
            raise PilotBlocked('control must be a small plain file')
        raw = os.read(fd, 16385)
        if len(raw) > 16384:
            raise PilotBlocked('control too large')
        return json.loads(raw, object_pairs_hook=_strict)
    finally:
        os.close(fd)

def read_authorization(path):
    path = Path(os.path.abspath(path))
    for p in [path, *path.parents]:
        info = p.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise PilotBlocked('authorization requires a root-controlled path')
    return read_control(path)

def validate_plan(plan):
    keys = {'schema','cabinet','year','report_id','report_type','max_send_entries'}
    if type(plan) is not dict or set(plan) != keys:
        raise PilotBlocked('invalid explicit pilot plan')
    if type(plan['schema']) is not int or plan['schema'] != 1:
        raise PilotBlocked('invalid plan schema')
    if any(type(plan[k]) is not int for k in ('year','report_id','report_type','max_send_entries')):
        raise PilotBlocked('plan requires strict integers')
    if plan['report_id'] <= 0 or not 1 <= plan['max_send_entries'] <= 3 or plan['year'] != 2026:
        raise PilotBlocked('pilot limited to explicit 2026 report and at most three send entries')
    _validate(_dataset(plan['report_type']), plan['cabinet'], str(plan['year']))

def validate_authorization(doc, plan, root, now):
    if type(doc) is not dict or type(doc.get('schema')) is not int or doc['schema'] != 1:
        raise PilotBlocked('invalid owner authorization')
    if (doc.get('plan_sha256') != _digest(plan) or doc.get('code_sha256') != code_digest()
            or doc.get('archive_root') != str(Path(os.path.abspath(root)))):
        raise PilotBlocked('authorization does not match plan/code/root')
    if type(doc.get('expires_epoch')) is not int or doc['expires_epoch'] <= now:
        raise PilotBlocked('owner authorization expired')
    for key in ('owner_api_pilot_authorized','shared_quota_verified','conflicting_clients_excluded'):
        if doc.get(key) is not True:
            raise PilotBlocked('owner pilot/shared quota/conflict exclusion evidence required')
    if not isinstance(doc.get('evidence_reference'), str) or not doc['evidence_reference'].strip():
        raise PilotBlocked('external evidence reference required')

def _resync(path):
    _ensure_scope_durable(path.parent)
    fd = os.open(_checked(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise PilotBlocked('invalid executor journal inode')
        os.fsync(fd)
    finally:
        os.close(fd)
    _sync_dir(path.parent)

def reconcile_admission(root, plan):
    """Read-only fail-closed check across ALL wake nonces and legacy HTTP logs.

    Evidence never reconstructs a budget: only its original sealed counter may
    authorize continuation. Unscoped/invalid evidence requires manual review.
    """
    from .wb_page_resume import _dir, _read_json, _validate_state, _verify_pages
    root = Path(root)
    folder = _checked(root / '.wb-executor')
    totals = {}
    plans = {_digest(plan): plan}
    def budget(p):
        discovery = p.get('kind') == 'wb-discovery'
        key = _digest(p)
        path = folder / (('discovery-' if discovery else '') + key + '.json')
        value = read_control(path)  # Missing/corrupt is NEVER zero.
        if type(value) is not dict:
            raise PilotBlocked('budget is not an object')
        seal = value.pop('state_sha256', None)
        count = value.get('entries' if discovery else 'send_entries')
        cap = value.get('approved_total_entries', p['max_send_entries'])
        if (seal != _digest(value) or value.get('plan_sha256') != key
                or type(count) is not int or type(cap) is not int
                or not 0 <= count <= cap <= 1000):
            raise PilotBlocked('original sealed budget invalid; no reset')
        return count
    def legacy(name, event):
        base = {'schema':1,'cabinet':'wb_laser_master','year':2026,'max_send_entries':3}
        if name == 'E-883801632-events.jsonl':
            return {**base,'report_id':883801632,'report_type':1}
        if name in ('history-october-first-events.jsonl','history-next-865431404-events.jsonl'):
            if event.get('method_scope') == 'list':
                return {'schema':1,'kind':'wb-discovery','cabinet':'wb_laser_master','year':2026,
                        'date_from':'2026-10-01','date_to':'2026-10-31','limit':1000,'max_send_entries':2}
            if event.get('method_scope') == 'detail':
                return {**base,'report_id':883801636 if name.startswith('history-october') else 865431404,
                        'report_type':2 if name.startswith('history-october') else 1}
        raise PilotBlocked('unscoped historical HTTP evidence; review required')
    if folder.exists():
        for path in sorted(folder.glob('*events.jsonl')):
            _checked(path)
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 16*1024*1024:
                    raise PilotBlocked('invalid HTTP evidence file')
                raw = os.read(fd, 16*1024*1024+1)
                if len(raw) > 16*1024*1024:
                    raise PilotBlocked('HTTP evidence too large')
            finally:
                os.close(fd)
            pending = None
            for line in raw.splitlines():
                event = json.loads(line, object_pairs_hook=_strict)
                if type(event) is not dict or event.get('event') not in ('HTTP_DISPATCH_ATTEMPT','HTTP_RESPONSE','HTTP_OUTCOME_UNKNOWN'):
                    raise PilotBlocked('invalid historical HTTP event')
                p = event.get('plan')
                if p is None and event['event'] != 'HTTP_DISPATCH_ATTEMPT' and pending is not None:
                    p = pending
                if p is None:
                    p = legacy(path.name, event)
                if p.get('kind') != 'wb-discovery':
                    validate_plan(p)
                else:
                    from .wb_discovery_resume import validate
                    validate(p)
                key = _digest(p);plans[key] = p
                if event['event'] == 'HTTP_DISPATCH_ATTEMPT':
                    totals[key] = totals.get(key, 0) + 1;pending = p
                else:
                    if pending is None:
                        # An orphan outcome still proves at least one spent entry.
                        totals[key] = totals.get(key, 0) + 1
                    elif _digest(pending) != key:
                        raise PilotBlocked('HTTP outcome scope mismatch')
                    pending = None
    selected = folder / (('discovery-' if plan.get('kind') == 'wb-discovery' else '') + _digest(plan) + '.json')
    counts = {}
    for key, p in plans.items():
        if key in totals or (key == _digest(plan) and (selected.exists() or selected.is_symlink())):
            counts[key] = budget(p)
            if totals.get(key, 0) > counts[key]:
                raise PilotBlocked('HTTP attempts exceed original sealed budget')
    if plan.get('kind') == 'wb-discovery':
        if folder.exists() and any(folder.glob('discovery-' + _digest(plan) + '-offset-*.json')):
            if budget(plan) < 1:
                raise PilotBlocked('discovery pages without spent budget')
    else:
        stage = _checked(_dir(root, plan['cabinet'], plan['year'], plan['report_id'], plan['report_type']))
        if stage.exists() and any(stage.iterdir()):
            count = budget(plan)
            state = _read_json(stage / 'state.json', required=True)
            _validate_state(state, plan['cabinet'], plan['year'], plan['report_id'], plan['report_type'])
            _verify_pages(stage, state, plan['report_id'], plan['report_type'])
            minimum = len(state['pages']) + (state['status'] == 'STAGED_COMPLETE')
            if count < minimum:
                raise PilotBlocked('staged pages exceed original sealed budget')
    return counts.get(_digest(plan), 0)

def failure_location(exc):
    frames=[];tb=exc.__traceback__
    while tb is not None:
        code=tb.tb_frame.f_code
        frames.append({'file':Path(code.co_filename).name,'function':code.co_name,'line':tb.tb_lineno})
        tb=tb.tb_next
    # Only fixed local classifications. Never export arbitrary exception messages.
    reasons={'non-increasing or duplicated WB rrdId':'WB_CURSOR_SEQUENCE_INVALID',
             'WB detail report type mismatch':'WB_REPORT_TYPE_MISMATCH',
             'foreign WB reportId in staged page':'WB_REPORT_ID_MISMATCH',
             'WB staged page payload checksum mismatch':'WB_RESPONSE_CHECKSUM_MISMATCH',
             'staged cursor file already exists':'WB_CURSOR_FILE_CONFLICT'}
    return {'error_type':type(exc).__name__,'errno':getattr(exc,'errno',None),
            'code':reasons.get(str(exc),'LOCAL_PROCESSING_FAILURE'),'frames':frames[-12:]}


KNOWN_REPAIR_PLAN_SHA256='dbdb4ea5ee55b2bf4f8c59d4efcf56db07a1ed7487f5c1b6c12232f9438b1ce2'
KNOWN_REPAIR_STATE_SHA256='abad7f67d570713cdee5f2f27a3ef160627362d8666e735a9c50564e2a4d5eb5'
KNOWN_REPAIR_RECEIPT_SHA256='db4033bc459beddcebd8649c11c63ca6d3fe7ad8aef9856eb8cabd8e24e3a711'

def _load_known_failure_receipt():
    path=Path('/var/lib/msp-finance-control/results/bb7f9919ee2a4a22b0bdc2a6f0a78645.json')
    _checked(path);st=path.stat()
    if st.st_uid!=0 or st.st_mode&0o022 or st.st_nlink!=1 or not stat.S_ISREG(st.st_mode) or st.st_size>65536:
        raise PilotBlocked('untrusted known failure receipt')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=KNOWN_REPAIR_RECEIPT_SHA256:
        raise PilotBlocked('known failure receipt changed')
    return json.loads(raw,object_pairs_hook=_strict)['jobs'][0]['outcome']['executor']

def recover_known_processing_hold(root,plan,state):
    """Owner-requested single recovery of ONE pinned legacy processing failure.

    Not a generic HOLD bypass. Original counter, all pages, cursor and cap stay.
    Another failure gets a new state digest and can never use this ticket again.
    """
    if (_digest(plan)!=KNOWN_REPAIR_PLAN_SHA256 or _digest(state)!=KNOWN_REPAIR_STATE_SHA256
            or state.get('processing_recovery') is not None):return False
    original=_load_known_failure_receipt()
    if _digest(original)!=KNOWN_REPAIR_STATE_SHA256 or original!=state:
        raise PilotBlocked('legacy repair state no longer matches recorded failure')
    reconcile_admission(root,plan)
    from .wb_page_resume import _dir,_read_json,_validate_state,_verify_pages
    stage=_dir(root,plan['cabinet'],plan['year'],plan['report_id'],plan['report_type'])
    page_state=_read_json(stage/'state.json',required=True)
    _validate_state(page_state,plan['cabinet'],plan['year'],plan['report_id'],plan['report_type'])
    _verify_pages(stage,page_state,plan['report_id'],plan['report_type'])
    if page_state['status']!='RUNNING' or len(page_state['pages'])!=1 or page_state['current_rrd_id']<=0:
        raise PilotBlocked('legacy repair requires exactly one verified retained page')
    attempts=unknown=0;statuses=[]
    for journal in sorted((Path(root)/'.wb-executor').glob('control-*-events.jsonl')):
        _checked(journal)
        with journal.open() as stream:
            for line in stream:
                event=json.loads(line,object_pairs_hook=_strict)
                if event.get('plan')!=plan:continue
                if event['event']=='HTTP_DISPATCH_ATTEMPT':attempts+=1
                elif event['event']=='HTTP_OUTCOME_UNKNOWN':unknown+=1
                elif event['event']=='HTTP_RESPONSE':statuses.append(event['status'])
    if attempts!=2 or statuses!=[200,200] or unknown:
        raise PilotBlocked('legacy repair HTTP evidence changed or uncertain')
    state['processing_recovery']={'original_state_sha256':KNOWN_REPAIR_STATE_SHA256,
                                 'original_receipt_sha256':KNOWN_REPAIR_RECEIPT_SHA256,
                                 'original_send_entries':2,'reason':'OWNER_REQUESTED_CAPTURED_RETRY'}
    state['status']='READY'
    return True


CAPTURED_HOLD_SHA256='bf7b0f8abb68e42e38b16f38315ccdef26d7e9905e3440d1e380bb30a32a3c35'
CAPTURED_RESPONSE_SHA256='185b1577e3ddd6d81bec8fcd89d0da6b423ee39026502891bc52b5e3d39a3f44'
CAPTURED_PREFIX_SHA256='d2aec1ff9adfcb0479e813f416b894b4ee50d497bc90e312bad3b95006be5985'

def recover_captured_processing_hold(root,plan,state):
    """Replay the exact investigated response under the corrected validation.

    This ticket admits NO transport. Original response, prefix and counter are
    cryptographically pinned. Another HOLD or changed evidence is not recoverable.
    """
    if _digest(plan)!=KNOWN_REPAIR_PLAN_SHA256 or _digest(state)!=CAPTURED_HOLD_SHA256:return False
    from .wb_page_resume import _dir,_read_json,_validate_state,_verify_pages,_validate_page,_unique_rows
    stage=_dir(root,plan['cabinet'],plan['year'],plan['report_id'],plan['report_type'])
    saved=_read_json(stage/'state.json',required=True)
    _validate_state(saved,plan['cabinet'],plan['year'],plan['report_id'],plan['report_type'])
    seen=_verify_pages(stage,saved,plan['report_id'],plan['report_type'])
    if len(saved['pages'])!=1 or saved['pages'][0]['sha256']!=CAPTURED_PREFIX_SHA256:
        raise PilotBlocked('captured recovery prefix changed')
    pending=stage/('response-'+str(saved['current_rrd_id'])+'.json')
    page,raw=_read_json(pending,required=True,with_bytes=True)
    if hashlib.sha256(raw).hexdigest()!=CAPTURED_RESPONSE_SHA256:raise PilotBlocked('captured response changed')
    _validate_page(page,plan['report_id'],plan['report_type'],saved['current_rrd_id'])
    _unique_rows(page,seen)
    attempts=0;statuses=[];unknown=0
    for journal in sorted((Path(root)/'.wb-executor').glob('control-*-events.jsonl')):
        _checked(journal)
        with journal.open() as stream:
            for line in stream:
                event=json.loads(line,object_pairs_hook=_strict)
                if event.get('plan')!=plan:continue
                if event['event']=='HTTP_DISPATCH_ATTEMPT':attempts+=1
                elif event['event']=='HTTP_RESPONSE':statuses.append(event['status'])
                elif event['event']=='HTTP_OUTCOME_UNKNOWN':unknown+=1
    if attempts!=3 or statuses!=[200,200,200] or unknown:raise PilotBlocked('captured recovery HTTP evidence changed')
    state['local_response_replay']={'prior_state_sha256':CAPTURED_HOLD_SHA256,
        'response_sha256':CAPTURED_RESPONSE_SHA256,'prefix_sha256':CAPTURED_PREFIX_SHA256,
        'original_send_entries':3,'provider_calls':0}
    state['status']='READY'
    return True


def verify_captured_replay_ticket(root,plan,state):
    ticket=state.get('local_response_replay')
    if ticket is None:return False
    expected={'prior_state_sha256':CAPTURED_HOLD_SHA256,'response_sha256':CAPTURED_RESPONSE_SHA256,
              'prefix_sha256':CAPTURED_PREFIX_SHA256,'original_send_entries':3,'provider_calls':0}
    if _digest(plan)!=KNOWN_REPAIR_PLAN_SHA256 or ticket!=expected:
        raise PilotBlocked('captured replay ticket changed')
    from .wb_page_resume import _dir,_read_json,_validate_state,_validate_page
    stage=_dir(root,plan['cabinet'],plan['year'],plan['report_id'],plan['report_type'])
    saved=_read_json(stage/'state.json',required=True)
    _validate_state(saved,plan['cabinet'],plan['year'],plan['report_id'],plan['report_type'])
    original_cursor=3111429097937
    page,raw=_read_json(stage/('response-'+str(original_cursor)+'.json'),required=True,with_bytes=True)
    if hashlib.sha256(raw).hexdigest()!=CAPTURED_RESPONSE_SHA256:
        raise PilotBlocked('captured response lost or changed after recovery')
    _validate_page(page,plan['report_id'],plan['report_type'],original_cursor)
    # A crash after arming but before cursor acknowledgement must still replay
    # locally, never invoke transport if the retained response disappears.
    return saved['current_rrd_id']==original_cursor


CURSOR_HOLD_SHA256='c68ac57cf52dc2315d5305840b880dfd399cdd3063db08f6721ed796fdfd1489'
CURSOR_ROWS_PROFILE_SHA256='94c7a7e3cb0a60de0eb86ba6ea12b6185fb65d94a139bfa26f66ed3ead5881fc'

def recover_cursor_policy_hold(root,plan,state):
    """One migration of the diagnosed four-entry HOLD, never a generic retry.

    Replay ONLY the checksum-verified response, after current chain/conflict/cycle
    validation and all-nonce reconciliation. Preserve all bytes and spent entries.
    """
    if _digest(plan)!=KNOWN_REPAIR_PLAN_SHA256 or _digest(state)!=CURSOR_HOLD_SHA256:return False
    if state.get('send_entries')!=4 or state.get('failure',{}).get('code')!='WB_CURSOR_SEQUENCE_INVALID':
        raise PilotBlocked('unexpected cursor-policy migration evidence')
    from .wb_page_resume import _dir,_read_json,_validate_state,_verify_pages,_validate_page,_validate_next_cursor,_unique_rows
    stage=_dir(root,plan['cabinet'],plan['year'],plan['report_id'],plan['report_type'])
    saved=_read_json(stage/'state.json',required=True)
    _validate_state(saved,plan['cabinet'],plan['year'],plan['report_id'],plan['report_type'])
    seen=_verify_pages(stage,saved,plan['report_id'],plan['report_type'])
    if saved['status']!='RUNNING' or len(saved['pages'])!=2:raise PilotBlocked('cursor-policy prefix changed')
    page,raw=_read_json(stage/('response-'+str(saved['current_rrd_id'])+'.json'),required=True,with_bytes=True)
    next_id=_validate_page(page,plan['report_id'],plan['report_type'],saved['current_rrd_id'])
    profile=[{'rrdId':r['rrdId'],'row_sha256':_digest(r)} for r in page['rows']]
    if _digest(profile)!=CURSOR_ROWS_PROFILE_SHA256:raise PilotBlocked('cursor-policy response differs from protected diagnostic')
    _validate_next_cursor(saved,next_id);_unique_rows(page,seen)
    events=[]
    for journal in sorted((Path(root)/'.wb-executor').glob('control-*-events.jsonl')):
        _checked(journal)
        events.extend(json.loads(line,object_pairs_hook=_strict) for line in journal.read_text().splitlines())
    events=[event for event in events if event.get('plan')==plan]
    if (sum(e['event']=='HTTP_DISPATCH_ATTEMPT' for e in events)!=4 or
            [e['status'] for e in events if e['event']=='HTTP_RESPONSE']!=[200]*4 or
            any(e['event']=='HTTP_OUTCOME_UNKNOWN' for e in events)):
        raise PilotBlocked('cursor-policy HTTP evidence changed or uncertain')
    state['cursor_policy_replay']={'prior_state_sha256':CURSOR_HOLD_SHA256,
        'response_sha256':hashlib.sha256(raw).hexdigest(),'cursor':saved['current_rrd_id'],
        'prefix_sha256':[p['sha256'] for p in saved['pages']],
        'original_send_entries':4,'provider_calls':0}
    state['status']='READY'
    return True

def verify_cursor_policy_ticket(root,plan,state):
    ticket=state.get('cursor_policy_replay')
    if ticket is None:return False
    if (_digest(plan)!=KNOWN_REPAIR_PLAN_SHA256 or type(ticket) is not dict or
            set(ticket)!={'prior_state_sha256','response_sha256','cursor','prefix_sha256','original_send_entries','provider_calls'} or
            ticket['prior_state_sha256']!=CURSOR_HOLD_SHA256 or ticket['original_send_entries']!=4 or
            ticket['provider_calls']!=0 or type(ticket['cursor']) is not int or ticket['cursor']<=0):
        raise PilotBlocked('cursor-policy replay ticket changed')
    from .wb_page_resume import _dir,_read_json,_validate_state,_validate_page
    stage=_dir(root,plan['cabinet'],plan['year'],plan['report_id'],plan['report_type'])
    saved=_read_json(stage/'state.json',required=True)
    _validate_state(saved,plan['cabinet'],plan['year'],plan['report_id'],plan['report_type'])
    if [p['sha256'] for p in saved['pages'][:2]]!=ticket['prefix_sha256']:
        raise PilotBlocked('cursor-policy replay prefix changed')
    page,raw=_read_json(stage/('response-'+str(ticket['cursor'])+'.json'),required=True,with_bytes=True)
    if hashlib.sha256(raw).hexdigest()!=ticket['response_sha256']:raise PilotBlocked('cursor-policy retained response changed')
    _validate_page(page,plan['report_id'],plan['report_type'],ticket['cursor'])
    return saved['current_rrd_id']==ticket['cursor']


def run_step(root, plan, authorization, factory, *, now=None, fault=None, admission_ceiling=None, policy_sha256=None, processing_recovery=False):
    """One adapter step. Injected factory is for offline tests or approved HTTP.

    Budget counts durable sender entries, not proven HTTPs; a crash or quota
    refusal may consume an entry conservatively. It is NEVER reset on retry.
    """
    now = time.time() if now is None else now
    validate_plan(plan)
    ceiling=plan['max_send_entries'] if admission_ceiling is None else admission_ceiling
    if type(ceiling) is not int or not plan['max_send_entries']<=ceiling<=1000:
        raise PilotBlocked('invalid cumulative admission ceiling')
    if ceiling>plan['max_send_entries'] and (not isinstance(policy_sha256,str) or len(policy_sha256)!=64 or any(c not in '0123456789abcdef' for c in policy_sha256)):
        raise PilotBlocked('root policy digest required for monotonic admission extension')
    validate_authorization(authorization, plan, root, now)
    root = Path(root)
    if not _checked(root).is_dir():
        raise PilotBlocked('archive root must be provisioned before execution')
    reconcile_admission(root, plan)
    key = _digest(plan)
    # A common local owner across cabinets/types. Not a cross-host Redis lease.
    with _lock(root, 'standalone', 'wb_executor'):
        folder = _checked(root / '.wb-executor')
        _ensure_scope_durable(folder)
        os.chmod(folder, 0o700)
        path = folder / (key + '.json')
        if path.exists() or path.is_symlink():
            state = read_control(path)
            if type(state) is not dict:
                raise PilotBlocked('executor journal must be an object')
            checksum = state.pop('state_sha256', None)
            if checksum != _digest(state):
                raise PilotBlocked('executor journal checksum mismatch; do not re-seal')
            if (type(state) is not dict or type(state.get('schema')) is not int or state['schema'] != 1
                    or state.get('plan_sha256') != key or type(state.get('send_entries')) is not int
                    or not 0 <= state['send_entries'] <= ceiling
                    or state.get('status') not in ('READY','DISPATCH_UNCERTAIN','WAITING_RATE_LIMIT',
                         'WAITING_RETRY','PAGE_STAGED','DONE','PAUSED_BUDGET','HOLD_ERROR')):
                raise PilotBlocked('executor journal invalid; do not reset')
            _resync(path)
        else:
            reconcile_admission(root, plan)
            state = {'schema':1,'plan_sha256':key,'send_entries':0,'status':'READY'}
            _safe_write(path, _encode({**state, 'state_sha256':_digest(state)}))
        def save():
            _safe_write(path, _encode({**state, 'state_sha256':_digest(state)}))
        prior_cap=state.get('approved_total_entries',plan['max_send_entries'])
        if type(prior_cap) is not int or prior_cap>ceiling:
            raise PilotBlocked('admission ceiling cannot decrease; reconcile policy')
        if ceiling!=prior_cap:
            state['admission_extension']={'from':prior_cap,'to':ceiling,'prior_state_sha256':_digest(state),'policy_sha256':policy_sha256}
            state['approved_total_entries']=ceiling
            save() # Same plan path/cursor/counter; never a replacement budget.

        replay_only=False
        if state['status'] == 'HOLD_ERROR':
            if recover_cursor_policy_hold(root,plan,state):
                replay_only=True;save()
            elif recover_captured_processing_hold(root,plan,state):
                replay_only=True;save()
            elif processing_recovery and recover_known_processing_hold(root,plan,state):save()
            else:return dict(state)
        replay_only=verify_cursor_policy_ticket(root,plan,state) or verify_captured_replay_ticket(root,plan,state) or replay_only
        until = state.get('not_before_epoch', 0)
        if type(until) not in (int,float) or not math.isfinite(until) or until < 0:
            raise PilotBlocked('invalid executor not-before; do not reset')
        if until > now:
            return dict(state)
        sender = None
        def guarded_send(request):
            nonlocal sender
            if replay_only:raise PilotBlocked('captured recovery is local replay only; no new sender entry')
            if state['status'] == 'DONE':
                raise PilotBlocked('completed journal must reconcile without new download')
            if state['send_entries'] >= ceiling:
                raise BudgetPause()
            reconcile_admission(root, plan)
            state['send_entries'] += 1
            state['status'] = 'DISPATCH_UNCERTAIN'
            state.pop('not_before_epoch', None)
            save()  # Failure => no factory, quota reservation or HTTP.
            if fault:
                fault('after_budget_before_sender')
            if sender is None:
                sender = factory()
            return sender(request)
        try:
            outcome = run_one_step(root, plan['cabinet'], plan['year'], plan['report_id'],
                                   plan['report_type'], guarded_send)
        except BudgetPause:
            state['status'] = 'PAUSED_BUDGET'
            save()
            return dict(state)
        except TransportUnavailable:
            state.update(status='WAITING_RETRY', not_before_epoch=now+66)
            save()
            return dict(state)
        except (GenerationError, ProviderError, ValueError, OSError) as exc:
            state.update(status='HOLD_ERROR', error_type=type(exc).__name__, failure=failure_location(exc))
            save()
            return dict(state)
        status = outcome['status']
        if status == 'WAITING_RATE_LIMIT':
            instant = datetime.fromisoformat(outcome['not_before_utc'])
            if instant.tzinfo is None:
                raise PilotBlocked('timezone required')
            state.update(status=status, not_before_epoch=max(instant.timestamp(),now+outcome['retry_after_seconds']))
        elif status == 'PAGE_STAGED':
            state.update(status=status, not_before_epoch=now+WB_PAGE_PAUSE_SECONDS)
        elif status == 'LOCAL_VERIFIED_NOT_PROVIDER_COMPLETE':
            state.update(status='DONE', generation=outcome['generation'],
                         manifest_sha256=outcome['manifest_sha256'], rows=outcome['rows'],
                         provider_coverage_proven=False)
            state.pop('not_before_epoch',None)
        else:
            raise PilotBlocked('unrecognized adapter status')
        save()
        return dict(state)

def run_bounded(root, plan, authorization, factory, *, clock=time.time, sleep=time.sleep):
    """Finish a small pilot autonomously, or return its durable paused state.

    No more than eight local reconciliation steps and 300 seconds of start/
    wait budget. One in-flight transport can outlast that start deadline;
    the proposed systemd watchdog is a separate outer bound. Long quota waits
    return to the supervisor instead of polling or occupying a daemon.
    """
    deadline = clock() + 300
    outcome = None
    for _ in range(8):
        if clock() >= deadline:
            break
        outcome = run_step(root, plan, authorization, factory, now=clock())
        if outcome['status'] in ('DONE','HOLD_ERROR','PAUSED_BUDGET'):
            return outcome
        until = outcome.get('not_before_epoch', clock())
        if until >= deadline:
            return outcome
        while clock() < until:
            sleep(min(60.0, until-clock()))
    return outcome

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--authorization-file', type=Path, required=True)
    p.add_argument('--creds-file', type=Path, required=True)
    p.add_argument('--one-step', action='store_true', help='future existing scheduler integration; no loop')
    args = p.parse_args(argv)
    plan = read_control(args.plan)
    auth = read_authorization(args.authorization_file)
    runner = run_step if args.one_step else run_bounded
    result = runner(args.root, plan, auth, lambda: ReadOnlyHTTP(
        cabinet=plan['cabinet'], credentials_file=args.creds_file, state_root=args.root))
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status']=='DONE' else 2

if __name__ == '__main__':
    raise SystemExit(main())
