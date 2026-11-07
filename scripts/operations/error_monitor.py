"""Local incident catalog, not an executor: never retries a business action.
Stable redacted output drives Hermes' existing monitor-mode cron scheduler.
"""
import argparse,fcntl,hashlib,json,os,re,subprocess,time
from pathlib import Path
STATE=Path('/home/hermes/.local/state/hermes-error-watch')
HOME=Path('/home/hermes/.hermes')
IGNORED_USER_UNITS={'msp-wb-history-driver.service':'superseded by scoped Laser Master campaign'}

def classify_log(text):
    codes=set(re.findall(r'\b[A-Z][A-Za-z]*(?:Error|Exception)\b',text))
    codes.update('HTTP_'+s for s in re.findall(r'\bHTTP[ /:]*(4\d\d|5\d\d)\b',text))
    return sorted(codes or ({'ERROR_LOG_EVENT'} if text.strip() else set()))

def reconcile(state,events,now):
    incidents=state.setdefault('incidents',{});seen=set()
    for event in events:
        ident=hashlib.sha256((event['source']+'\0'+event['code']).encode()).hexdigest()[:20];seen.add(ident)
        item=incidents.get(ident)
        if item is None or item.get('status')=='resolved':
            item={'id':ident,'source':event['source'],'code':event['code'],'status':'open','first_seen':now,'remediation':'pending'};incidents[ident]=item
        if item.get('remediation')=='resolved' and not event['source'].startswith(('hermes_log:','journal:')):item['remediation']='pending'
        item['details']=event.get('details',{});item['last_seen']=now
    for ident,item in incidents.items():
        if ident not in seen and item['status']=='open':item.update(status='resolved',resolved_at=now)
    opened=sorted(i for i,x in incidents.items() if x['status']=='open')
    blocked=sorted(i for i in opened if incidents[i].get('remediation')=='blocked_external')
    actionable=[{'id':i,'source':incidents[i]['source'],'code':incidents[i]['code'],
                 'retry_round':min(3,int(max(0,now-incidents[i]['first_seen'])//600))}
                for i in opened if i not in blocked and incidents[i].get('remediation')!='resolved']
    return {'open':opened,'blocked':blocked,'actionable':actionable}

def collect(state,run=subprocess.run):
    events=[]
    for scope,flags in [('user',['--user']),('system',[])]:
        try:
            p=run(['/usr/bin/systemctl',*flags,'list-units','--type=service','--state=failed','--all','--no-pager','--output=json'],capture_output=True,text=True,timeout=12)
            if p.returncode:raise RuntimeError('systemd read failed')
            for unit in json.loads(p.stdout):
                name=unit['unit']
                if scope=='user' and name in IGNORED_USER_UNITS:continue
                events.append({'source':scope+':'+name,'code':'SERVICE_FAILED','details':{'unit':name,'load':unit['load']}})
        except Exception as exc:events.append({'source':'collector:'+scope,'code':type(exc).__name__,'details':{}})
    cron=HOME/'cron/jobs.json'
    try:
        for job in json.loads(cron.read_text()).get('jobs',[]):
            status=job.get('last_status')
            if job.get('enabled') and status not in (None,'ok','delivery_queued','running','no_change'):
                events.append({'source':'cron:'+job['id'],'code':'CRON_'+str(status).upper(),'details':{'job_id':job['id']}})
    except Exception as exc:events.append({'source':'collector:cron','code':type(exc).__name__,'details':{}})
    campaign=Path('/home/hermes/.local/state/msp-finance-history-wb-laser-master-20261106/state.json')
    if campaign.exists():
        try:
            v=json.loads(campaign.read_text())
            if v.get('phase')=='HOLD':events.append({'source':'finance:wb_laser_master','code':'CAMPAIGN_HOLD','details':{'reason':v.get('reason'),'failure':v.get('failure'),'state':str(campaign)}})
        except Exception as exc:events.append({'source':'collector:finance','code':type(exc).__name__,'details':{}})
    try:
        since=str(int(state.get('last_collection_epoch',time.time())))
        p=run(['/usr/bin/journalctl','--user','--priority=err','--since=@'+since,'-n','100','--output=json','--no-pager'],capture_output=True,text=True,timeout=12)
        if p.returncode:raise RuntimeError('user journal read failed')
        for line in p.stdout.splitlines():
            value=json.loads(line);unit=value.get('_SYSTEMD_USER_UNIT',value.get('USER_UNIT','user-session'))
            if unit in IGNORED_USER_UNITS:continue
            for code in classify_log(str(value.get('MESSAGE',''))):
                events.append({'source':'journal:'+unit+':'+code,'code':code,'details':{'unit':unit,'journal':'user','cursor':value.get('__CURSOR')}})
    except Exception as exc:events.append({'source':'collector:journal','code':type(exc).__name__,'details':{}})
    offsets=state.setdefault('log_offsets',{})
    for name in ('errors.log',):
        p=HOME/'logs'/name
        if not p.exists():continue
        st=p.stat();prior=offsets.get(name)
        # Start at EOF on first install: do not reinterpret historical errors as new.
        start=st.st_size if prior is None else (prior['offset'] if prior['inode']==st.st_ino and prior['offset']<=st.st_size else 0)
        with p.open('rb') as stream:stream.seek(start);raw=stream.read(256*1024);end=stream.tell()
        offsets[name]={'inode':st.st_ino,'offset':end}
        for code in classify_log(raw.decode('utf-8','replace')):
            events.append({'source':'hermes_log:'+name+':'+code,'code':code,'details':{'file':str(p),'offset':start}})
    # Log incidents require explicit verified remediation; disappearance of the
    # line from the next tail is not recovery. Service faults are state-based.
    sources={e['source'] for e in events}
    for item in state.get('incidents',{}).values():
        if item['status']=='open' and item['source'].startswith(('hermes_log:','journal:')) and item.get('remediation')!='resolved' and item['source'] not in sources:
            events.append({k:item[k] for k in ('source','code','details')})
    return events

def write(path,value):
    tmp=path.with_suffix('.new');raw=(json.dumps(value,sort_keys=True,ensure_ascii=False)+'\n').encode()
    fd=os.open(tmp,os.O_CREAT|os.O_TRUNC|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
    os.replace(tmp,path);fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)

def main():
    p=argparse.ArgumentParser();p.add_argument('--quiet',action='store_true');p.add_argument('--mark',nargs=2,metavar=('ID','STATUS'));p.add_argument('--evidence',default='');a=p.parse_args()
    STATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (STATE/'monitor.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX);path=STATE/'incidents.json';state=json.loads(path.read_text()) if path.exists() else {'schema':1,'incidents':{}}
        if a.mark:
            ident,status=a.mark
            if status not in ('resolved','blocked_external','investigating'):raise ValueError('invalid remediation status')
            if not a.evidence:raise ValueError('verified evidence required')
            state['incidents'][ident].update(remediation=status,evidence=a.evidence[:1000])
        events=collect(state);summary=reconcile(state,events,time.time());state['last_collection_epoch']=time.time();write(path,state)
        if not a.quiet:print(json.dumps(summary,sort_keys=True,separators=(',',':')))
if __name__=='__main__':main()
