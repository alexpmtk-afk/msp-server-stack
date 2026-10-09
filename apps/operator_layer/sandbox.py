"""Registered isolated marker action; no arbitrary SQL, filenames or commands.
Every mutation crosses BEFORE -> target commit -> independent readback -> AFTER.
Unknown admission never authorizes mutation again, even when target is absent.
"""
import contextlib,hashlib,json,os,sqlite3,time,uuid
from pathlib import Path
from .tasks import stamp
class SandboxAction:
 estimated_seconds=5
 def __init__(self,root,context,now=time.time):
  self.root=Path(root);self.context=context;self.now=now;self.deferred=False
  self.tid=context['task_id'];self.step=context['current_block']
  self.request=hashlib.sha256(f'{self.tid}:{self.step}:sandbox_marker'.encode()).hexdigest()
  if 'sandbox_marker' not in context['block']['allowed_mutations']:raise ValueError('sandbox_action_not_allowed')
  path=self.root/'sandbox.sqlite'
  fd=os.open(path,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600);os.close(fd)
  with contextlib.closing(sqlite3.connect(path)) as db:
   db.execute('CREATE TABLE IF NOT EXISTS markers(request TEXT PRIMARY KEY,task TEXT,step INTEGER,value TEXT)');db.commit()
 def checkpoint(self,kind):
  with contextlib.closing(sqlite3.connect(self.root/'journal.sqlite')) as db:
   db.execute('PRAGMA synchronous=FULL');db.execute('BEGIN IMMEDIATE')
   d=json.loads(db.execute('SELECT body FROM tasks WHERE id=?',(self.tid,)).fetchone()[0])
   d['last_checkpoint']={'id':str(uuid.uuid4()),'kind':kind,'at':stamp()}
   db.execute('UPDATE tasks SET body=? WHERE id=?',(json.dumps(d),self.tid))
   db.execute('INSERT INTO events(task,kind,body) VALUES (?,?,?)',(self.tid,kind,json.dumps({'request_id':self.request,'step':self.step})));db.commit()
 def readback(self):
  # A new independent connection reads actual target state, not model claims.
  with contextlib.closing(sqlite3.connect(self.root/'sandbox.sqlite')) as db:
   r=db.execute('SELECT task,step,value FROM markers WHERE request=?',(self.request,)).fetchone()
   if not r:return None
   if r!=(self.tid,self.step,'verified-sandbox-marker'):raise ValueError('target_state_conflict')
   return {'verified':True,'request_id':self.request,'mutation_count':1,'task_id':self.tid,'step':self.step}
 def mutate(self):
  with contextlib.closing(sqlite3.connect(self.root/'sandbox.sqlite')) as db:
   db.execute('PRAGMA synchronous=FULL')
   db.execute('INSERT INTO markers VALUES (?,?,?,?)',(self.request,self.tid,self.step,'verified-sandbox-marker'));db.commit()
 def after_readback(self,receipt):
  with contextlib.closing(sqlite3.connect(self.root/'journal.sqlite')) as db:
   db.execute('PRAGMA synchronous=FULL');db.execute("UPDATE operations SET state='APPLIED',evidence=? WHERE id=?",(json.dumps(receipt),self.request));db.commit()
  self.checkpoint('sandbox_after_readback')
 def execute(self):
  self.checkpoint('sandbox_before_operation')
  with contextlib.closing(sqlite3.connect(self.root/'journal.sqlite')) as db:
   db.execute('PRAGMA synchronous=FULL');db.execute('BEGIN IMMEDIATE')
   r=db.execute('SELECT state FROM operations WHERE id=?',(self.request,)).fetchone()
   if r:
    db.rollback();receipt=self.readback()
    if receipt:self.after_readback(receipt);return receipt|{'execute':False}
    return {'state':'RECONCILIATION_REQUIRED','execute':False}
   if self.now()+self.estimated_seconds>=self.context['budget']['soft_deadline']:
    db.rollback();self.deferred=True;return {'kind':'checkpoint','execute':False}
   if db.execute("SELECT 1 FROM operations WHERE task=? AND state='UNKNOWN'",(self.tid,)).fetchone():
    db.rollback();return {'state':'RECONCILIATION_REQUIRED','execute':False}
   db.execute('INSERT INTO operations VALUES (?,?,?,?,?,NULL)',(self.request,self.tid,self.step,'sandbox_marker','UNKNOWN'));db.commit()
  self.mutate();receipt=self.readback()
  if not receipt:raise RuntimeError('mutation_result_unknown')
  self.after_readback(receipt);return receipt|{'execute':True}
 def register(self):
  from tools.registry import registry
  def handler(args,**kwargs):
   if args:raise ValueError('sandbox_action_takes_no_arguments')
   return json.dumps(self.execute())
  registry.register(name='operator_sandbox_marker',toolset='operator-sandbox',schema={'name':'operator_sandbox_marker','description':'Write exactly one isolated SQLite marker for the current durable task step, with budget guard and independent readback. No parameters. Must be called to complete a sandbox_marker step.','parameters':{'type':'object','properties':{},'additionalProperties':False}},handler=handler)
