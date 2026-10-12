"""Explicit, offline-only saved multipart planning receipt reconciliation.

By default, inspect without writes. --apply requires the durable worker process
to be stopped (exclusive existing worker-service.lock), a pinned task/request
and SHA256 of the exact original runtime_receipts.body UTF-8 bytes.
Never invokes the model, tool executor, Telegram, or external network.
"""
import argparse,fcntl,hashlib,json,os,re,sqlite3
from pathlib import Path
from .receipt_schema import normalize_receipt
from .tasks import Journal
from .queue import TaskQueue,Worker

def _sha_utf8(s):
 return hashlib.sha256(s.encode('utf-8')).hexdigest()

def inspect(config,task_id,execution_id,expected_sha):
 if not re.fullmatch(r'[0-9a-f-]{36}',task_id):raise ValueError('invalid_task_id')
 if not re.fullmatch(r'[0-9a-f]{64}',execution_id):raise ValueError('invalid_execution_id')
 if not re.fullmatch(r'[0-9a-f]{64}',expected_sha):raise ValueError('invalid_receipt_sha')
 scope=tuple(config['scope'])
 if len(scope)!=4 or any(not isinstance(x,str) or not x for x in scope):raise ValueError('invalid_scope')
 root=Path(config['root']).absolute()
 if root.is_symlink() or not (root/'journal.sqlite').is_file():raise ValueError('missing_or_unsafe_journal')
 db=sqlite3.connect((root/'journal.sqlite').as_uri()+'?mode=ro',uri=True,timeout=5)
 try:
  db.execute('PRAGMA query_only=ON')
  task_row=db.execute('SELECT body FROM tasks WHERE id=?',(task_id,)).fetchone()
  if not task_row:raise ValueError('task_not_found')
  task=json.loads(task_row[0])
  if (task.get('status')!='BLOCKED' or task.get('last_error')!='BLOCKED_SCHEMA_MISMATCH:plan_required' or
      task.get('requires_decomposition') is not True or task.get('origin_chat')!=scope[2]):
   raise ValueError('task_not_expected_blocked_planning_state')
  origin=task.get('origin') or {}
  if any(origin.get(k)!=v for k,v in zip(('profile','owner','origin_chat','session_key'),scope)):
   raise ValueError('task_scope_mismatch')
  qr=db.execute('SELECT state,request FROM task_queue WHERE task=?',(task_id,)).fetchone()
  if not qr or qr!=('BLOCKED','multipart:'+task['input_reference']['multipart_task_id']):
   raise ValueError('queue_state_mismatch')
  count=db.execute('SELECT COUNT(*) FROM task_executions WHERE task=?',(task_id,)).fetchone()[0]
  if count!=1:raise ValueError('unexpected_execution_count')
  ex=db.execute('SELECT request,execution_id,block,state,error,reconciliation,context FROM task_executions WHERE task=?',(task_id,)).fetchone()
  if (ex[0]!=execution_id or ex[1]!=execution_id or ex[2]!=-1 or ex[3]!='UNKNOWN' or
      ex[4]!='plan_required' or ex[5]!='BLOCKED_SCHEMA_MISMATCH'):
   raise ValueError('execution_identity_or_status_mismatch')
  saved=db.execute('SELECT body FROM runtime_receipts WHERE request=?',(execution_id,)).fetchone()
  if not saved or _sha_utf8(saved[0])!=expected_sha:raise ValueError('saved_receipt_hash_mismatch')
  raw=json.loads(saved[0]);normalized=normalize_receipt(raw)
  context=json.loads(ex[6])
  if (context.get('task_id')!=task_id or context.get('requires_decomposition') is not True or
      context.get('input_reference')!=task['input_reference']):
   raise ValueError('planning_context_mismatch')
  if normalized.get('kind')!='plan':raise ValueError('saved_not_plan')
  if not all(b['allowed_mutations']==[] for b in normalized['plan']):raise ValueError('plan_mutation_not_permitted')
  Journal.task_document(None,task['origin_chat'],task['goal'],normalized['plan'])
  from .hermes_executor import HermesExecutor
  if HermesExecutor.verify(None,context,normalized) is not True:raise ValueError('plan_independent_verifier_rejected')
  ref=task['input_reference'];mid=ref['multipart_task_id']
  row=db.execute('SELECT body FROM multipart WHERE id=?',(mid,)).fetchone()
  if not row:raise ValueError('multipart_not_found')
  m=json.loads(row[0])
  if m.get('durable_task_id')!=task_id or m.get('status')!='DISPATCHED' or m.get('assembled_hash')!=ref['assembled_hash']:
   raise ValueError('multipart_reference_changed')
  parts=db.execute('SELECT number,text,hash FROM multipart_parts WHERE task=? ORDER BY number',(mid,)).fetchall()
  if not parts or [p[0] for p in parts]!=list(range(1,len(parts)+1)) or any(_sha_utf8(p[1])!=p[2] for p in parts):
   raise ValueError('multipart_parts_changed')
  assembled='\n\n'.join(p[1] for p in parts)
  if _sha_utf8(assembled)!=ref['assembled_hash']:raise ValueError('original_input_hash_mismatch')
  return dict(task_id=task_id,execution_id=execution_id,receipt_sha256=expected_sha,plan_blocks=len(normalized['plan']),mode='READ_ONLY',validated=True)
 finally:db.close()

