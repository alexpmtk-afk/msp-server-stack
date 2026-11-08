"""Only financial sender: runs as msp-reports INSIDE existing msp-wb-pilot.service."""
import hashlib,json,os,sys,time,stat,urllib.error
from pathlib import Path
ROOT=Path('__CONTROL_RELEASE__')
ARCHIVE=Path('/opt/mcp/data/msp-marketplace-reports')
ACTIVE=Path('/etc/msp-marketplace-reports-executor/control-active.json')
def record(path,value):
 from apps.msp_marketplace_reports.wb_page_resume import _checked
 _checked(path);fd=os.open(path,os.O_CREAT|os.O_APPEND|os.O_WRONLY|os.O_NOFOLLOW,0o600)
 try:
  st=os.fstat(fd)
  if not stat.S_ISREG(st.st_mode) or st.st_uid!=os.geteuid() or st.st_nlink!=1:raise ValueError('event path')
  os.write(fd,(json.dumps(value)+'\n').encode());os.fchmod(fd,0o600);os.fsync(fd)
 finally:os.close(fd)
class Audit:
 def __init__(self,inner,journal,url,plan):self.inner=inner;self.journal=journal;self.url=url;self.plan=plan
 def open(self,req,timeout):
  if req.full_url!=self.url or req.get_method()!='POST':raise ValueError('fixed root-approved HTTPS scope')
  from apps.msp_marketplace_reports import standalone_wb as s
  s.reconcile_admission(self.journal.parent.parent,self.plan)
  record(self.journal,{'event':'HTTP_DISPATCH_ATTEMPT','plan':self.plan})
  try:r=self.inner.open(req,timeout=timeout)
  except urllib.error.HTTPError as e:record(self.journal,{'event':'HTTP_RESPONSE','plan':self.plan,'status':int(e.code)});raise
  except Exception as e:record(self.journal,{'event':'HTTP_OUTCOME_UNKNOWN','plan':self.plan,'error_type':type(e).__name__});raise
  record(self.journal,{'event':'HTTP_RESPONSE','plan':self.plan,'status':int(r.status)});return r
def execute(root,plan,auth,factory,policy_sha,*,clock=time.time,sleep=time.sleep):
 from apps.msp_marketplace_reports.generation_store import verified_payload_cache
 with verified_payload_cache():
  return _execute(root,plan,auth,factory,policy_sha,clock=clock,sleep=sleep)

def _execute(root,plan,auth,factory,policy_sha,*,clock=time.time,sleep=time.sleep):
 from apps.msp_marketplace_reports import standalone_wb as s
 from apps.msp_marketplace_reports import wb_discovery_resume as d
 from apps.msp_marketplace_reports.finance_receipts import report_receipt
 s.validate_authorization(auth,plan,root,clock());s.reconcile_admission(root,plan);deadline=clock()+300
 if plan.get('kind')=='wb-discovery':
  out=d.step(root,plan,auth,factory,now=clock())
  if out['status']=='PAGE_STAGED_RECONCILE':out=d.step(root,plan,auth,lambda:(_ for _ in ()).throw(ValueError('replay only')),now=clock())
  return {'executor':{'status':'DONE' if out['status']=='COMPLETE' else ('HOLD_ERROR' if out['status']=='HOLD_ERROR' else 'PAUSED_BUDGET')},'discovery':out,'report_detail_complete':False}
 path=Path(root)/'.wb-executor'/(s._digest(plan)+'.json')
 prior=s.read_control(path) if path.exists() else {}
 baseline=prior.get('send_entries',0)
 repair_portion=(s._digest(plan)==s.KNOWN_REPAIR_PLAN_SHA256 and prior.get('status')=='HOLD_ERROR' and not prior.get('processing_recovery'))
 portion_limit=1 if repair_portion else 3
 outcome=None
 for _ in range(12):
  receipt=report_receipt(root,plan['cabinet'],2026,plan['report_id'],plan['report_type'])
  if receipt.get('verified'):return {'executor':{'status':'DONE'},'report_detail_complete':True,'receipt':receipt}
  if receipt['status']=='STAGED_PUBLICATION_PENDING':
   def no_sender():raise ValueError('local terminal publication must never use network')
   outcome=s.run_step(root,plan,auth,no_sender,now=clock(),admission_ceiling=1000,policy_sha256=policy_sha)
   verified=report_receipt(root,plan['cabinet'],2026,plan['report_id'],plan['report_type'])
   if not verified.get('verified'):raise ValueError('local publication did not verify; no refetch')
   return {'executor':{'status':'DONE'},'report_detail_complete':True,'receipt':verified,'local_publication_recovery':True}
  if receipt['status']=='HOLD_INVALID_LOCAL_EVIDENCE':raise ValueError('archive integrity HOLD; no refetch')
  count=s.read_control(path)['send_entries'] if path.exists() else 0
  if count-baseline>=portion_limit or clock()>=deadline:break
  until=(outcome or {}).get('not_before_epoch',0)
  if until>=deadline:break
  if until>clock():sleep(until-clock())
  outcome=s.run_step(root,plan,auth,factory,now=clock(),admission_ceiling=1000,policy_sha256=policy_sha,processing_recovery=repair_portion)
  if outcome['status'] in ('HOLD_ERROR','PAUSED_BUDGET'):break
 return {'executor':{**(outcome or {}),'status':'HOLD_ERROR' if (outcome or {}).get('status')=='HOLD_ERROR' else 'PAUSED_BUDGET'},'report_detail_complete':False,'wake_entries':(s.read_control(path)['send_entries']-baseline if path.exists() else 0)}
