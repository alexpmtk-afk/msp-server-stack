"""Read-only source reconciliation + durable once-per-period notifications."""
import datetime,fcntl,hashlib,json,os,re,sqlite3,stat,subprocess,sys,time,uuid
from pathlib import Path
from contextlib import closing
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parent))
import model
ROOT=Path(__file__).resolve().parent
BASE=Path('/var/lib/msp-finance-notices')
WB=Path('/var/lib/msp-wb-daily-weekly')
OZ=Path('/var/lib/msp-ozon-daily')
ARCHIVE=Path('/opt/mcp/data/msp-marketplace-reports')
TZ=ZoneInfo('Europe/Moscow')
def read_raw(path,uid=0):
 path=Path(path);s=path.lstat()
 if not stat.S_ISREG(s.st_mode) or s.st_uid!=uid or s.st_mode&0o022 or s.st_nlink!=1:raise ValueError('untrusted metadata')
 return path.read_bytes()
def read(path,uid=0):return json.loads(read_raw(path,uid))
def save(path,value):
 path=Path(path);raw=(json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False)+'\n').encode();tmp=path.with_name('.'+path.name+'.'+uuid.uuid4().hex)
 fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644)
 try:
  with os.fdopen(fd,'wb',closefd=False) as f:f.write(raw);f.flush()
  os.fchmod(fd,0o644);os.fsync(fd)
 finally:os.close(fd)
 os.replace(tmp,path);fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY);os.fsync(fd);os.close(fd)
def cycle(base,key):
 p=base/'cycles'/(key+'.json')
 if not p.exists():return None
 value=read(p)
 if value.get('key')!=key:raise ValueError('cycle identity')
 return value
def indices():
 values={}
 for cab in model.WB:
  root=ARCHIVE/'wb-current-catalog'/cab;pin=read(root/'CURRENT.json',995)
  if not re.fullmatch('[0-9a-f]{32}',pin.get('generation','')):raise ValueError('view generation')
  raw=read_raw(root/'generations'/pin['generation']/'view.json',995)
  if hashlib.sha256(raw).hexdigest()!=pin['sha256']:raise ValueError('view integrity')
  view=json.loads(raw)
  if view['cabinet']!=cab:raise ValueError('view cabinet')
  values[cab]={'reports':{str(i):r for i,r in enumerate(view['sources'])}}
 return values
def deliver(report):
 # Claim is durable before constructing the only sender process.
 key=report['kind']+'-'+report['day'];ledger=BASE/'deliveries'/(key+'.json');outbox=BASE/'outbox'/(key+'.json')
 if ledger.exists():return read(ledger)
 text=model.render(report);save(outbox,report);save(ledger,dict(status='SENDING',kind=report['kind'],day=report['day'],text_sha256=hashlib.sha256(text.encode()).hexdigest()))
 try:
  cmd=['/usr/sbin/runuser','-u','hermes','--','/usr/bin/python3','-I','-B',str(ROOT/'sender.py'),str(outbox)]
  done=subprocess.run(cmd,capture_output=True,text=True,timeout=35,check=True);answer=json.loads(done.stdout)
  if answer.get('status')!='SENT' or answer.get('chat_id')!=-1002485321031 or answer.get('thread_id')!=758 or type(answer.get('message_id')) is not int or answer.get('text_sha256')!=hashlib.sha256(text.encode()).hexdigest():raise ValueError('acknowledgement mismatch')
 except Exception as exc:answer=dict(status='DELIVERY_UNCERTAIN',error_type=type(exc).__name__)
 answer.update(kind=report['kind'],day=report['day']);save(ledger,answer);return answer