class SavedOnly:
 def __init__(self,execution_id,raw):self.execution_id=execution_id;self.raw=raw
 def readback(self,rid,context):
  if rid!=self.execution_id:raise ValueError('unexpected_saved_execution')
  return json.loads(self.raw)
 def verify(self,context,outcome):
  from .hermes_executor import HermesExecutor
  return HermesExecutor.verify(None,context,outcome)
 def execute(self,*args,**kwargs):raise RuntimeError('model_execution_forbidden')
 def interrupt(self):pass

def apply(config,task_id,execution_id,expected_sha):
 # Worker owns this existing flock for its lifetime. Do not stop or signal it.
 root=Path(config['root']).absolute()
 lock=root/'worker-service.lock'
 if lock.is_symlink() or not lock.is_file():raise ValueError('worker_lock_missing')
 fd=os.open(lock,os.O_RDWR|os.O_NOFOLLOW)
 try:
  try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:raise ValueError('worker_running_apply_forbidden') from None
  # Re-read all bytes and all immutable anchors while holding the lock.
  metadata=inspect(config,task_id,execution_id,expected_sha)
  db=sqlite3.connect((root/'journal.sqlite').as_uri()+'?mode=ro',uri=True,timeout=5)
  try:
   db.execute('PRAGMA query_only=ON')
   raw=db.execute('SELECT body FROM runtime_receipts WHERE request=?',(execution_id,)).fetchone()[0]
  finally:db.close()
  j=Journal(root)
  try:
   q=TaskQueue(j,allowed_scope=tuple(config['scope']))
   worker=Worker(q,SavedOnly(execution_id,raw),SavedOnly(execution_id,raw).verify,worker_id='saved-plan-offline-reconcile')
   if not worker.reconcile(task_id):raise ValueError('saved_plan_reconciliation_failed')
   state=q.status(task_id)['state'];task=j.get(task_id)
   if (state!='WAITING_NEXT_TURN' or task.get('requires_decomposition') is not False or
       task.get('completed_blocks') or task.get('status')=='DONE'):
    raise ValueError('unexpected_post_reconciliation_state')
   if j.db.execute('SELECT COUNT(*) FROM task_executions WHERE task=?',(task_id,)).fetchone()[0]!=1:
    raise ValueError('reexecution_detected')
   metadata.update(mode='APPLIED_OFFLINE',task_status=state,verified_original_execution_only=True)
   return metadata
  finally:j.close()
 finally:
  fcntl.flock(fd,fcntl.LOCK_UN)
  os.close(fd)

def main(argv=None):
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--config',required=True)
 parser.add_argument('--task-id',required=True)
 parser.add_argument('--execution-id',required=True)
 parser.add_argument('--receipt-sha256',required=True)
 parser.add_argument('--apply',action='store_true',help='Requires stopped Worker and explicit operator approval')
 args=parser.parse_args(argv)
 config=json.loads(Path(args.config).read_text(encoding='utf-8'))
 if config.get('devexec_write_enabled',False):raise ValueError('production_devexec_writes_must_be_disabled')
 result=(apply if args.apply else inspect)(config,args.task_id,args.execution_id,args.receipt_sha256)
 print(json.dumps(result,sort_keys=True))

if __name__=='__main__':main()