def main():
 if os.geteuid()!=995 or os.getegid()!=985:raise ValueError('fixed executor identity')
 sys.path.insert(0,str(ROOT))
 from apps.msp_marketplace_reports import standalone_wb as s
 from apps.msp_marketplace_reports.runtime import ReadOnlyHTTP
 from apps.msp_marketplace_reports.providers import WB_LIST,WB_DETAIL
 active=s.read_authorization(ACTIVE);plan=active['plan'];auth=s.read_authorization('/etc/msp-marketplace-reports-executor/approval.json')
 s.validate_authorization(auth,plan,ARCHIVE,time.time())
 if sys.argv[1:]==['--readcheck']:
  print(json.dumps({'uid':995,'gid':985,'approval_read':'PASS','provider_calls':0}));return 0
 if sys.argv[1:]:raise ValueError('no worker arguments')
 class Sender(ReadOnlyHTTP):
  def __call__(self,req):
   expected=WB_LIST if plan.get('kind')=='wb-discovery' else WB_DETAIL+str(plan['report_id'])
   if req.marketplace!='wb' or req.path!=expected:raise ValueError('fixed selected method/report')
   status,rows=super().__call__(req)
   if expected!=WB_LIST and status==200:
    if type(rows) is not list or not rows:raise ValueError('detail shape')
    for row in rows:
     if type(row.get('reportId')) is not int or row['reportId']!=plan['report_id'] or type(row.get('reportType')) is not int or row['reportType']!=plan['report_type'] or type(row.get('rrdId')) is not int or row['rrdId']<=0:raise ValueError('detail identity')
   return status,rows
 journal=ARCHIVE/'.wb-executor'/('control-'+active['run_id']+'-events.jsonl')
 def factory():
  sender=Sender(cabinet=plan['cabinet'],credentials_file=Path(os.environ['CREDENTIALS_DIRECTORY'])/'cabinets.json',state_root=ARCHIVE)
  path=WB_LIST if plan.get('kind')=='wb-discovery' else WB_DETAIL+str(plan['report_id'])
  sender.opener=Audit(sender.opener,journal,'https://finance-api.wildberries.ru'+path,plan);return sender
 result=execute(ARCHIVE,plan,auth,factory,active['policy_sha256'])
 observed=[json.loads(line) for line in journal.read_text().splitlines()] if journal.exists() else []
 result.update(http_dispatch_attempts=sum(v['event']=='HTTP_DISPATCH_ATTEMPT' for v in observed),http_response_statuses=[v['status'] for v in observed if v['event']=='HTTP_RESPONSE'],http_outcomes_unknown=sum(v['event']=='HTTP_OUTCOME_UNKNOWN' for v in observed))
 print(json.dumps(result,sort_keys=True));return 0 if result['executor']['status']=='DONE' else 2
if __name__=='__main__':
 try:raise SystemExit(main())
 except Exception as e:
  frames=[];tb=e.__traceback__
  while tb is not None:
   c=tb.tb_frame.f_code;frames.append({'file':Path(c.co_filename).name,'function':c.co_name,'line':tb.tb_lineno});tb=tb.tb_next
  print(json.dumps({'error_type':type(e).__name__,'wrapper_status':'STOP_OR_UNCERTAIN','failure':{'error_type':type(e).__name__,'errno':getattr(e,'errno',None),'frames':frames[-8:]}}));raise SystemExit(1)
