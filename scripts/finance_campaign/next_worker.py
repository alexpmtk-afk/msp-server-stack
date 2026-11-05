"""First historical vertical slice; sole installed executor, no second queue.
Fixed laser/October discovery + report865431404 type1, never accepted883801632.
"""
import json
import os
from pathlib import Path
import sys
import time
import stat
import urllib.error

ARCHIVE=Path('/opt/mcp/data/msp-marketplace-reports')
RELEASE=Path('__HISTORY_RELEASE__')
DISCOVERY={'schema':1,'kind':'wb-discovery','cabinet':'wb_laser_master','year':2026,
 'date_from':'2026-10-01','date_to':'2026-10-31','limit':1000,'max_send_entries':2}
DETAIL={'schema':1,'cabinet':'wb_laser_master','year':2026,'report_id':865431404,'report_type':1,'max_send_entries':3}
BATCH={'schema':1,'kind':'wb-history-next-865431404','discovery':DISCOVERY,'detail':DETAIL,'max_send_entries':5}

def event(path,value):
    from apps.msp_marketplace_reports.wb_page_resume import _checked
    _checked(path)
    fd=os.open(path,os.O_WRONLY|os.O_APPEND|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        st=os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid!=os.geteuid() or st.st_nlink!=1:raise ValueError('unsafe HTTP evidence')
        os.write(fd,(json.dumps(value,sort_keys=True)+'\n').encode());os.fchmod(fd,0o600);os.fsync(fd)
    finally:os.close(fd)

class AuditedOpener:
    def __init__(self,inner,path):self.inner=inner;self.path=path
    def open(self,request,timeout):
        allowed={'https://finance-api.wildberries.ru/api/finance/v1/sales-reports/list':'list',
                 'https://finance-api.wildberries.ru/api/finance/v1/sales-reports/detailed/865431404':'detail'}
        if request.get_method()!='POST' or request.full_url not in allowed:raise ValueError('fixed history endpoint required')
        event(self.path,{'event':'HTTP_DISPATCH_ATTEMPT','method_scope':allowed[request.full_url]})
        try:response=self.inner.open(request,timeout=timeout)
        except urllib.error.HTTPError as exc:
            event(self.path,{'event':'HTTP_RESPONSE','status':int(exc.code)});raise
        except Exception as exc:
            event(self.path,{'event':'HTTP_OUTCOME_UNKNOWN','error_type':type(exc).__name__});raise
        event(self.path,{'event':'HTTP_RESPONSE','status':int(response.status)})
        return response

def events(path):
    from apps.msp_marketplace_reports.wb_page_resume import _checked
    _checked(path)
    if not path.exists():return []
    if not path.is_file() or path.stat().st_size>32768 or path.stat().st_nlink!=1 or path.stat().st_uid!=os.geteuid():raise ValueError('unsafe event journal')
    return [json.loads(line) for line in path.read_text().splitlines()]

def reconcile_events(root,observed):
    from apps.msp_marketplace_reports import standalone_wb as s
    for kind,plan,prefix in [('list',DISCOVERY,'discovery-'),('detail',DETAIL,'')]:
        attempts=sum(v.get('event')=='HTTP_DISPATCH_ATTEMPT' and v.get('method_scope')==kind for v in observed)
        if not attempts:continue
        path=Path(root)/'.wb-executor'/(prefix+s._digest(plan)+'.json')
        state=s.read_control(path)  # Missing journal with HTTP evidence MUST NOT initialize a fresh budget.
        seal=state.pop('state_sha256',None);count=state.get('entries' if kind=='list' else 'send_entries')
        if seal!=s._digest(state) or state.get('plan_sha256')!=s._digest(plan) or type(count) is not int or not attempts<=count<=plan['max_send_entries']:
            raise ValueError('HTTP/budget evidence mismatch; never reset')

def execute(root,authorization,make_sender,*,clock=time.time,sleep=time.sleep,max_seconds=330):
    from apps.msp_marketplace_reports import standalone_wb as s
    from apps.msp_marketplace_reports import wb_discovery_resume as discovery
    from apps.msp_marketplace_reports.finance_receipts import report_receipt
    s.validate_authorization(authorization,BATCH,root,clock())
    # Actual business-value/hash check, not a hardcoded skip with no evidence.
    accepted=report_receipt(root,'wb_laser_master',2026,883801632,1)
    if not accepted.get('verified') or accepted.get('rows')!=841:
        raise ValueError('accepted pilot evidence requires reconciliation; never redownload it')
    previous_buyout=report_receipt(root,'wb_laser_master',2026,883801636,2)
    if not previous_buyout.get('verified') or previous_buyout.get('rows')!=46:
        raise ValueError('completed buyout requires reconciliation; never redownload it')
    def subauth(plan):return {**authorization,'plan_sha256':s._digest(plan)}
    before=clock();inventory=None
    def wait(until):
        delay=max(0,until-clock())
        if clock()+delay-before>=max_seconds:return False
        if delay:sleep(delay)
        return True
    # Local receipt replays do not enter sender. At most2 list +3 detail entries.
    for _ in range(16):
        if clock()-before>=max_seconds:break
        state=discovery.step(root,DISCOVERY,subauth(DISCOVERY),make_sender,now=clock())
        status=state['status']
        if status=='COMPLETE':
            inventory=discovery.read_inventory(root,[DISCOVERY]);inventory['budget_entries']=state['entries'];break
        if status in ('HOLD_ERROR','PAUSED_BUDGET'):
            return {'executor':{'status':status},'discovery':state,'report_detail_complete':False,'skipped_completed':[883801632,883801636]}
        if not wait(max(state.get('not_before_epoch',0),clock()+66 if state.get('provider_calls')==1 else 0)):break
    if inventory is None:
        return {'executor':{'status':'WAITING_RATE_LIMIT'},'report_detail_complete':False,'skipped_completed':[883801632,883801636]}
    selected=[r for r in inventory['items'] if r['reportId']==865431404]
    if len(selected)!=1 or selected[0]['reportType']!=1 or selected[0]['dateFrom'][:10]!='2026-10-01' or selected[0]['dateTo'][:10]!='2026-10-04':
        raise ValueError('approved next report not confirmed by discovery; no substitute ID')
    result=None
    from datetime import datetime
    list_safe_after=max(datetime.fromisoformat(value).timestamp()+66 for value in inventory['checked_at_per_window'])
    for _ in range(8):
        receipt=report_receipt(root,'wb_laser_master',2026,865431404,1)
        if receipt['status']=='HOLD_INVALID_LOCAL_EVIDENCE':raise ValueError('damaged archive; no redownload')
        if receipt.get('verified'):
            return {'executor':{'status':'DONE'},'report_detail_complete':True,'report_id':865431404,'report_type':1,
                    'receipt':receipt,'discovery':inventory,'skipped_completed':[883801632,883801636]}
        # After a list response use a full safety interval BEFORE reserving quota.
        if not wait(max(list_safe_after,(result or {}).get('not_before_epoch',0))):break
        result=s.run_step(root,DETAIL,subauth(DETAIL),make_sender,now=clock())
        if result['status'] in ('HOLD_ERROR','PAUSED_BUDGET'):
            return {'executor':result,'report_detail_complete':False,'discovery':inventory,'skipped_completed':[883801632,883801636]}
        if result['status']=='DONE':continue
        if result['status'] not in ('PAGE_STAGED','WAITING_RATE_LIMIT','WAITING_RETRY'):raise ValueError('unknown executor state')
    return {'executor':result or {'status':'WAITING_RATE_LIMIT'},'report_detail_complete':False,
            'discovery':inventory,'skipped_completed':[883801632,883801636]}

def main():
    if os.geteuid()!=995 or os.getegid()!=985:raise ValueError('msp-reports995:985 required')
    sys.path.insert(0,str(RELEASE))
    from apps.msp_marketplace_reports import standalone_wb as s
    from apps.msp_marketplace_reports.runtime import ReadOnlyHTTP
    from apps.msp_marketplace_reports.providers import WB_LIST
    auth=s.read_authorization('/etc/msp-marketplace-reports-executor/approval.json')
    s.validate_authorization(auth,BATCH,ARCHIVE,time.time())
    if sys.argv[1:]==['--check-approval-only']:
        print(json.dumps({'approval_read':'PASS','uid':995,'gid':985,'provider_calls':0}));return 0
    if sys.argv[1:]:raise ValueError('fixed historical batch only')
    # One original controller identity and lock. No direct urllib/API client.
    class Sender(ReadOnlyHTTP):
        def __call__(self,req):
            if req.marketplace!='wb':raise ValueError('WB only')
            if req.path==WB_LIST:
                expected={'dateFrom':DISCOVERY['date_from'],'dateTo':DISCOVERY['date_to'],'period':'weekly','limit':1000,'offset':req.body.get('offset')}
                if req.body!=expected or type(req.body.get('offset')) is not int or req.body['offset']<0:raise ValueError('fixed discovery scope')
            elif req.path=='/api/finance/v1/sales-reports/detailed/865431404':
                if set(req.body)!={'limit','rrdId'} or req.body['limit']!=1000 or type(req.body['rrdId']) is not int or req.body['rrdId']<0:raise ValueError('fixed detail scope')
            else:raise ValueError('unapproved report or endpoint')
            result=super().__call__(req)
            if req.path!=WB_LIST and result[0]==200:
                if type(result[1]) is not list or not result[1]:raise ValueError('invalid detail response')
                for r in result[1]:
                    if (type(r) is not dict or type(r.get('reportId')) is not int or r['reportId']!=865431404
                        or type(r.get('reportType')) is not int or r['reportType']!=1
                        or type(r.get('rrdId')) is not int or r['rrdId']<=0):raise ValueError('detail response identity')
            return result
    def factory():
        sender=Sender(cabinet='wb_laser_master',credentials_file=Path(os.environ['CREDENTIALS_DIRECTORY'])/'cabinets.json',state_root=ARCHIVE)
        sender.opener=AuditedOpener(sender.opener,journal)
        return sender
    journal=ARCHIVE/'.wb-executor/history-next-865431404-events.jsonl'
    previous_events=events(journal);reconcile_events(ARCHIVE,previous_events);previous=len(previous_events)
    outcome=execute(ARCHIVE,auth,factory)
    observed=events(journal)[previous:]
    outcome.update(http_dispatch_attempts_this_run=sum(v['event']=='HTTP_DISPATCH_ATTEMPT' for v in observed),
                   http_response_statuses=[v['status'] for v in observed if v['event']=='HTTP_RESPONSE'],
                   http_outcomes_unknown=sum(v['event']=='HTTP_OUTCOME_UNKNOWN' for v in observed))
    outcome['release']=str(RELEASE);outcome['batch_max_entries']=5
    print(json.dumps(outcome,sort_keys=True))
    return 0 if outcome['executor']['status']=='DONE' else 2

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({'error_type':type(exc).__name__,'wrapper_status':'STOP_OR_UNCERTAIN'}));raise SystemExit(1)
