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

def run_step(root, plan, authorization, factory, *, now=None, fault=None, admission_ceiling=None, policy_sha256=None):
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

        if state['status'] == 'HOLD_ERROR':
            return dict(state)
        until = state.get('not_before_epoch', 0)
        if type(until) not in (int,float) or not math.isfinite(until) or until < 0:
            raise PilotBlocked('invalid executor not-before; do not reset')
        if until > now:
            return dict(state)
        sender = None
        def guarded_send(request):
            nonlocal sender
            if state['status'] == 'DONE':
                raise PilotBlocked('completed journal must reconcile without new download')
            if state['send_entries'] >= ceiling:
                raise BudgetPause()
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
            state.update(status='HOLD_ERROR', error_type=type(exc).__name__)
            save()
            return dict(state)
        status = outcome['status']
        if status == 'WAITING_RATE_LIMIT':
            instant = datetime.fromisoformat(outcome['not_before_utc'])
            if instant.tzinfo is None:
                raise PilotBlocked('timezone required')
            state.update(status=status, not_before_epoch=max(instant.timestamp(),now+outcome['retry_after_seconds']))
        elif status == 'PAGE_STAGED':
            state.update(status=status, not_before_epoch=now+66)
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
