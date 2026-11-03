"""Root recovery evidence gate; reads old private records and existing report state.
No state reset, chmod, API, Redis command or raw log/credential disclosure.
"""
import hashlib
import json
import os
from pathlib import Path
import stat

OLD_STATE=Path('/var/lib/msp-wb-E-883801632')
OLD_PUBLIC=Path('/opt/mcp/report-run-results/wb-883801632-E.json')
ARCHIVE=Path('/opt/mcp/data/msp-marketplace-reports')
OLD_RUNNER_SHA='ccaec90551d6414808d506661e6b7004e6814fd9d49225e0070762bd433529c2'

def raw(p,uid=0,limit=65536):
    from apps.msp_marketplace_reports.wb_page_resume import _checked
    _checked(p);st=p.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid!=uid or st.st_nlink!=1 or st.st_size>limit:raise ValueError('unsafe recovery evidence')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        data=os.read(fd,limit+1)
        if len(data)>limit:raise ValueError('oversized recovery evidence')
        return data
    finally:os.close(fd)

def inspect_failure(*,old_state=OLD_STATE,old_public=OLD_PUBLIC,archive=ARCHIVE,
                    evidence_uid=0,archive_uid=995,old_runner_sha=OLD_RUNNER_SHA,
                    program_parent=Path('/var/lib')):
    from apps.msp_marketplace_reports import standalone_wb as s
    from apps.msp_marketplace_reports.wb_page_resume import _dir,_read_json,_validate_state,_verify_pages
    from apps.msp_marketplace_reports.wb_worker_adapter import _read_coverage,_validate_coverage
    plan={'schema':1,'cabinet':'wb_laser_master','year':2026,'report_id':883801632,'report_type':1,'max_send_entries':3}
    private=json.loads(raw(old_state/'result.json',evidence_uid));public=json.loads(raw(old_public,evidence_uid))
    if private!=public or private.get('status')!='FAIL' or private.get('worker_exit')!=1 or private.get('api_enabled_after_run') is not False or private.get('outcome',{}).get('error_type')!='PermissionError':
        raise ValueError('different failure requires reconciliation')
    output=json.loads(raw(old_state/'worker-output.json',evidence_uid))
    if output!=private['outcome']:raise ValueError('private/public worker mismatch')
    stderr=raw(old_state/'worker-stderr.txt',evidence_uid)
    control=json.loads(raw(old_state/'controls.json',evidence_uid));program=Path(control['runner_path'])
    if program.parent.parent!=program_parent or not program.parent.name.startswith('msp-wb-E-program-') or program.name!='runner.py':raise ValueError('unexpected failed runner path')
    if hashlib.sha256(raw(program,evidence_uid)).hexdigest()!=old_runner_sha:raise ValueError('failed runner source differs')
    folder=_dir(archive,'wb_laser_master',2026,883801632,1)
    budget_path=archive/'.wb-executor'/(s._digest(plan)+'.json')
    events_path=archive/'.wb-executor/E-883801632-events.jsonl'
    stage_path=folder/'state.json';paths=[];budget=None
    for p in (budget_path,events_path,stage_path):
        if p.exists() or p.is_symlink():paths.append(p)
    if budget_path.exists():
        budget=json.loads(raw(budget_path,archive_uid));seal=budget.pop('state_sha256',None)
        if (seal!=s._digest(budget) or budget.get('plan_sha256')!=s._digest(plan)
            or type(budget.get('send_entries')) is not int or not 0<=budget['send_entries']<=3):raise ValueError('invalid preserved budget')
    state=_read_json(stage_path)
    if not state and folder.exists() and any(folder.iterdir()):
        raise ValueError('orphan staged files require reconciliation; no fresh cursor')
    if state:
        _validate_state(state,'wb_laser_master',2026,883801632,1);_verify_pages(folder,state,883801632,1)
        paths.extend(folder/('page-'+str(p['cursor'])+'.json') for p in state['pages'])
        if budget is None:raise ValueError('staging exists without budget; do not recreate counter')
        if state['status']=='STAGED_COMPLETE':
            coverage=_read_coverage(folder);_validate_coverage(archive,'wb_laser_master',2026,883801632,1,coverage)
            paths.extend(p for p in folder.iterdir() if p.is_file() and p not in paths)
    events=[]
    if events_path.exists():
        events=[json.loads(line) for line in raw(events_path,archive_uid,16384).splitlines()]
        if any(v.get('event') not in ('HTTP_DISPATCH_ATTEMPT','HTTP_RESPONSE','HTTP_OUTCOME_UNKNOWN') for v in events):raise ValueError('unknown event history')
        if budget is None:raise ValueError('HTTP evidence without budget; no inference of zero')
    attempts=sum(v.get('event')=='HTTP_DISPATCH_ATTEMPT' for v in events)
    if budget and attempts>budget['send_entries']:raise ValueError('HTTP attempts exceed preserved entries')
    snapshot={str(p):hashlib.sha256(raw(p,archive_uid,64*1024*1024)).hexdigest() for p in paths}
    return {'old_private_failure':'PermissionError','old_runner_sha256':old_runner_sha,
            'historical_exception_path_recorded':False,'old_stderr_bytes':len(stderr),
            'old_stdout_matches_public':True,'budget_entries_before_resume':budget['send_entries'] if budget else 0,
            'http_dispatch_attempts_observed_before_resume':attempts,
            'http_count_completeness':'NO_ACCEPTED_BUDGET_OR_EVENTS' if budget is None else 'EXISTING_JOURNAL_PRESERVED_NOT_RESET',
            'pages_before_resume':len(state['pages']) if state else 0,
            'cursor_before_resume':state['current_rrd_id'] if state else 0,
            'snapshots':snapshot}

def assert_preserved(snapshot,*,archive_uid=995):
    for name,digest in snapshot.items():
        if hashlib.sha256(raw(Path(name),archive_uid,64*1024*1024)).hexdigest()!=digest:
            raise ValueError('report state changed during read-only approval check')
