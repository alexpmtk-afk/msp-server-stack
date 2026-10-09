"""Independent scoped worker. No Telegram polling or delivery in this service."""
import argparse,fcntl,json,os,signal,time,uuid,threading
from pathlib import Path
from .tasks import Journal,bounded
PROBES=[
 ('47fc93fd-4d76-4e9f-b34c-18c752762a1a','NOT YET ESTABLISHED','2026-10-07T06:12:44.998Z'),
 ('8a53ea8e-19fb-41ee-93d5-cc99a9bd8f25','NOT YET ESTABLISHED','2026-10-07T06:13:28.709Z'),
 ('129917b0-09df-4d21-8fb5-ef95ea889ed6','ModuleNotFoundError: module not recorded','2026-10-07T06:13:37.210Z'),
 ('6f6c9b43-5d7b-47a4-8529-9247aa9115e0','ModuleNotFoundError: ruamel','2026-10-07T06:13:47.441Z'),
 ('faa87cf4-4a80-4057-89b6-afaccf911e9b','child import apps.operator_layer failed; parent EOFError','2026-10-07T06:14:04.461Z')]
def migrate(j):
 db=j.db
 db.executescript('''CREATE TABLE IF NOT EXISTS schema_versions(version INTEGER PRIMARY KEY, applied_at REAL);
 CREATE TABLE IF NOT EXISTS receipt_normalizations(request TEXT PRIMARY KEY,raw_body TEXT NOT NULL,raw_hash TEXT NOT NULL,schema_version INTEGER,normalized_body TEXT,error TEXT);
 CREATE TABLE IF NOT EXISTS recovery_tombstones(task_id TEXT PRIMARY KEY,state TEXT NOT NULL,reason TEXT,observed_at TEXT,probe_marker TEXT,retry_allowed INTEGER NOT NULL CHECK(retry_allowed=0),reconciliation TEXT NOT NULL);
 ''')
 # Compatible additive migration: original journal remains the task authority.
 from .queue import TaskQueue
 TaskQueue(j,allowed_scope=('migration','migration','migration','migration'),_migrating=True)
 for table,fields in {
 'task_queue':{'available_at':'REAL NOT NULL DEFAULT 0','lease_started_at':'REAL','heartbeat_at':'REAL','generation':'INTEGER NOT NULL DEFAULT 0'},
 'task_executions':{'execution_id':'TEXT','finished_at':'REAL','codex_thread_id':'TEXT','codex_turn_id':'TEXT','error':'TEXT','reconciliation':'TEXT'},
 'outbox':{'outbox_id':'TEXT','status':"TEXT NOT NULL DEFAULT 'PENDING'",'created_at':'REAL','delivered_at':'REAL','delivery_receipt':'TEXT'}
 }.items():
  columns={r[1] for r in db.execute('PRAGMA table_info('+table+')')}
  for name,typ in fields.items():
   if name not in columns:db.execute('ALTER TABLE '+table+' ADD COLUMN '+name+' '+typ)
 db.execute("UPDATE task_executions SET execution_id=request WHERE execution_id IS NULL")
 db.execute("UPDATE outbox SET outbox_id=task,created_at=COALESCE(created_at,?) WHERE outbox_id IS NULL",(time.time(),))
 db.execute("UPDATE outbox SET status='DELIVERED' WHERE delivered=1")
 db.executescript('''CREATE VIEW IF NOT EXISTS durable_tasks AS SELECT id AS task_id,json_extract(body,'$.status') AS status,json_extract(body,'$.current_block') AS current_step,json_extract(body,'$.origin') AS origin,json_extract(body,'$.origin_chat') AS origin_chat,json_extract(body,'$.created_at') AS created_at,json_extract(body,'$.updated_at') AS updated_at FROM tasks;
 CREATE VIEW IF NOT EXISTS queue AS SELECT task AS task_id,state AS status,available_at,worker AS lease_owner,lease_started_at,lease_expires AS lease_expires_at,heartbeat_at,generation,token AS fencing_token FROM task_queue;
 CREATE VIEW IF NOT EXISTS executions AS SELECT execution_id,task AS task_id,request AS request_id,block AS execution_step,state,started AS started_at,finished_at,codex_thread_id,codex_turn_id,result AS receipt,error,reconciliation FROM task_executions;
 CREATE TRIGGER IF NOT EXISTS outbox_metadata AFTER INSERT ON outbox BEGIN UPDATE outbox SET outbox_id=NEW.task,created_at=CAST(strftime('%s','now') AS REAL) WHERE task=NEW.task; END;''')
 db.execute('INSERT OR IGNORE INTO schema_versions VALUES (1,?)',(time.time(),));db.commit()
