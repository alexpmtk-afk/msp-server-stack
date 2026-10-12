"""Explicit readback finalizer for the controlled multipart audit, never a model retry."""
import hashlib,json,re,time
from datetime import datetime,timezone
from .multipart import Collector
from .tasks import Turn,Budget

def read_audit(j,tid,rid):
 d=j.get(tid);mid=d['input_reference']['multipart_task_id'];c=Collector.__new__(Collector);c.j=j;c.db=j.db;m=c._get(mid);source=c.input_for(tid)
 parts=j.db.execute('SELECT number,message_id,received_at FROM multipart_parts WHERE task=? ORDER BY number',(mid,)).fetchall()
 tasks=[json.loads(r[0]) for r in j.db.execute('SELECT body FROM tasks') if json.loads(r[0]).get('input_reference',{}).get('multipart_task_id')==mid]
 ex=j.db.execute('SELECT request,started FROM task_executions WHERE task=?',(tid,)).fetchall()
 markers={k:bool(re.search(r'E2E-MULTIPART-\d{8}-'+k+r'-\d+',source)) for k in ('ALPHA','BRAVO','CHARLIE')}
 if len(parts)!=3 or [p[0] for p in parts]!=[1,2,3] or not m['final_received']:raise ValueError('audit_incomplete_input')
 if len(tasks)!=1 or len(ex)!=1 or ex[0][0]!=rid:raise ValueError('audit_identity_or_count_mismatch')
 final_at=parts[-1][2];created=datetime.fromisoformat(d['created_at']).timestamp();early=ex[0][1]<final_at
 input_hash=hashlib.sha256(source.encode()).hexdigest()
 if created<final_at or early or not all(markers.values()) or input_hash!=m['assembled_hash']:raise ValueError('audit_acceptance_failed')
 utc=lambda x:datetime.fromtimestamp(x,timezone.utc).isoformat()
 proof={'verified':True,'multipart_task_id':mid,'durable_task_id':tid,'execution_id':rid,'parts':[{'number':n,'message_id':msg,'received_at':utc(at)} for n,msg,at in parts],'task_created_at':d['created_at'],'execution_started_at':utc(ex[0][1]),'early_execution':False,'durable_task_count':1,'execution_count':1,'markers':markers,'assembled_hash_verified':True}
 answer='Multipart: '+mid+'\nDurable Task: '+tid+'\n'+'\n'.join(f"Часть {p['number']}: message_id={p['message_id']}, {p['received_at']}" for p in proof['parts'])+'\nDurable Task создана: '+d['created_at']+'\nExecution стартовал: '+utc(ex[0][1])+'\nРаннее выполнение: NO\nDurable Tasks: 1; executions: 1\nALPHA / BRAVO / CHARLIE: присутствуют\nHash input: verified\nMULTIPART E2E: PASS'
 return proof|{'answer':answer}

def finish_existing_audit(j,q,tid,rid):
 proof=read_audit(j,tid,rid);d=j.get(tid)
 if d['status']=='DONE':return proof
 if not all(b['allowed_mutations']==[] and b['acceptance']==['verified'] and 'Multipart Collector E2E' in b['goal'] for b in d['plan']):raise ValueError('not_controlled_audit_plan')
 row=j.db.execute('SELECT state FROM task_executions WHERE request=? AND task=?',(rid,tid)).fetchone()
 if not row or row[0]!='VERIFIED':raise ValueError('planning_receipt_not_reconciled')
 with q.claim('existing-execution-readback-finalizer',tid) as claim:
  if claim is None:raise ValueError('audit_task_not_available')
  claim.fence();j.db.execute('BEGIN IMMEDIATE');j.external_transaction=True
  try:
   while j.get(tid)['status']!='DONE':
    t=Turn(j,j.get(tid),'existing-execution-readback-finalizer',Budget())
    t.checkpoint('after_readback',{'production_state':proof,'next_action':'complete authoritative readback audit'})
    t.complete({'verified':True})
   q._transition(tid,'DONE',last_error=None)
   j.db.execute("UPDATE task_executions SET error=NULL,reconciliation='VERIFIED_READBACK_AND_AUDIT',finished_at=? WHERE request=?",(time.time(),rid))
   j.db.execute('INSERT INTO events(task,kind,body) VALUES (?,?,?)',(tid,'existing_execution_authoritative_audit',json.dumps(proof)))
   j.db.execute('UPDATE outbox SET body=? WHERE task=?',(json.dumps({'task_id':tid,'status':'DONE','result':{'kind':'complete','evidence':proof}}),tid));j.db.commit()
  except BaseException:j.db.rollback();raise
  finally:j.external_transaction=False
 return proof
