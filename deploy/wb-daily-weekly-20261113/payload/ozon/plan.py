"""Pure scheduling decisions, independent of transport and supervisor."""
import datetime
from zoneinfo import ZoneInfo
TZ=ZoneInfo('Europe/Moscow')
FIRST=datetime.date(2026,11,13)
CABINETS=('ozon_dmitrieva','ozon_novokshenov','ozon_laser_master')
INTERVAL=1200
MAX_ATTEMPTS=3
TERMINAL={'VERIFIED','WAITING_NEXT_DAY','HOLD'}

def eligible_day(now):
    now=now.astimezone(TZ)
    return now.date()-datetime.timedelta(days=1 if (now.hour,now.minute)>=(8,40) else 2)

def make_cycle(now,catalog,*,manual=None):
    now=now.astimezone(TZ);last=eligible_day(now)
    dates=[datetime.date.fromisoformat(manual['day'])] if manual else []
    if manual:
        last=dates[0]
        if not FIRST<=dates[0]<now.date():raise ValueError('manual past-day scope')
        cabinets=manual.get('cabinets',list(CABINETS))
        if not cabinets or len(cabinets)!=len(set(cabinets)) or any(c not in CABINETS for c in cabinets):raise ValueError('cabinet scope')
    else:
        cabinets=CABINETS;day=FIRST
        while day<=last:dates.append(day);day+=datetime.timedelta(days=1)
    jobs=[]
    for day in dates:
        for cabinet in cabinets:
            key=cabinet+'|'+day.isoformat();known=catalog.get(key,{})
            # An unsafe past attempt is NOT a missing report and cannot be reset
            # by a manual download request or tomorrow's timer.
            if known.get('status')=='VERIFIED':continue
            if known.get('status')=='HOLD':
                jobs.append(dict(key=key,cabinet=cabinet,day=day.isoformat(),status='HOLD',attempts=0,next_due=now.timestamp(),result=known.get('result',{})))
                continue
            jobs.append(dict(key=key,cabinet=cabinet,day=day.isoformat(),status='PENDING',attempts=0,next_due=now.timestamp()))
    return dict(status='RUNNING',created_at=now.isoformat(),business_through=last.isoformat(),jobs=jobs,max_attempts=1 if manual else MAX_ATTEMPTS,manual=bool(manual))

def due_job(cycle,now_epoch):
    return next((j for j in cycle['jobs'] if j['status'] not in TERMINAL and j['next_due']<=now_epoch),None)

def settle(job,result,now_epoch,max_attempts):
    if result.get('cabinet')!=job['cabinet'] or result.get('day')!=job['day']:raise ValueError('receipt scope')
    status=result.get('status')
    if status=='VERIFIED':job['status']='VERIFIED'
    elif status=='WAITING_DATA':
        job['status']='WAITING_NEXT_DAY' if job['attempts']>=max_attempts else 'WAITING_DATA'
        job['next_due']=now_epoch+INTERVAL
    elif status=='HOLD':job['status']='HOLD'
    else:raise ValueError('unknown worker state')
    job['result']=result

def cycle_status(cycle):
    states={j['status'] for j in cycle['jobs']}
    if states-set(TERMINAL):return 'WAITING_REPORTS' if states<=TERMINAL|{'WAITING_DATA'} else 'RUNNING'
    if 'HOLD' in states:return 'HOLD'
    if 'WAITING_NEXT_DAY' in states:return 'WAITING_NEXT_DAY'
    return 'VERIFIED'
