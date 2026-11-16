"""WB type2 is optional publication, never an inferred zero financial amount.

Callers must verify source files/current view before accepting closure evidence.
No HTTP, secrets, state writes or amount calculations in this shared policy.
"""
import copy,datetime
from zoneinfo import ZoneInfo
OPTIONAL='OPTIONAL_NOT_LISTED'
READY={'VERIFIED',OPTIONAL}
TZ=ZoneInfo('Europe/Moscow')
def days(start,end):
 a=datetime.date.fromisoformat(start);b=datetime.date.fromisoformat(end)
 return {(a+datetime.timedelta(days=i)).isoformat() for i in range((b-a).days+1)}
def main_closure(index,start,end):
 target=days(start,end);covered=set();proof=[]
 for r in index.get('reports',{}).values():
  if r['report_type']==1 and r['period']=='weekly' and days(r['from'],r['to'])&target:
   covered.update(days(r['from'],r['to']));proof.append(r['report_id'])
 return proof if target<=covered else []
def later_main(index,end):
 return [r['report_id'] for r in index.get('reports',{}).values() if r['report_type']==1 and r['from']>end]
def assess(job,parts,index,now=None):
 parts=copy.deepcopy(parts);bytype={p['type']:p for p in parts};main=bytype.get(1,{});buyout=bytype.get(2,{})
 if main.get('status')!='VERIFIED' or buyout.get('status')!='WAITING_DATA' or buyout.get('report_ids'):return parts
 # A named-but-unavailable report is NOT an absent optional publication.
 closure=main_closure(index,job['date_from'],job['date_to']);later=later_main(index,job['date_to'])
 today=(now or datetime.datetime.now(TZ)).astimezone(TZ).date();end=datetime.date.fromisoformat(job['date_to'])
 limit=1 if job.get('bootstrap') else (10 if job['period']=='weekly' else 3)
 reason=None;proof=[]
 if job['period']=='daily' and closure:reason='PERIOD_CLOSED_BY_VERIFIED_MAIN_WEEKLY';proof=closure
 elif later:reason='LATER_VERIFIED_MAIN_REPORT_EXISTS';proof=later
 elif job['period']=='weekly' and today>=end+datetime.timedelta(days=2):reason='MAIN_WEEKLY_READY_AFTER_MONDAY'
 elif job['attempt']>=limit:reason='NOT_LISTED_AT_FINAL_AVAILABILITY_CHECK'
 if reason:buyout.update(status=OPTIONAL,reason=reason,evidence_report_ids=proof,financial_zero_inferred=False,report_downloaded=False)
 return parts
def overall(parts):return 'VERIFIED' if all(p['status'] in READY for p in parts) else 'WAITING_DATA'
def required_missing(parts):
 return [p for p in parts if p.get('status')=='WAITING_DATA' and (p['type']==1 or bool(p.get('report_ids')))]
def reassess_result(job,result,index,now=None):
 if result.get('status') not in ('WAITING_DATA','VERIFIED'):return result
 scope=(job['cabinet'],job['period'],job['from'],job['to'])
 if (result.get('cabinet'),result.get('period'),result.get('date_from'),result.get('date_to'))!=scope:raise ValueError('reassessment scope')
 standard={'cabinet':job['cabinet'],'period':job['period'],'date_from':job['from'],'date_to':job['to'],'attempt':job['attempts'],'bootstrap':job.get('bootstrap',False)}
 parts=assess(standard,result.get('parts',[]),index,now)
 if not parts or parts==result.get('parts'):return result
 updated=copy.deepcopy(result);updated.update(parts=parts,status=overall(parts),policy_reassessment={'rule':'WB_OPTIONAL_BUYOUT_V1_20261113','source_result_unchanged':True,'financial_zero_inferred':False})
 return updated
