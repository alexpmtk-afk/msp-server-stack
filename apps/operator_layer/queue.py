"""Scoped persistent queue. All runtime calls happen AFTER a durable UNKNOWN record.
Flock is a live-process fence, not a lease expiry heuristic. No shell/thread RPC API.
"""
import contextlib,fcntl,hashlib,json,os,sqlite3,threading,time,uuid
from .tasks import Budget,Turn,bounded,stamp
STATES={'QUEUED','LEASED','RUNNING','CHECKPOINTED','WAITING_NEXT_TURN','BLOCKED','INTERRUPTED','DONE','FAILED','CANCELLED'}
SPEC={'task_id','request_id','profile','owner','origin_chat','session_key','origin_platform'}

class TaskQueue:
 def __init__(self,journal,*,allowed_scope,_migrating=False):
  if len(allowed_scope)!=4 or any(not isinstance(x,str) or not x for x in allowed_scope):raise ValueError('invalid_queue_scope')
  self.j=journal;self.db=journal.db;self.scope=tuple(allowed_scope)
  self.db.executescript('''CREATE TABLE IF NOT EXISTS task_queue(task TEXT PRIMARY KEY, request TEXT UNIQUE NOT NULL, scope TEXT NOT NULL, state TEXT NOT NULL, worker TEXT, token TEXT, lease_expires REAL, updated REAL NOT NULL);
CREATE TABLE IF NOT EXISTS task_executions(request TEXT PRIMARY KEY, task TEXT NOT NULL, block INTEGER NOT NULL, state TEXT NOT NULL, result TEXT, context TEXT NOT NULL, started REAL NOT NULL);
CREATE TABLE IF NOT EXISTS task_queue_events(seq INTEGER PRIMARY KEY, task TEXT, state TEXT, at REAL);
''')
  if not _migrating:
   from .worker_service import migrate
   migrate(journal)
 def _transition(self,tid,state,**updates):
  if state not in STATES:raise ValueError('invalid_queue_state')
  self.db.execute('UPDATE task_queue SET state=?,updated=? WHERE task=?',(state,time.time(),tid))
  d=self.j.get(tid);d.update(status=state,updated_at=stamp(),**updates)
  bounded(d);self.db.execute('UPDATE tasks SET body=? WHERE id=?',(json.dumps(d),tid))
  self.db.execute('INSERT INTO task_queue_events(task,state,at) VALUES (?,?,?)',(tid,state,time.time()))
 def status(self,tid):
  r=self.db.execute('SELECT state,worker,lease_expires FROM task_queue WHERE task=?',(tid,)).fetchone()
  if not r:raise ValueError('not_queued')
  return {'task_id':tid,'state':r[0],'worker_id':r[1],'lease_expires':r[2]}
 def submit(self,spec):
  if set(spec)!=SPEC or (spec['profile'],spec['owner'],spec['origin_chat'],spec['session_key'])!=self.scope or spec['origin_platform']!='telegram':raise ValueError('invalid_task_scope_or_fields')
  bounded(spec)
  if not isinstance(spec['request_id'],str) or not 1<=len(spec['request_id'])<=256:raise ValueError('invalid_request_id')
  self.db.execute('BEGIN IMMEDIATE')
  try:
   tid=spec['task_id']
   if self.db.execute('SELECT 1 FROM recovery_tombstones WHERE task_id=?',(tid,)).fetchone():raise ValueError('probe_retry_forbidden')
   d=self.j.get(tid)
   if d['origin_chat']!=spec['origin_chat']:raise ValueError('origin_mismatch')
   origin={k:spec[k] for k in ('profile','owner','origin_chat','session_key','origin_platform')}
   if d.get('origin') and d['origin']!=origin:raise ValueError('origin_mismatch')
   row=self.db.execute('SELECT task,request,scope FROM task_queue WHERE task=? OR request=?',(tid,spec['request_id'])).fetchone()
   if row:
    if row!=(tid,spec['request_id'],json.dumps(origin,sort_keys=True)):raise ValueError('dispatch_conflict')
   else:
    if d['status'] not in ('READY','PLANNING'):raise ValueError('task_not_dispatchable')
    if d.get('input_reference'):
     from .multipart import Collector
     c=Collector.__new__(Collector);c.j=self.j;c.db=self.db
     mid=d['input_reference']['multipart_task_id'];m=c._get(mid)
     if m['status']!='ASSEMBLED' or m['durable_task_id']!=tid:raise ValueError('multipart_not_assembled')
     if spec['request_id']!='multipart:'+mid or (m['profile'],m['owner'],m['origin_chat'],m['routing_session_key'])!=self.scope:raise ValueError('multipart_scope_mismatch')
     c.input_for(tid)
    self.db.execute("INSERT INTO task_queue(task,request,scope,state,worker,token,lease_expires,updated) VALUES (?,?,?,'QUEUED',NULL,NULL,NULL,?)",(tid,spec['request_id'],json.dumps(origin,sort_keys=True),time.time()))
    self._transition(tid,'QUEUED',origin=origin)
   self.db.commit();return {'request_id':spec['request_id'],'task_id':tid,'accepted':True}
  except BaseException:self.db.rollback();raise
 def read_submission(self,request_id):
  r=self.db.execute('SELECT task,scope FROM task_queue WHERE request=?',(request_id,)).fetchone()
  if not r:return None
  o=json.loads(r[1])
  if (o['profile'],o['owner'],o['origin_chat'],o['session_key'])!=self.scope:raise ValueError('readback_scope_mismatch')
  return {'request_id':request_id,'task_id':r[0],'accepted':True}
 def enqueue_multipart(self,collector):
  collector.recover()
  for item in collector.pending():
   mid=item['multipart_task_id'];d=collector._get(mid)
   if (d['profile'],d['owner'],d['origin_chat'],d['routing_session_key'])!=self.scope:continue
   if item['dispatch_state']=='UNKNOWN':
    receipt=self.read_submission('multipart:'+mid)
    if receipt:collector.confirm_dispatch(mid,receipt)
    # Absence alone doesn't authorize retry of an external provider. This in-process
    # queue shares the exact target database, so it is authoritative here.
    else:collector.confirm_not_dispatched(mid,{'request_id':'multipart:'+mid,'task_id':item['durable_task_id'],'accepted':False})
   if collector.status(mid)['status']=='DISPATCHED':continue
   req=collector.prepare_dispatch(mid)
   self.submit({k:req[k] for k in SPEC if k in req}|{'origin_platform':'telegram'})
   collector.confirm_dispatch(mid,self.read_submission(req['request_id']))
 def _lock(self,name):
  fd=os.open(self.j.root/name,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
  try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:os.close(fd);return None
  return fd
 def recover(self):
  rows=self.db.execute("SELECT task FROM task_queue WHERE state IN ('LEASED','RUNNING','CHECKPOINTED') AND scope=?",(self._scope_json(),)).fetchall()
  for (tid,) in rows:
   fd=self._lock(tid+'.lock')
   if fd is None:continue
   try:
    self.db.execute('BEGIN IMMEDIATE')
    d=self.j.get(tid);r=self.db.execute("SELECT block FROM task_executions WHERE task=? AND state='UNKNOWN' ORDER BY started DESC LIMIT 1",(tid,)).fetchone()
    if d['status']=='DONE':state='DONE'
    elif r and (d['current_block']>r[0] or (d.get('requires_decomposition') is False and r[0]==-1)):
     self.db.execute("UPDATE task_executions SET state='VERIFIED' WHERE task=? AND state='UNKNOWN'",(tid,));state='WAITING_NEXT_TURN'
    elif r:
     state='INTERRUPTED'
     self.db.execute("UPDATE task_executions SET reconciliation='RECONCILIATION_REQUIRED' WHERE task=? AND state='UNKNOWN'",(tid,))
    else:state='QUEUED'
    self._transition(tid,state,last_error='worker_lost' if state=='INTERRUPTED' else None)
    self.db.execute('UPDATE task_queue SET worker=NULL,token=NULL,lease_expires=NULL WHERE task=?',(tid,));self.db.commit()
   except BaseException:self.db.rollback();raise
   finally:os.close(fd)
 def _scope_json(self):return json.dumps(dict(zip(('profile','owner','origin_chat','session_key'),self.scope))|{'origin_platform':'telegram'},sort_keys=True)
 @contextlib.contextmanager
 def claim(self,worker_id,task_id=None,recovery=False):
  if not worker_id or len(worker_id)>128:raise ValueError('invalid_worker')
  self.recover();claim=None;fd=None;origin_fd=None
  try:
   states=('INTERRUPTED','BLOCKED') if recovery else ('QUEUED','WAITING_NEXT_TURN')
   rows=self.db.execute('SELECT task FROM task_queue WHERE state IN (?,?) AND scope=? AND available_at<=? AND task NOT IN (SELECT task_id FROM recovery_tombstones)'+(' AND task=?' if task_id else '')+' ORDER BY updated',(*states,self._scope_json(),time.time(),*((task_id,) if task_id else ()))).fetchall()
   for (tid,) in rows:
    fd=self._lock(tid+'.lock')
    if fd is None:continue
    origin_fd=self._lock('origin-'+hashlib.sha256(self._scope_json().encode()).hexdigest()+'.lock')
    if origin_fd is None:os.close(fd);fd=None;continue
    self.db.execute('BEGIN IMMEDIATE')
    row=self.db.execute('SELECT state FROM task_queue WHERE task=?',(tid,)).fetchone()
    if row[0] not in states:self.db.rollback();os.close(fd);os.close(origin_fd);fd=origin_fd=None;continue
    token=str(uuid.uuid4());self._transition(tid,'LEASED')
    self.db.execute('UPDATE task_queue SET worker=?,token=?,lease_expires=?,lease_started_at=?,heartbeat_at=?,generation=generation+1 WHERE task=?',(worker_id,token,time.time()+90,time.time(),time.time(),tid));self.db.commit()
    claim=Claim(self,tid,worker_id,token,recovery);break
   yield claim
  finally:
   if claim:
    with self.db:
     row=self.db.execute('SELECT state FROM task_queue WHERE task=? AND token=?',(claim.task_id,claim.token)).fetchone()
     if row and row[0]=='LEASED':self._transition(claim.task_id,'INTERRUPTED' if recovery else 'QUEUED')
     self.db.execute('UPDATE task_queue SET worker=NULL,token=NULL,lease_expires=NULL WHERE task=? AND token=?',(claim.task_id,claim.token))
   if origin_fd is not None:os.close(origin_fd)
   if fd is not None:os.close(fd)

class Claim:
 def __init__(self,q,tid,worker,token,recovery):self.q=q;self.task_id=tid;self.worker=worker;self.token=token;self.recovery=recovery
 def heartbeat(self):
  with contextlib.closing(sqlite3.connect(self.q.j.root/'journal.sqlite',timeout=5)) as db:
   n=db.execute('UPDATE task_queue SET lease_expires=?,heartbeat_at=? WHERE task=? AND token=?',(time.time()+90,time.time(),self.task_id,self.token)).rowcount
   if n!=1:raise ValueError('lease_lost')
   db.commit()
 def fence(self):
  row=self.q.db.execute('SELECT token FROM task_queue WHERE task=?',(self.task_id,)).fetchone()
  if not row or row[0]!=self.token:raise ValueError('lease_lost')

class Worker:
 def __init__(self,queue,executor,verifier,*,worker_id):self.q=queue;self.executor=executor;self.verifier=verifier;self.worker_id=worker_id
 def _context(self,tid,budget):
  d=self.q.j.get(tid);keys=('task_id','goal','completed_blocks','current_block','current_branch','last_commit','tests_status','owner_action_required','last_checkpoint','production_state','next_action','origin','input_reference','requires_decomposition')
  return {k:d.get(k) for k in keys}|{'block':d['plan'][d['current_block']],'budget':budget.context()}
 def _source(self,tid):
  d=self.q.j.get(tid)
  if not d.get('input_reference'):return None
  from .multipart import Collector
  c=Collector.__new__(Collector);c.j=self.q.j;c.db=self.q.db
  return c.input_for(tid)
 def _schema_block(self,claim,rid,reason):
  with self.q.db:
   self.q.db.execute("UPDATE task_executions SET error=?,reconciliation='BLOCKED_SCHEMA_MISMATCH' WHERE request=?",(reason,rid))
   self.q._transition(claim.task_id,'BLOCKED',last_error='BLOCKED_SCHEMA_MISMATCH:'+reason,next_action='read saved receipt; explicit schema repair required')
  return False
 def _settle(self,claim,rid,context,outcome):
  from .receipt_schema import normalize_receipt
  claim.fence();raw=json.dumps(outcome,sort_keys=True);raw_hash=hashlib.sha256(raw.encode()).hexdigest()
  try:canonical=normalize_receipt(outcome)
  except ValueError as exc:
   reason=str(exc)
   with self.q.db:self.q.db.execute('INSERT OR REPLACE INTO receipt_normalizations VALUES (?,?,?,?,NULL,?)',(rid,raw,raw_hash,None,reason))
   return self._schema_block(claim,rid,reason)
  with self.q.db:self.q.db.execute('INSERT OR REPLACE INTO receipt_normalizations VALUES (?,?,?,?,?,NULL)',(rid,raw,raw_hash,1,json.dumps(canonical,sort_keys=True)))
  try:return self._apply_settlement(claim,rid,context,canonical)
  except (ValueError,TypeError,KeyError) as exc:
   # Deterministic contract errors isolate one task, never kill the service.
   return self._schema_block(claim,rid,'invalid_checkpoint' if str(exc)=='invalid_checkpoint' else 'settlement_validation_failed')
 def _apply_settlement(self,claim,rid,context,outcome):
  claim.fence();bounded(outcome)
  if not self.verifier(context,outcome):
   with self.q.db:self.q._transition(claim.task_id,'BLOCKED',last_error='acceptance_not_verified')
   return False
  self.q.db.execute('BEGIN IMMEDIATE')
  self.q.j.external_transaction=True
  try:
   d=self.q.j.get(claim.task_id);t=Turn(self.q.j,d,self.worker_id,Budget())
   kind=outcome.get('kind');updates=outcome.get('updates',{})
   if updates:t.checkpoint('after_readback',updates)
   if kind=='complete':t.complete(outcome['evidence'])
   elif kind=='plan':t.set_execution_plan(outcome['plan'],{'input_hash':context['input_reference']['assembled_hash']})
   elif kind=='checkpoint':t.checkpoint('recovery',updates)
   elif kind=='blocked':
    self.q._transition(claim.task_id,'BLOCKED',last_error='owner_or_capability_action_required')
    self.q.db.commit();return False
   else:raise ValueError('invalid_executor_outcome')
   with contextlib.nullcontext():
    self.q.db.execute("UPDATE task_executions SET state='VERIFIED',result=?,finished_at=?,reconciliation='VERIFIED_READBACK' WHERE request=?",(json.dumps(outcome),time.time(),rid))
    done=self.q.j.get(claim.task_id)['status']=='DONE'
    self.q._transition(claim.task_id,'DONE' if done else 'CHECKPOINTED')
    if done:
     self.q.db.execute('UPDATE outbox SET body=? WHERE task=?',(json.dumps({'task_id':claim.task_id,'status':'DONE','result':outcome}),claim.task_id))
    else:self.q._transition(claim.task_id,'WAITING_NEXT_TURN')
   self.q.db.commit();return True
  except BaseException:
   self.q.db.rollback();raise
  finally:self.q.j.external_transaction=False

 def run_once(self):
  with self.q.claim(self.worker_id) as claim:
   if claim is None:return False
   budget=Budget();context=self._context(claim.task_id,budget)
   if context['block']['allowed_mutations'] and not ((getattr(self.executor,'sandbox_enabled',False) and context['block']['allowed_mutations']==['sandbox_marker']) or (getattr(self.executor,'devexec_write_enabled',False) and callable(getattr(self.executor,'approval_for',None)) and self.executor.approval_for(context))):
    with self.q.db:self.q._transition(claim.task_id,'BLOCKED',last_error='operation_not_registered')
    return False
   if not budget.can_start(5 if context['block']['allowed_mutations']==['sandbox_marker'] else 0):
    with self.q.db:self.q._transition(claim.task_id,'WAITING_NEXT_TURN',next_action='soft budget exhausted before step')
    return False
   if self.q.db.execute("SELECT 1 FROM task_executions WHERE task=? AND state='UNKNOWN'",(claim.task_id,)).fetchone():
    with self.q.db:self.q._transition(claim.task_id,'BLOCKED',last_error='unknown_execution_readback_required')
    return False
   block=-1 if context.get('requires_decomposition') else context['current_block']
   count=self.q.db.execute('SELECT COUNT(*) FROM task_executions WHERE task=? AND block=?',(claim.task_id,block)).fetchone()[0]
   rid=hashlib.sha256(f'{claim.task_id}:{block}:{count}'.encode()).hexdigest()
   with self.q.db:
    self.q.db.execute("INSERT INTO task_executions(request,task,block,state,result,context,started) VALUES (?,?,?,'UNKNOWN',NULL,?,?)",(rid,claim.task_id,block,json.dumps(context),time.time()))
    self.q.db.execute('UPDATE task_executions SET execution_id=request WHERE request=?',(rid,))
    self.q._transition(claim.task_id,'RUNNING')
   stop=threading.Event();lost=threading.Event()
   def heartbeat():
    while not stop.wait(20):
     try:claim.heartbeat()
     except Exception:lost.set();self.executor.interrupt();return
   thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
   try:
    outcome=self.executor.execute(context,self._source(claim.task_id),rid,budget)
    if lost.is_set():raise ValueError('lease_lost')
    claim.fence();self._settle(claim,rid,context,outcome)
   except Exception as exc:
    with self.q.db:self.q.db.execute("UPDATE task_executions SET reconciliation='RECONCILIATION_REQUIRED' WHERE request=? AND state='UNKNOWN'",(rid,));self.q._transition(claim.task_id,'INTERRUPTED',last_error='turn_timeout' if isinstance(exc,TimeoutError) else 'runtime_or_transport_interrupted')
   finally:stop.set();thread.join(timeout=5)
   return True
 def reconcile(self,tid):
  with self.q.claim(self.worker_id,tid,recovery=True) as claim:
   if claim is None:return False
   row=self.q.db.execute("SELECT request,context FROM task_executions WHERE task=? AND state='UNKNOWN' ORDER BY started DESC LIMIT 1",(tid,)).fetchone()
   if not row:return False
   rid,raw=row;context=json.loads(raw)
   try:result=self.executor.readback(rid,context)
   except (ValueError,TypeError,KeyError):return self._schema_block(claim,rid,'receipt_readback_invalid')
   if result is None:
    with self.q.db:self.q._transition(tid,'BLOCKED',last_error='unknown_execution_readback_required')
    return False
   return self._settle(claim,rid,context,result)
