"""Durable orchestration. No commands, credentials, or Codex thread ownership.
Kernel locks fence live writers; SQLite FULL transactions survive worker death.
The caller must retain the turn context for the entire execution, not one RPC.
"""
import contextlib,fcntl,hashlib,json,os,re,sqlite3,time,uuid
from pathlib import Path
from datetime import datetime,timezone

def stamp():return datetime.now(timezone.utc).isoformat()
FIELDS={'current_branch','last_commit','tests_status','owner_action_required','last_error','production_state','next_action'}
KINDS={'commit','tests','before_mutation','after_readback','block_boundary','recovery'}
def bounded(value):
 raw=json.dumps(value,ensure_ascii=False)
 if len(raw.encode())>16000:raise ValueError('context_too_large')
 if re.search(r'(?i)(private.key|bearer\s|gh[pousr]_|-----BEGIN|password|cookie|secret|access_token)',raw):raise ValueError('sensitive_context_rejected')
 return value

class Budget:
 def __init__(self,started=None,now=time.time):
  self.now=now;self.started=now() if started is None else started;self.soft_deadline=self.started+480
 def can_start(self,estimated_seconds=0):return self.now()+estimated_seconds<self.soft_deadline
 def context(self):return {'turn_started_at':self.started,'elapsed_seconds':max(0,self.now()-self.started),'soft_deadline':self.soft_deadline,'hard_limit_seconds':600}

class Journal:
 def __init__(self,root):
  self.root=Path(root).absolute()
  if self.root.is_symlink():raise ValueError('unsafe_journal_path')
  self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
  if self.root.stat().st_uid!=os.getuid() or self.root.stat().st_mode&0o077:raise ValueError('unsafe_journal_permissions')
  db=self.root/'journal.sqlite'
  fd=os.open(db,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600);os.close(fd)
  if db.stat().st_uid!=os.getuid() or db.stat().st_mode&0o077:raise ValueError('unsafe_database_permissions')
  self.db=sqlite3.connect(db,timeout=5);self.db.execute('PRAGMA synchronous=FULL')
  self.db.executescript('CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, body TEXT NOT NULL); CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY, task TEXT, kind TEXT, body TEXT); CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY, task TEXT, block INTEGER, name TEXT, state TEXT, evidence TEXT); CREATE TABLE IF NOT EXISTS outbox(task TEXT PRIMARY KEY, origin TEXT, body TEXT, delivered INTEGER DEFAULT 0);')
 def close(self):self.db.close()
 def __del__(self):
  if hasattr(self,'db'):self.db.close()
 def get(self,task_id):
  row=self.db.execute('SELECT body FROM tasks WHERE id=?',(task_id,)).fetchone()
  if not row:raise ValueError('unknown_task')
  return json.loads(row[0])
 def save(self,d,kind):
  bounded(d);d['updated_at']=stamp()
  with (contextlib.nullcontext() if getattr(self,"external_transaction",False) else self.db):
   self.db.execute('INSERT OR REPLACE INTO tasks VALUES (?,?)',(d['task_id'],json.dumps(d)))
   self.db.execute('INSERT INTO events(task,kind,body) VALUES (?,?,?)',(d['task_id'],kind,json.dumps(d)))
   if d['status']=='DONE':self.db.execute('INSERT OR IGNORE INTO outbox(task,origin,body) VALUES (?,?,?)',(d['task_id'],d['origin_chat'],json.dumps({'status':'PASS','completed_blocks':d['completed_blocks']})))
 def task_document(self,origin,goal,plan,task_id=None):
  if not isinstance(plan,list) or not plan:raise ValueError('plan_required')
  for i,b in enumerate(plan):
   if set(b)!={'goal','acceptance','allowed_mutations','expected_output','dependencies','rollback','readback'} or not b['acceptance'] or any(not isinstance(n,int) or n<0 or n>=i for n in b['dependencies']):raise ValueError('invalid_block')
  bounded([origin,goal,plan]);tid=task_id or str(uuid.uuid4());now=stamp()
  d=dict(task_id=tid,origin_chat=origin,goal=goal,created_at=now,status='READY',plan=plan,current_block=0,completed_blocks=[],pending_blocks=list(range(len(plan))),current_branch=None,last_commit=None,tests_status='UNKNOWN',owner_action_required=None,last_checkpoint=None,last_error=None,production_state={},next_action='resume block 0',updated_at=now,lease=None)
  return d
 def create(self,origin,goal,plan):
  d=self.task_document(origin,goal,plan);self.save(d,'created');return d['task_id']
 def unfinished(self):return [json.loads(r[0]) for r in self.db.execute('SELECT body FROM tasks') if json.loads(r[0])['status']!='DONE']
 def results(self):return [dict(task_id=r[0],origin_chat=r[1],result=json.loads(r[2]),delivered=bool(r[3])) for r in self.db.execute('SELECT task,origin,body,delivered FROM outbox')]
 @contextlib.contextmanager
 def turn(self,tid,writer,started=None):
  if not re.fullmatch(r'[a-f0-9-]{36}',tid):raise ValueError('invalid_task_id')
  fd=os.open(self.root/(tid+'.lock'),os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
  locked=False
  try:
   try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);locked=True
   except BlockingIOError:raise ValueError('active_writer') from None
   d=self.get(tid)
   if d['status']=='DONE':raise ValueError('task_already_done')
   if d['status'] not in ('READY','PLANNING','INTERRUPTED','RUNNING'):raise ValueError('task_not_runnable')
   if d['status']=='RUNNING':d['status']='INTERRUPTED';d['last_error']='worker_lost';self.save(d,'crash_recovery')
   t=Turn(self,d,writer,Budget(started));yield t
  except BaseException:
   if locked:
    d=self.get(tid)
    if d['status']=='RUNNING':d['status']='INTERRUPTED';d['last_error']='turn_interrupted';d['lease']=None;self.save(d,'interrupted')
   raise
  finally:
   if locked:
    d=self.get(tid)
    if d['status']=='RUNNING':d['status']='INTERRUPTED';d['lease']=None;self.save(d,'turn_end')
    fcntl.flock(fd,fcntl.LOCK_UN)
   os.close(fd)

