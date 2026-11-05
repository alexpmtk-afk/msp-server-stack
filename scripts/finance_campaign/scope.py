"""Receipt-derived bounded campaign admission, not a queue or a sender."""
from datetime import date

def next_plan(receipt):
    if receipt.get('status')!='PASS' or receipt.get('api_enabled_after_run') is not False:raise ValueError('successful closed run required')
    outcome=receipt['outcome'];done=outcome['receipt']
    required={'verified':True,'terminal_http_status':204,'page_hashes_verified':True,'publication_verified':True,'report_id':883801636,'report_type':2,'rows':46}
    if any(type(done.get(k)) is not type(v) or done[k]!=v for k,v in required.items()) or outcome.get('report_detail_complete') is not True:raise ValueError('unconfirmed completed report')
    inv=outcome['discovery']
    if inv.get('cabinet')!='wb_laser_master' or inv.get('year')!=2026:raise ValueError('wrong discovery owner/year')
    items=[];seen=set()
    for row in inv['items']:
        rid=row['reportId'];kind=row['reportType'];start=date.fromisoformat(row['dateFrom'][:10]);end=date.fromisoformat(row['dateTo'][:10])
        if type(rid) is not int or rid<=0 or rid in seen or type(kind) is not int or kind not in (1,2) or not date(2026,1,1)<=start<=end<=date(2026,12,31):raise ValueError('invalid discovered identity')
        seen.add(rid)
        if rid in (883801632,883801636):continue
        items.append({'schema':1,'cabinet':'wb_laser_master','year':2026,'report_id':rid,'report_type':kind,'max_send_entries':3,'date_from':start.isoformat(),'date_to':end.isoformat()})
    items.sort(key=lambda r:(r['date_from'],r['report_type'],r['report_id']))
    if not items:raise ValueError('no next discovered report')
    return {'schema':1,'completed_excluded':[883801632,883801636],'next':items[0],
            'remaining_discovered':items,'coverage':'OCTOBER_DISCOVERY_ONLY_NOT_YEAR_COMPLETE',
            'other_cabinets':{'wb_novokshenov':'DISCOVERY_REQUIRED','wb_dmitrieva':'DISCOVERY_REQUIRED'},
            'year_windows':'2026-01-01_THROUGH_LAST_AVAILABLE_CLOSED_PERIOD','daily_enabled':False}

def admit_wake(request,policy):
    """Unprivileged wake can select existing admission, never expand root policy.
    Policy loading/root path validation and systemd authorization are separate.
    This function deliberately does not start/enable a unit or touch quotas.
    """
    if type(request) is not dict or set(request)!={'campaign_id','max_entries'}:raise ValueError('fixed wake fields required')
    if request['campaign_id'] not in policy.get('campaign_ids',[]):raise ValueError('campaign not root-approved')
    n=request['max_entries'];cap=policy.get('max_wake_entries')
    if type(n) is not int or type(cap) is not int or not 1<=n<=cap:raise ValueError('bounded wake required')
    return dict(request)

def admit_ozon_method(evidence,method):
    """Version announcements cannot substitute complete current schema acceptance."""
    required={'official_schema_verified':True,'pagination_verified':True,'terminal_verified':True,'method_quota_verified':True,'period_and_row_identity_verified':True}
    if evidence.get('method')!=method or any(evidence.get(k) is not v for k,v in required.items()):raise ValueError('Ozon exact-method contract not yet verified')
    if method!='/v1/finance/realization/posting':raise ValueError('first FINAL pilot only')
    return {'cabinet':'ozon_laser_master','method':method,'year':2026,'month':10,'max_send_entries':1}
