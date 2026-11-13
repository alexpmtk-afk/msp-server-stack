"""Either published WB type completes availability; no invented financial zero.

Callers verify retained source/current-view integrity before applying this rule.
Listed-but-uncaptured reports and transport/unknown outcomes stay actionable.
"""
import copy,datetime
from zoneinfo import ZoneInfo
RULE='WB_ANY_REPORT_V2_20261113'
OPTIONAL='NOT_LISTED'
READY={'VERIFIED',OPTIONAL,'OPTIONAL_NOT_LISTED'}
TZ=ZoneInfo('Europe/Moscow')
def days(start,end):
 a=datetime.date.fromisoformat(start);b=datetime.date.fromisoformat(end)
 return {(a+datetime.timedelta(days=i)).isoformat() for i in range((b-a).days+1)}
def type_closure(index,start,end,typ):
 target=days(start,end);covered=set();proof=[]
 for r in index.get('reports',{}).values():
  if r['report_type']==typ and r['period']=='weekly' and days(r['from'],r['to'])&target:
   covered.update(days(r['from'],r['to']));proof.append(r['report_id'])
 return proof if target and target<=covered else []
def main_closure(index,start,end):return type_closure(index,start,end,1)
def weekly_closure(index,start,end):
 # A complete type is needed; disjoint partial types do not close each other.
 return type_closure(index,start,end,1) or type_closure(index,start,end,2)
def assess(job,parts,index,now=None):
 parts=copy.deepcopy(parts)
 if len(parts)!=2 or {p.get('type') for p in parts}!={1,2}:return parts
 verified=[p for p in parts if p.get('status')=='VERIFIED']
 if not verified:return parts
 for part in parts:
  if part.get('status')=='WAITING_DATA' and not part.get('report_ids'):
   part.update(status=OPTIONAL,reason='COUNTERPART_NOT_PUBLISHED_OTHER_TYPE_VERIFIED',evidence_report_ids=[rid for p in verified for rid in p.get('report_ids',[])],verified_types=[p['type'] for p in verified],financial_zero_inferred=False,report_downloaded=False)
 return parts
def overall(parts):
 return 'VERIFIED' if len(parts)==2 and {p.get('type') for p in parts}=={1,2} and all(p['status'] in READY for p in parts) and any(p['status']=='VERIFIED' for p in parts) else 'WAITING_DATA'
def required_missing(parts):
 available=any(p.get('status')=='VERIFIED' for p in parts)
 return [p for p in parts if p.get('status')=='WAITING_DATA' and (bool(p.get('report_ids')) or not available)]
def reassess_result(job,result,index,now=None):
 if result.get('status') not in ('WAITING_DATA','VERIFIED'):return result
 scope=(job['cabinet'],job['period'],job['from'],job['to'])
 if (result.get('cabinet'),result.get('period'),result.get('date_from'),result.get('date_to'))!=scope:raise ValueError('reassessment scope')
 standard={'cabinet':job['cabinet'],'period':job['period'],'date_from':job['from'],'date_to':job['to'],'attempt':job['attempts'],'bootstrap':job.get('bootstrap',False)}
 parts=assess(standard,result.get('parts',[]),index,now)
 if not parts or parts==result.get('parts'):return result
 updated=copy.deepcopy(result);updated.update(parts=parts,status=overall(parts),policy_reassessment={'rule':RULE,'source_result_unchanged':True,'financial_zero_inferred':False})
 return updated