class Turn:
 def __init__(self,j,d,writer,budget):
  self.j=j;self.d=d;self.budget=budget;self.closed=False
  self.recovery_required=d['status']=='INTERRUPTED'
  d['status']='RUNNING';d['lease']={'writer':writer,'pid':os.getpid(),**budget.context()};j.save(d,'turn_start')
 def context(self):
  return {k:self.d[k] for k in ('task_id','origin_chat','goal','current_block','completed_blocks','last_checkpoint','current_branch','last_commit','tests_status','production_state','next_action')}|{'block':self.d['plan'][self.d['current_block']],'budget':self.budget.context(),'recovery_required':self.recovery_required,'input_reference':self.d.get('input_reference'),'requires_decomposition':self.d.get('requires_decomposition',False),'pending_operations':list(self.j.db.execute("SELECT id,name FROM operations WHERE task=? AND state='UNKNOWN'",(self.d['task_id'],)))}
 def guard(self):
  if self.closed:raise ValueError('one_block_per_turn')
  if not self.budget.can_start():raise ValueError('soft_deadline_checkpoint_required')
 def checkpoint(self,kind,updates):
  if self.closed:raise ValueError('one_block_per_turn')
  if kind not in KINDS or set(updates)-FIELDS:raise ValueError('invalid_checkpoint')
  bounded(updates);self.d.update(updates);self.d['last_checkpoint']={'schema_version':1,'id':str(uuid.uuid4()),'kind':kind,'at':stamp()};self.j.save(self.d,'checkpoint')
  if kind=='recovery':self.recovery_required=False
 def begin_operation(self,name,mutation):
  self.guard()
  if self.recovery_required:raise ValueError('recovery_readback_required')
  if mutation not in self.d['plan'][self.d['current_block']]['allowed_mutations']:raise ValueError('mutation_not_allowed')
  bounded(name);rid=hashlib.sha256(f"{self.d['task_id']}:{self.d['current_block']}:{name}".encode()).hexdigest()
  row=self.j.db.execute('SELECT state FROM operations WHERE id=?',(rid,)).fetchone()
  if row:
   if row[0]=='UNKNOWN':raise ValueError('readback_required')
   if row[0]=='APPLIED':return {'request_id':rid,'execute':False}
  if self.j.db.execute("SELECT 1 FROM operations WHERE task=? AND state='UNKNOWN'",(self.d['task_id'],)).fetchone():raise ValueError('readback_required')
  self.checkpoint('before_mutation',{'next_action':'readback operation '+rid})
  with self.j.db:self.j.db.execute('INSERT OR REPLACE INTO operations VALUES (?,?,?,?,?,?)',(rid,self.d['task_id'],self.d['current_block'],name,'UNKNOWN',None))
  return {'request_id':rid,'execute':True}
 def reconcile(self,rid,evidence,applied):
  if self.closed:raise ValueError('one_block_per_turn')
  if evidence.get('verified') is not True:raise ValueError('verified_readback_required')
  bounded(evidence)
  with self.j.db:
   c=self.j.db.execute('UPDATE operations SET state=?,evidence=? WHERE id=? AND task=?',('APPLIED' if applied else 'NOT_APPLIED',json.dumps(evidence),rid,self.d['task_id']))
   if c.rowcount!=1:raise ValueError('unknown_operation')
  self.checkpoint('after_readback',{'production_state':evidence});self.recovery_required=False
 def set_execution_plan(self,plan,evidence):
  self.guard()
  if not self.d.get('requires_decomposition') or evidence.get('input_hash')!=self.d.get('input_reference',{}).get('assembled_hash'):raise ValueError('decomposition_not_verified')
  self.j.task_document(self.d['origin_chat'],self.d['goal'],plan)
  self.d.update(plan=plan,current_block=0,completed_blocks=[],pending_blocks=list(range(len(plan))),requires_decomposition=False,status='READY',lease=None,next_action='resume execution block 0')
  self.checkpoint('block_boundary',{});self.closed=True
 def complete(self,evidence):
  self.guard()
  if self.d.get('requires_decomposition'):raise ValueError('execution_plan_required')
  bounded(evidence)
  b=self.d['plan'][self.d['current_block']]
  if self.recovery_required or any(evidence.get(k) is not True for k in b['acceptance']):raise ValueError('acceptance_not_verified')
  if self.j.db.execute("SELECT 1 FROM operations WHERE task=? AND state='UNKNOWN'",(self.d['task_id'],)).fetchone():raise ValueError('readback_required')
  n=self.d['current_block'];self.d['completed_blocks'].append(n);self.d['pending_blocks'].remove(n)
  self.d['status']='READY' if self.d['pending_blocks'] else 'DONE';self.d['lease']=None
  self.d['current_block']=n+1;self.d['next_action']=f'resume block {n+1}' if self.d['pending_blocks'] else 'deliver final result'
  self.checkpoint('block_boundary',{})
  self.closed=True
