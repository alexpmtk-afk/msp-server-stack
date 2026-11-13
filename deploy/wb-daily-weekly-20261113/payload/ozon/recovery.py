"""Deterministic recovery primitives: retained responses, bounded reconciliation."""
import hashlib,json,stat,time
from pathlib import Path
class Paused(RuntimeError):pass
class StartNotificationLost(RuntimeError):pass

def read_checked(path):
    s=path.lstat()
    if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or s.st_mode&0o022:raise ValueError('unsafe retained inode')
    return path.read_bytes()

def retained_page(daydir,index,cabinet,day,cursor):
    stem=Path(daydir)/f'{index:03d}'
    paths=[stem.with_suffix(s) for s in ('.entry.json','.response.json','.meta.json')]
    exists=[p.exists() or p.is_symlink() for p in paths]
    if not any(exists):return None
    if not all(exists):raise ValueError('unknown response outcome or partial durable response; HOLD')
    entry=json.loads(read_checked(paths[0]));raw=read_checked(paths[1]);meta=json.loads(read_checked(paths[2]))
    if entry.get('cabinet')!=cabinet or entry.get('method')!='/v1/finance/accrual/by-day' or entry.get('body')!={'date':day,'last_id':cursor}:raise ValueError('retained entry scope')
    if meta.get('status')!=200 or meta.get('truncated') is not False or meta.get('sha256')!=hashlib.sha256(raw).hexdigest() or meta.get('bytes')!=len(raw):raise ValueError('retained response integrity/HTTP HOLD')
    issued=meta.get('received_epoch')
    if type(issued) not in (float,int) or issued<=0:raise ValueError('retained response timestamp')
    return raw,issued

def check_cursor_age(cursor,issued,*,now=None):
    if cursor and (issued is None or (time.time() if now is None else now)-issued>=840):raise ValueError('expired cursor; no automatic day restart')

def wait_worker(*,start,state,has_result,pause,sleeper=time.sleep,deadline):
    # A failed client notification does not mean the managed process has stopped.
    if has_result():return 'receipt'
    try:start()
    except Paused:raise
    except StartNotificationLost:pause('PAUSED_CONTROLLER_LINK')
    while time.time()<deadline:
        if has_result():return 'receipt'
        try:status=state()
        except Paused:raise
        except (OSError,ConnectionError):status='unavailable'
        if status in ('inactive','failed'):return 'reconcile'
        if status=='unavailable':pause('PAUSED_CONTROLLER_LINK')
        elif status not in ('active','activating','reloading'):raise ValueError('unknown executor state')
        sleeper(2)
    raise Paused('authorization deadline reached; reconcile owned process')

def reconcile_retained(worker):
    """Validate the complete existing budget and all saved pages before any HTTP."""
    completed={};numbers=[]
    for daydir in sorted(worker.STATE.iterdir()):
        if not daydir.is_dir():continue
        day=daydir.name
        if day != worker.DAY:raise ValueError('foreign retained day')
        stems={p.name.split('.')[0] for p in daydir.iterdir()}
        if any(not __import__('re').fullmatch('[0-9]{3}',s) for s in stems):raise ValueError('foreign retained page')
        indexes=sorted(int(s) for s in stems)
        if indexes!=list(range(1,len(indexes)+1)) or len(indexes)>worker.PAGE_LIMIT:raise ValueError('retained page gap/budget')
        rows=[];seen={};cursors=[];cursor='';pages=[];issued=None
        for index in indexes:
            raw,issued=retained_page(daydir,index,worker.CABINET,day,cursor)
            entry=json.loads(read_checked(daydir/f'{index:03d}.entry.json'));numbers.append(entry['send_entry_number'])
            parsed=worker.inspect_page(raw,day,input_cursor=cursor,prior_cursors=cursors,seen=seen)
            rows.extend(parsed['rows']);seen=parsed['seen']
            pages.append({'page':index,'rows':len(parsed['rows']),'sha256':worker.sha(raw),'origin':'new retained response','warnings':parsed['warnings']})
            if not parsed['last_id'] and index!=indexes[-1]:raise ValueError('page after terminal cursor')
            cursors.append(cursor);cursor=parsed['last_id']
        if indexes and not cursor:
            result={'date':day,'rows':rows,'pages':pages,'status':'CURSOR_EXHAUSTED_UNRECONCILED','provider_coverage_verified':False}
            summary=worker.STATE/(day+'.summary.json')
            if summary.exists():
                expected={k:v for k,v in result.items() if k!='rows'};expected['rows']=len(rows)
                if json.loads(read_checked(summary))!=expected:raise ValueError('retained summary conflict')
            completed[day]=result
        elif indexes:check_cursor_age(cursor,issued)
    if sorted(numbers)!=list(range(1,len(numbers)+1)) or len(numbers)>worker.BUDGET:raise ValueError('cumulative entry ledger mismatch')
    # A summary with no supporting source pages is not a completed day.
    if any(p.name.removesuffix('.summary.json') not in completed for p in worker.STATE.glob('*.summary.json')):raise ValueError('summary without source')
    return completed