def quarantine_probes(j):
 with j.db:
  for tid,reason,at in PROBES:
   j.db.execute('INSERT OR IGNORE INTO recovery_tombstones VALUES (?,?,?,?,?,0,?)',(tid,'RECONCILIATION_REQUIRED',reason,at,'local-runtime-probe','UNRESOLVED_TEMPORARY_JOURNAL_REMOVED'))
class Outbox:
 """At-most-once admission. Unknown delivery is NEVER blindly resent."""
 def __init__(self,j):self.j=j
 def acquire(self):
  db=self.j.db;db.execute('BEGIN IMMEDIATE')
  try:
   r=db.execute("SELECT task,origin,body FROM outbox WHERE status='PENDING' AND delivered=0 LIMIT 1").fetchone()
   if r:db.execute("UPDATE outbox SET status='DELIVERY_UNKNOWN',outbox_id=task,created_at=COALESCE(created_at,?) WHERE task=?",(time.time(),r[0]))
   db.commit();return dict(task_id=r[0],origin_chat=r[1],payload=json.loads(r[2])) if r else None
  except BaseException:db.rollback();raise
 def ack(self,tid,receipt):
  bounded(receipt)
  with self.j.db:
   n=self.j.db.execute("UPDATE outbox SET status='DELIVERED',delivered=1,delivered_at=?,delivery_receipt=? WHERE task=? AND status='DELIVERY_UNKNOWN'",(time.time(),json.dumps(receipt),tid)).rowcount
   if n!=1:raise ValueError('delivery_not_claimed')
def acceptance(context,outcome):
 if outcome.get('kind')=='complete':return all(outcome.get('evidence',{}).get(k) is True for k in context['block']['acceptance'])
 return outcome.get('kind') in ('checkpoint','blocked')
class FixtureExecutor:
 def execute(self,context,source,rid,budget):
  return {'kind':'complete','evidence':{k:True for k in context['block']['acceptance']}}
 def interrupt(self):pass
 def readback(self,*args):return None

def main():
 p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--test-fixture',action='store_true');p.add_argument('--once',action='store_true');a=p.parse_args()
 config=json.loads(Path(a.config).read_text());j=Journal(config['root'])
 lock_fd=os.open(j.root/'worker-service.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
 try:fcntl.flock(lock_fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:
  os.close(lock_fd);j.close();raise SystemExit('worker_instance_already_active')
 migrate(j);quarantine_probes(j)
 from .queue import TaskQueue,Worker
 from .hermes_executor import HermesExecutor
 if a.test_fixture and not config.get('test_only',False):raise ValueError('fixture_requires_test_only_config')
 q=TaskQueue(j,allowed_scope=tuple(config['scope']))
 ex=FixtureExecutor() if a.test_fixture else HermesExecutor(j.root,profile=config['scope'][0],sandbox_enabled=config.get('sandbox_enabled',False),devexec_readonly_enabled=config.get('devexec_readonly_enabled',False),devexec_write_enabled=config.get('devexec_write_enabled',False))
 worker=Worker(q,ex,acceptance if a.test_fixture else ex.verify,worker_id='worker-'+str(uuid.uuid4()));stopping=False;wake=threading.Event()
 def stop(*args):
  nonlocal stopping
  stopping=True;wake.set();ex.interrupt()
 signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
 try:
  while not stopping:
   q.recover()
   # Recovery is readback-only: no receipt means BLOCKED, never a new execution.
   for (tid,) in list(j.db.execute("SELECT task FROM task_queue WHERE state='INTERRUPTED' AND scope=?",(q._scope_json(),))):
    worker.reconcile(tid)
   ran=worker.run_once()
   if config.get('telegram_delivery',False):
    from .production import deliver_once,telegram_sender
    deliver_once(j,q,telegram_sender,min_created_at=config.get('telegram_delivery_cutover_at'))
   if a.once:break
   if not ran:wake.wait(min(5,max(.05,config.get('poll',1))))
 finally:j.close();os.close(lock_fd)
if __name__=='__main__':main()
