"""Explicit input assembly, not a debounce and never an executor.
Uses the same private FULL-synchronous database as the Durable Journal.
All scope keys must be supplied by authenticated routing, never parsed from text.
"""
import hashlib,json,re,time,uuid
from .tasks import stamp
HEADER=re.compile(r'^TASK\s+(\d+)/(\d+)(?:\s+(END))?(?:\s*[—–-]\s*(.*))?\s*$',re.I)
CONTROLS={'/task begin','/task end','/task status','/task cancel'}
OPEN=('COLLECTING','COMPLETE','ASSEMBLED','ERROR')
MAX_PARTS=128
MAX_BYTES=256_000
PLANNING=[dict(goal='Plan collected task into bounded execution blocks',acceptance=['plan_approved'],allowed_mutations=[],expected_output='typed plan with capabilities and acceptance',dependencies=[],readback='verify assembled input hash and plan',rollback='cancel unexecuted plan')]

def digest(text):return hashlib.sha256(text.encode()).hexdigest()
def scope_key(scope):
 if len(scope)!=4 or any(not isinstance(x,str) or not x or len(x)>256 for x in scope):raise ValueError('invalid_scope')
 return json.dumps(scope,separators=(',',':'))

class Collector:
 def __init__(self,journal):
  self.j=journal;self.db=journal.db
  self.db.executescript('''
CREATE TABLE IF NOT EXISTS multipart(id TEXT PRIMARY KEY, scope TEXT NOT NULL, body TEXT NOT NULL, state TEXT NOT NULL);
CREATE UNIQUE INDEX IF NOT EXISTS multipart_open_scope_v2 ON multipart(scope) WHERE state IN ('COLLECTING','COMPLETE','ASSEMBLED','ERROR');
CREATE TABLE IF NOT EXISTS multipart_parts(task TEXT NOT NULL, number INTEGER NOT NULL, message_id TEXT NOT NULL, update_id INTEGER, received_at REAL NOT NULL, text TEXT NOT NULL, hash TEXT NOT NULL, PRIMARY KEY(task,number));
CREATE TABLE IF NOT EXISTS multipart_receipts(scope TEXT NOT NULL, message_id TEXT NOT NULL, update_id INTEGER, fingerprint TEXT NOT NULL, task TEXT NOT NULL, PRIMARY KEY(scope,message_id));
CREATE UNIQUE INDEX IF NOT EXISTS multipart_update ON multipart_receipts(scope,update_id) WHERE update_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS multipart_dispatch(task TEXT PRIMARY KEY, durable TEXT UNIQUE NOT NULL, state TEXT NOT NULL);
''')
 def _get(self,mid):
  r=self.db.execute('SELECT body FROM multipart WHERE id=?',(mid,)).fetchone()
  if not r:raise ValueError('unknown_collection')
  return json.loads(r[0])
 def _put(self,d):
  if d.get('durable_task_id') and d['status'] in ('ERROR','CANCELLED'):
   self.db.execute("DELETE FROM multipart_dispatch WHERE task=? AND state='PENDING'",(d['multipart_task_id'],))
   task=self.j.get(d['durable_task_id']);task['status']='CANCELLED' if d['status']=='CANCELLED' else 'BLOCKED';task['next_action']='multipart '+d['status'].lower();task['updated_at']=stamp()
   self.db.execute('UPDATE tasks SET body=? WHERE id=?',(json.dumps(task),task['task_id']))
  d['updated_at']=stamp();self.db.execute('INSERT OR REPLACE INTO multipart VALUES (?,?,?,?)',(d['multipart_task_id'],d['scope'],json.dumps(d),d['status']))
 def _open(self,key):
  r=self.db.execute("SELECT body FROM multipart WHERE scope=? AND state IN ('COLLECTING','COMPLETE','ASSEMBLED','ERROR')",(key,)).fetchone()
  return json.loads(r[0]) if r else None
 def status(self,mid):
  d=self._get(mid);numbers=[r[0] for r in self.db.execute('SELECT number FROM multipart_parts WHERE task=? ORDER BY number',(mid,))]
  return {k:d[k] for k in ('multipart_task_id','status','mode','expected_parts','final_received','assembled_hash','durable_task_id')}|{'received_parts':numbers,'missing_parts':[n for n in range(1,(d['expected_parts'] or 0)+1) if n not in numbers],'consumed':True}
 def _reply(self,d,reason=None):
  r=self.status(d['multipart_task_id'])
  if reason:r['reason']=reason
  return r
 def _new(self,key,scope,mode,expected):
  now=stamp();mid=str(uuid.uuid4())
  d=dict(multipart_task_id=mid,scope=key,origin_chat=scope[2],routing_session_key=scope[3],owner=scope[1],profile=scope[0],mode=mode,expected_parts=expected,status='COLLECTING',created_at=now,updated_at=now,final_received=False,assembled_hash=None,durable_task_id=None,last_error=None)
  self._put(d);return d
 def receive(self,scope,message_id,update_id,text,received_at=None):
  key=scope_key(scope)
  if not isinstance(message_id,str) or not message_id or len(message_id)>128 or not isinstance(text,str):raise ValueError('invalid_message')
  if update_id is not None and (not isinstance(update_id,int) or isinstance(update_id,bool)):raise ValueError('invalid_update')
  first,sep,rest=text.partition('\n');h=HEADER.fullmatch(first.strip());control=text.strip().lower();fp=digest(text)
  # IMMEDIATE serializes independent processes. Never await a provider in this transaction.
  self.db.execute('BEGIN IMMEDIATE')
  try:
   replay=self.db.execute('SELECT task,fingerprint FROM multipart_receipts WHERE scope=? AND (message_id=? OR (? IS NOT NULL AND update_id=?))',(key,message_id,update_id,update_id)).fetchone()
   if replay:
    d=self._get(replay[0])
    uncertain=self.db.execute("SELECT 1 FROM multipart_dispatch WHERE task=? AND state='UNKNOWN'",(d['multipart_task_id'],)).fetchone()
    if replay[1]!=fp and d['status'] in OPEN and not uncertain:d['status']='ERROR';d['last_error']='message_replay_conflict';self._put(d)
    result=self._reply(d,'duplicate_update' if replay[1]==fp else 'message_replay_conflict')
   else:
    d=self._open(key)
    explicit=h is not None or control.startswith('/task') or re.match(r'^TASK\s+\d+/',first,re.I)
    if not d and not explicit:
     result={'consumed':False}
    else:
     result,d=self._receive_new(key,scope,d,message_id,update_id,text,h,control,rest,received_at)
     if d:
      self.db.execute('INSERT INTO multipart_receipts VALUES (?,?,?,?,?)',(key,message_id,update_id,fp,d['multipart_task_id']))
   self.db.commit();return result
  except BaseException:self.db.rollback();raise
 def _receive_new(self,key,scope,d,message_id,update_id,text,h,control,rest,at):
  if d and control!='/task status' and self.db.execute("SELECT 1 FROM multipart_dispatch WHERE task=? AND state='UNKNOWN'",(d['multipart_task_id'],)).fetchone():return self._reply(d,'dispatch_uncertain_readback_required'),d
  if control.startswith('/task'):
   if control not in CONTROLS:return {'consumed':True,'reason':'invalid_task_control'},d
   if control=='/task status':return (self._reply(d) if d else {'consumed':True,'reason':'no_open_collection'}),d
   if control=='/task begin':
    if d:return self._reply(d,'collection_already_open'),d
    d=self._new(key,scope,'manual',None);return self._reply(d),d
   if not d:return {'consumed':True,'reason':'no_open_collection'},None
   if control=='/task cancel':
    d['status']='CANCELLED';self._put(d);return self._reply(d),d
   if d['status'] in ('COMPLETE','ASSEMBLED') and control=='/task end':return self._reply(d,'already_complete'),d
   if d['mode']!='manual':return self._reply(d,'numbered_requires_final_end'),d
   if d['status']=='ERROR':return self._reply(d,'collection_error'),d
   if not self.db.execute('SELECT 1 FROM multipart_parts WHERE task=?',(d['multipart_task_id'],)).fetchone():return self._reply(d,'empty_collection'),d
   d['final_received']=True;d['status']='COMPLETE';self._put(d);return self._reply(d),d
  if h:
   n,total=int(h[1]),int(h[2]);final=bool(h[3]);body='\n'.join(x for x in (h[4],rest) if x is not None and x!='')
   if not 1<=n<=total<=MAX_PARTS or (final and n!=total):return {'consumed':True,'reason':'invalid_part_number'},d
   if not d:
    if n!=1:return {'consumed':True,'reason':'first_part_required'},None
    d=self._new(key,scope,'numbered',total)
   if d['mode']!='numbered':return self._reply(d,'mode_conflict'),d
   if d['expected_parts']!=total:
    d['status']='ERROR';d['last_error']='part_count_conflict';self._put(d);return self._reply(d,'part_count_conflict'),d
  else:
   if d and d['mode']=='manual':
    n=self.db.execute('SELECT COALESCE(MAX(number),0)+1 FROM multipart_parts WHERE task=?',(d['multipart_task_id'],)).fetchone()[0];body=text;final=False
   else:return (self._reply(d,'finish_or_cancel_current_collection') if d else {'consumed':True,'reason':'invalid_task_header'}),d
  if d['status']=='ERROR':return self._reply(d,'collection_error'),d
  if d['status'] in ('COMPLETE','ASSEMBLED') and not h:return self._reply(d,'collection_already_complete'),d
  existing=self.db.execute('SELECT hash FROM multipart_parts WHERE task=? AND number=?',(d['multipart_task_id'],n)).fetchone()
  if existing:
   if existing[0]!=digest(body):d['status']='ERROR';d['last_error']='conflicting_part';self._put(d);return self._reply(d,'conflicting_part'),d
  else:
   size=self.db.execute('SELECT COALESCE(SUM(length(CAST(text AS BLOB))),0) FROM multipart_parts WHERE task=?',(d['multipart_task_id'],)).fetchone()[0]
   if n>MAX_PARTS or size+len(body.encode())>MAX_BYTES:
    d['status']='ERROR';d['last_error']='collection_limit';self._put(d);return self._reply(d,'collection_limit'),d
   self.db.execute('INSERT INTO multipart_parts VALUES (?,?,?,?,?,?,?)',(d['multipart_task_id'],n,message_id,update_id,time.time() if at is None else at,body,digest(body)))
  d['final_received']=d['final_received'] or final
  count=self.db.execute('SELECT COUNT(*) FROM multipart_parts WHERE task=?',(d['multipart_task_id'],)).fetchone()[0]
  if d['status']!='ASSEMBLED' and d['mode']=='numbered' and d['final_received'] and count==d['expected_parts']:d['status']='COMPLETE'
  self._put(d);return self._reply(d),d
 def assemble(self,mid):
  self.db.execute('BEGIN IMMEDIATE')
  try:
   d=self._get(mid)
   if d['status'] in ('ASSEMBLED','DISPATCHED'):
    self.db.commit();return self.status(mid)
   if d['status']!='COMPLETE':raise ValueError('collection_not_complete')
   rows=self.db.execute('SELECT number,text,hash FROM multipart_parts WHERE task=? ORDER BY number',(mid,)).fetchall()
   expected=d['expected_parts'] or len(rows)
   if not d['final_received'] or [r[0] for r in rows]!=list(range(1,expected+1)) or any(digest(r[1])!=r[2] for r in rows):raise ValueError('assembly_integrity_error')
   assembled='\n\n'.join(r[1] for r in rows)
   tid=str(uuid.uuid5(uuid.NAMESPACE_URL,'hermes-multipart:'+mid))
   task=self.j.task_document(d['origin_chat'],'Plan collected multipart task',PLANNING,task_id=tid)
   task['requires_decomposition']=True
   task['status']='PLANNING'
   task['input_reference']={'multipart_task_id':mid,'assembled_hash':digest(assembled)}
   self.db.execute('INSERT INTO tasks VALUES (?,?)',(tid,json.dumps(task)))
   self.db.execute('INSERT INTO events(task,kind,body) VALUES (?,?,?)',(tid,'multipart_created',json.dumps(task)))
   d['assembled_hash']=digest(assembled);d['durable_task_id']=tid;d['status']='ASSEMBLED';self._put(d)
   self.db.execute("INSERT INTO multipart_dispatch VALUES (?,?,'PENDING')",(mid,tid))
   self.db.commit();return self.status(mid)
  except BaseException:self.db.rollback();raise
 def input_for(self,tid):
  task=self.j.get(tid);ref=task.get('input_reference')
  if not ref:raise ValueError('no_input_reference')
  d=self._get(ref['multipart_task_id'])
  if d['status'] not in ('ASSEMBLED','DISPATCHED') or d['durable_task_id']!=tid:raise ValueError('input_not_assembled')
  rows=self.db.execute('SELECT text FROM multipart_parts WHERE task=? ORDER BY number',(d['multipart_task_id'],)).fetchall();text='\n\n'.join(r[0] for r in rows)
  if digest(text)!=ref['assembled_hash']:raise ValueError('input_hash_mismatch')
  return text
 def pending(self):return [dict(multipart_task_id=r[0],durable_task_id=r[1],dispatch_state=r[2]) for r in self.db.execute("SELECT * FROM multipart_dispatch WHERE state!='ACKNOWLEDGED'")]
 def recover(self):
  ids=[r[0] for r in self.db.execute("SELECT id FROM multipart WHERE state='COMPLETE'")]
  for mid in ids:self.assemble(mid)
  return self.pending()
 def expire(self,mid):
  with self.db:
   d=self._get(mid)
   if d['status']!='COLLECTING':raise ValueError('only_collecting_can_expire')
   d['status']='EXPIRED';self._put(d)

 def prepare_dispatch(self,mid):
  """Persist UNKNOWN BEFORE transport. Caller must read back after any response.
  A dispatcher must hold the origin session writer lock; this is not a Codex call.
  """
  self.db.execute('BEGIN IMMEDIATE')
  try:
   d=self._get(mid)
   if d['status']!='ASSEMBLED':raise ValueError('not_dispatchable')
   row=self.db.execute('SELECT state FROM multipart_dispatch WHERE task=?',(mid,)).fetchone()
   if not row or row[0]!='PENDING':raise ValueError('dispatch_readback_required')
   self.db.execute("UPDATE multipart_dispatch SET state='UNKNOWN' WHERE task=?",(mid,));self.db.commit()
   return {'operation':'submit_operator_task','request_id':'multipart:'+mid,'task_id':d['durable_task_id'],'multipart_task_id':mid,'profile':d['profile'],'owner':d['owner'],'origin_chat':d['origin_chat'],'session_key':d['routing_session_key'],'input_hash':d['assembled_hash']}
  except BaseException:self.db.rollback();raise
 def confirm_dispatch(self,mid,receipt):
  """receipt must be an independent scoped queue readback, not transport success."""
  self.db.execute('BEGIN IMMEDIATE')
  try:
   d=self._get(mid)
   if receipt!={'request_id':'multipart:'+mid,'task_id':d['durable_task_id'],'accepted':True}:raise ValueError('invalid_dispatch_readback')
   row=self.db.execute('SELECT state FROM multipart_dispatch WHERE task=?',(mid,)).fetchone()
   if d['status'] not in ('ASSEMBLED','DISPATCHED') or not row or row[0] not in ('UNKNOWN','ACKNOWLEDGED'):raise ValueError('no_dispatch_attempt')
   self.db.execute("UPDATE multipart_dispatch SET state='ACKNOWLEDGED' WHERE task=?",(mid,));d['status']='DISPATCHED';self._put(d);self.db.commit()
  except BaseException:self.db.rollback();raise
 def confirm_not_dispatched(self,mid,receipt):
  self.db.execute('BEGIN IMMEDIATE')
  try:
   d=self._get(mid)
   if receipt!={'request_id':'multipart:'+mid,'task_id':d['durable_task_id'],'accepted':False} or d['status']!='ASSEMBLED':raise ValueError('invalid_dispatch_readback')
   c=self.db.execute("UPDATE multipart_dispatch SET state='PENDING' WHERE task=? AND state='UNKNOWN'",(mid,))
   if c.rowcount!=1:raise ValueError('no_unknown_dispatch')
   self.db.commit()
  except BaseException:self.db.rollback();raise
