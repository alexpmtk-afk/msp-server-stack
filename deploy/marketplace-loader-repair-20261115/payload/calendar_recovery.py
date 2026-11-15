"""Narrow reconciliation of proven pre-send snapshot-ceiling failures only."""
import copy,re
CABINETS=('ozon_dmitrieva','ozon_novokshenov','ozon_laser_master')

def rearm(cycle,catalog,sources,*,day,cycle_id,now):
 if cycle.get('cycle_id')!=cycle_id or cycle.get('status')!='HOLD' or len(cycle.get('jobs',[]))!=3:raise ValueError('repair cycle scope')
 if {j['cabinet'] for j in cycle['jobs']}!=set(CABINETS):raise ValueError('repair cabinet scope')
 cy=copy.deepcopy(cycle);ca=copy.deepcopy(catalog)
 for j in cy['jobs']:
  cab=j['cabinet'];key=cab+'|'+day;s=sources[cab];result=s['result'];known=ca.get(key,{})
  if j.get('key')!=key or j.get('day')!=day or j.get('status')!='HOLD' or j.get('attempts')!=1:raise ValueError('repair job scope')
  if known.get('status')!='HOLD' or known.get('cycle_id')!=cycle_id:raise ValueError('catalog repair scope')
  if result.get('status')!='HOLD' or result.get('cabinet')!=cab or result.get('day')!=day or result.get('error_type')!='AccrualError':raise ValueError('not a calendar preflight failure')
  if not any(f.get('file')=='ozon_accruals.py' and f.get('function')=='request_body' and f.get('line')==54 for f in result.get('frames',[])):raise ValueError('unexpected failure location')
  if known.get('result')!=result or j.get('result')!=result:raise ValueError('conflicting original failure')
  if any(s.get(k)!=0 for k in ('entries','responses','derived')) or not re.fullmatch('[0-9a-f]{32}',s.get('nonce','')):raise ValueError('outcome not proven before sender')
  j.update(status='IN_FLIGHT',next_due=now,calendar_recovery=dict(original_result=copy.deepcopy(result),reason='CALENDAR_CEILING_BEFORE_ANY_SENDER_ENTRY'))
  ca[key]=dict(known,status='RECOVERY_PENDING',calendar_recovery=copy.deepcopy(j['calendar_recovery']))
 cy['status']='RUNNING'
 return cy,ca
