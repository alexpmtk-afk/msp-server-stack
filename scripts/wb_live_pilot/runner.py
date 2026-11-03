"""One approved WB report through unchanged PR104, with redacted dispatch evidence."""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import urllib.error

RELEASE=Path('/opt/mcp/projects/msp-marketplace-reports-releases/c1fee070e9efa0c925a78f266fdf03cb12a173cf')
ARCHIVE=Path('/opt/mcp/data/msp-marketplace-reports')
EXPECTED_PATH='/api/finance/v1/sales-reports/detailed/883801632'
URL='https://finance-api.wildberries.ru'+EXPECTED_PATH


def emit_event(path,entry):
    """No URL query/header/token/body/response content is ever journalled."""
    from apps.msp_marketplace_reports.wb_page_resume import _checked
    _checked(path)
    fd=os.open(path,os.O_WRONLY|os.O_APPEND|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        st=os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid!=os.geteuid() or st.st_nlink!=1:raise ValueError('unsafe event journal')
        with os.fdopen(fd,'a',closefd=False) as f:
            f.write(json.dumps(entry,sort_keys=True)+'\n');f.flush();os.fchmod(fd,0o600);os.fsync(fd)
    finally:os.close(fd)


def validate_response(status,rows):
    if status==204:return
    if status!=200:return  # existing PR104 handles errors/cooldown/STOP.
    if type(rows) is not list or not rows:raise ValueError('invalid pilot response shape')
    for r in rows:
        if (type(r) is not dict or type(r.get('reportId')) is not int or r['reportId']!=883801632
            or type(r.get('reportType')) is not int or r['reportType']!=1
            or type(r.get('rrdId')) is not int or r['rrdId']<=0):
            raise ValueError('pilot response identity mismatch')


class AuditedOpener:
    def __init__(self,inner,path):self.inner=inner;self.path=path
    def open(self,request,timeout):
        if request.full_url!=URL or request.get_method()!='POST':raise ValueError('fixed pilot endpoint required')
        body=json.loads(request.data)
        if set(body)!={'limit','rrdId'} or type(body['limit']) is not int or body['limit']!=1000 or type(body['rrdId']) is not int or body['rrdId']<0:raise ValueError('fixed pilot request required')
        entry={'event':'HTTP_DISPATCH_ATTEMPT','rrdId':body['rrdId']}
        emit_event(self.path,entry)  # after accepted quota, BEFORE HTTP.
        try:
            response=self.inner.open(request,timeout=timeout)
        except urllib.error.HTTPError as exc:
            emit_event(self.path,{'event':'HTTP_RESPONSE','status':int(exc.code)})
            raise
        except Exception as exc:
            emit_event(self.path,{'event':'HTTP_OUTCOME_UNKNOWN','error_type':type(exc).__name__})
            raise
        emit_event(self.path,{'event':'HTTP_RESPONSE','status':int(response.status)})
        return response


def main(*,expected_uid=995):
    if os.geteuid()!=expected_uid:raise ValueError('existing msp-reports required')
    sys.path.insert(0,str(RELEASE))
    from apps.msp_marketplace_reports import standalone_wb as s
    from apps.msp_marketplace_reports.runtime import ReadOnlyHTTP
    from apps.msp_marketplace_reports.wb_page_resume import _dir,_read_json,_validate_state,_verify_pages
    plan=s.read_control(RELEASE/'pilot-plan.json')
    if plan!={'schema':1,'cabinet':'wb_laser_master','year':2026,'report_id':883801632,'report_type':1,'max_send_entries':3}:raise ValueError('pilot plan drift')
    auth=s.read_authorization('/etc/msp-marketplace-reports-executor/approval.json')
    events=ARCHIVE/'.wb-executor'/'E-883801632-events.jsonl'
    class Sender(ReadOnlyHTTP):
        def __call__(self,request):
            if request.path!=EXPECTED_PATH or request.marketplace!='wb':raise ValueError('pilot report scope')
            result=super().__call__(request)
            validate_response(*result)
            return result
    def factory():
        cred=Path(os.environ['CREDENTIALS_DIRECTORY'])/'cabinets.json'
        sender=Sender(cabinet='wb_laser_master',credentials_file=cred,state_root=ARCHIVE)
        sender.opener=AuditedOpener(sender.opener,events)
        return sender
    outcome=s.run_bounded(ARCHIVE,plan,auth,factory)
    folder=_dir(ARCHIVE,'wb_laser_master',2026,883801632,1)
    page_state=_read_json(folder/'state.json')
    summary={'executor':outcome,'report_id':883801632,'report_type':1,'cabinet':'wb_laser_master'}
    if page_state:
        _validate_state(page_state,'wb_laser_master',2026,883801632,1);_verify_pages(folder,page_state,883801632,1)
        summary.update(pages=len(page_state['pages']),cursor=page_state['current_rrd_id'],
                       page_hashes=[p['sha256'] for p in page_state['pages']],
                       terminal=page_state['status']=='STAGED_COMPLETE',stage_path=str(folder),
                       rows_staged=sum(len(_read_json(folder/('page-'+str(p['cursor'])+'.json'),required=True)['rows']) for p in page_state['pages']))
        if page_state['status']=='STAGED_COMPLETE':
            from apps.msp_marketplace_reports.wb_worker_adapter import _read_coverage,_validate_coverage
            coverage=_read_coverage(folder);_validate_coverage(ARCHIVE,'wb_laser_master',2026,883801632,1,coverage)
            summary.update(rows=coverage['rows'],generation=coverage['generation'],manifest_sha256=coverage['manifest_sha256'],
                           report_detail_complete=True,financial_reconciliation_proven=False,
                           archive_scope=str(ARCHIVE/'.b7-generations/wb_weekly_finance_main/wb_laser_master/2026'),
                           published_generation_path=str(ARCHIVE/'.b7-generations/wb_weekly_finance_main/wb_laser_master/2026/generations'/coverage['generation']))
        else:summary['report_detail_complete']=False
    if events.exists():
        from apps.msp_marketplace_reports.wb_page_resume import _checked
        _checked(events)
        if events.stat().st_size>16384:raise ValueError('events oversized')
        values=[json.loads(line) for line in events.read_text().splitlines()]
        summary.update(http_dispatch_attempts_this_run=sum(v.get('event')=='HTTP_DISPATCH_ATTEMPT' for v in values),
                       http_response_statuses=[v['status'] for v in values if v.get('event')=='HTTP_RESPONSE'],
                       http_outcomes_unknown=sum(v.get('event')=='HTTP_OUTCOME_UNKNOWN' for v in values))
    else:
        summary.update(http_dispatch_attempts_this_run=0,http_response_statuses=[],http_outcomes_unknown=0)
    print(json.dumps(summary,sort_keys=True))
    return 0 if outcome['status']=='DONE' else 2

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({'wrapper_status':'STOP_OR_UNCERTAIN','error_type':type(exc).__name__}));raise SystemExit(1)