def status(path):return read(path).get('status') if path.exists() else None
def workload(pending):
 path=BASE/'queue.sqlite3'
 with closing(sqlite3.connect(path)) as db, db:
  db.execute('CREATE TABLE IF NOT EXISTS items (id TEXT PRIMARY KEY, state TEXT NOT NULL)')
  db.execute('DELETE FROM items')
  for row in pending:db.execute('INSERT INTO items VALUES (?,?)',(row['kind']+'-'+row['day'],row['status']))
 os.chmod(path,0o644)
def tick(now):
 now=now.astimezone(TZ);cfg=read(BASE/'config.json');first=datetime.date.fromisoformat(cfg['first_run_date']);today=now.astimezone(TZ).date();pending=[];sent=0
 for n in range((today-first).days+1):
  run_date=first+datetime.timedelta(days=n);key=run_date.isoformat();day=(run_date-datetime.timedelta(days=1)).isoformat()
  if run_date==today and (now.hour,now.minute)<(8,45):continue
  daily_path=BASE/'deliveries'/('daily-'+day+'.json');week_path=BASE/'deliveries'/('weekly-'+day+'.json');daily_status=status(daily_path);weekly_status=status(week_path) if run_date.weekday()==0 else 'NOT_APPLICABLE'
  if daily_status=='SENT' and weekly_status in ('SENT','NOT_APPLICABLE'):continue
  wc=cycle(WB,key);oc=cycle(OZ,key)
  if daily_status is None:
   report=model.daily(wc,oc,read(WB/'jobs.json'),read(OZ/'catalog.json'),day,indices())
   if report is None:pending.append(dict(kind='daily',day=day,status='UNKNOWN' if wc is None or oc is None else 'WAITING_FOR_SOURCE_COMPLETION'))
   else:
    daily_status=deliver(report)['status'];sent+=1
    if daily_status!='SENT':pending.append(dict(kind='daily',day=day,status='DELIVERY_UNCERTAIN_NO_REPLAY'))
  elif daily_status!='SENT':pending.append(dict(kind='daily',day=day,status='DELIVERY_UNCERTAIN_NO_REPLAY'))
  if run_date.weekday()==0 and weekly_status!='SENT':
   if daily_status!='SENT':pending.append(dict(kind='weekly',day=day,status='WAITING_FOR_DAILY_DELIVERY'))
   elif weekly_status is None:
    report=model.weekly(wc,read(WB/'jobs.json'),day)
    if report is None:pending.append(dict(kind='weekly',day=day,status='UNKNOWN' if wc is None else 'WAITING_FOR_SOURCE_COMPLETION'))
    else:
     answer=deliver(report);sent+=1
     if answer['status']!='SENT':pending.append(dict(kind='weekly',day=day,status='DELIVERY_UNCERTAIN_NO_REPLAY'))
   else:pending.append(dict(kind='weekly',day=day,status='DELIVERY_UNCERTAIN_NO_REPLAY'))
  if sent>=2:break
 value=dict(status='WAITING' if pending else 'IDLE',pending=pending,queue_size=len(pending),notification_attempts=sent,background_model_calls=0)
 workload(pending);save(BASE/'status.json',value);return value
def main():
 if os.geteuid()!=0:raise PermissionError('root required')
 lock=BASE/'lock';s=lock.lstat()
 if s.st_uid!=0 or not stat.S_ISREG(s.st_mode) or s.st_mode&0o077:raise ValueError('notice lock')
 with lock.open('rb') as f:
  fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);tick(datetime.datetime.now(TZ))
if __name__=='__main__':
 if sys.argv[1:] not in ([],['--serve']):raise SystemExit(2)
 while True:
  try:main()
  except BlockingIOError:pass
  except Exception as exc:
   if os.geteuid()==0 and BASE.exists():
    workload([dict(kind='system',day='source',status='UNKNOWN')]);save(BASE/'status.json',dict(status='UNKNOWN',queue_size=None,error_type=type(exc).__name__,background_model_calls=0))
   if '--serve' not in sys.argv:raise SystemExit(2)
  if '--serve' not in sys.argv:break
  time.sleep(60)
