"""Owner's WB schedule: daily3checks; Monday weekly10checks; interval20min."""
import datetime
from zoneinfo import ZoneInfo
TZ=ZoneInfo('Europe/Moscow')
CABINETS=('wb_dmitrieva','wb_laser_master','wb_novokshenov')
INTERVAL=1200
TERMINAL={'VERIFIED','WAITING_NEXT_RUN','HOLD'}
def make_job(cab,period,start,end,bootstrap=False):
    return {'key':'|'.join((cab,period,start,end)),'cabinet':cab,'period':period,'from':start,'to':end,'bootstrap':bootstrap,'attempts':0,'status':'PENDING','next_due':0,'max_attempts':1 if bootstrap else (10 if period=='weekly' else 3)}
def make_cycle(now,known,coverage,bootstrap=False):
    now=now.astimezone(TZ);today=now.date();yesterday=today-datetime.timedelta(days=1);jobs=[]
    if bootstrap:
        jobs=[make_job(c,'weekly','2025-12-29',yesterday.isoformat(),True) for c in CABINETS]
    else:
        monday=today-datetime.timedelta(days=today.weekday())
        if today.weekday()==0:
            for c in CABINETS:jobs.append(make_job(c,'weekly',(monday-datetime.timedelta(days=7)).isoformat(),yesterday.isoformat()))
        for c in CABINETS:
            # Coverage consists of actually published weekly documents, not an
            # assumed Monday watermark; fragments and legal missing buyouts stay visible.
            latest=[]
            for typ in (1,2):
                dates=[datetime.date.fromisoformat(r['to']) for r in coverage.get(c,[]) if r['report_type']==typ]
                latest.append(max(dates) if dates else datetime.date(2025,12,31))
            day=max(datetime.date(2026,1,1),min(latest)+datetime.timedelta(days=1))
            while day<=yesterday:
                jobs.append(make_job(c,'daily',day.isoformat(),day.isoformat()));day+=datetime.timedelta(days=1)
    selected=[]
    for job in jobs:
        old=known.get(job['key'])
        if old and old['status']=='VERIFIED':continue
        if old and old['status']=='HOLD':job.update(status='HOLD',result=old)
        job['next_due']=now.timestamp();selected.append(job)
    return {'status':'RUNNING','created_at':now.isoformat(),'jobs':selected,'bootstrap':bootstrap,'through':yesterday.isoformat()}
def due_job(cycle,now):return next((j for j in cycle['jobs'] if j['status'] not in TERMINAL and j['next_due']<=now),None)
def settle(job,result,now):
    if (result.get('cabinet'),result.get('period'),result.get('date_from'),result.get('date_to'))!=(job['cabinet'],job['period'],job['from'],job['to']):raise ValueError('result scope')
    state=result.get('status')
    if state=='VERIFIED':job['status']='VERIFIED'
    elif state=='WAITING_DATA':job.update(status='WAITING_NEXT_RUN' if job['attempts']>=job['max_attempts'] else 'WAITING_DATA',next_due=now+INTERVAL)
    elif state=='HOLD':job['status']='HOLD'
    else:raise ValueError('unknown result state')
    job['result']=result
def status(cycle):
    states={j['status'] for j in cycle['jobs']}
    if states-TERMINAL:return 'WAITING_REPORTS' if states<=TERMINAL|{'WAITING_DATA'} else 'RUNNING'
    if 'HOLD' in states:return 'HOLD'
    return 'WAITING_NEXT_RUN' if 'WAITING_NEXT_RUN' in states else 'VERIFIED'
