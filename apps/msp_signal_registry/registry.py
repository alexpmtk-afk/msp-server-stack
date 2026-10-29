"""Passive six-signal event ledger. No network, action execution or Telegram polling."""
from __future__ import annotations
import argparse, hashlib, json, os, re, sqlite3, time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path('/home/hermes/.local/share/msp/signal-registry')
DB=Path('/opt/mcp/data/msp/msp_signal_registry.sqlite3')
SOURCE='-1003375632914'
REMOTE='-1002485321031'
GROUP='-1004306291068'
OWNER='639699477'
ARCHIVE=Path('/home/hermes/.hermes/channel-archive/messages.sqlite3')
DATA=Path('/opt/mcp/data/msp/msp_data.sqlite3')
BUTTONS=Path('/opt/mcp/data/msp/msp_signal_price_buttons.sqlite3')
NOTIFY=Path('/opt/mcp/data/msp/msp_signal_notifications.sqlite3')
WORKFLOW=Path('/home/hermes/.local/share/msp/sig032-approval/workflow.sqlite3')
DIRECT=Path('/opt/mcp/data/msp/msp_sig032_approval_events.sqlite3')
RULES=[('SIG-002','Поднять цену',r'\bподнять\s+цен[уы]\b'),('SIG-016','Обнулить FBS',r'\bнужно\s+обнулить\s+fbs\b'),('SIG-015','Обнулённые остатки',r'\bкарточки\s+с\s+обнуленн\w*\s+остатк\w*'),('SIG-021','Расход рекламы',r'\bпревышен\s+расход\s+по\s+рк\b'),('SIG-022','Высокий ДРР',r'\bаномально\s+высокий\s+дрр\b'),('SIG-032','Размеры/вес',r'\bрасхождени\w*\s+(?:в\s+)?размер\w*|\bрасхождени\w*.*\bвес\w*')]
DDL='''
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS signal_types(code TEXT PRIMARY KEY,title TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS signals(id INTEGER PRIMARY KEY,chat_id TEXT NOT NULL,message_id INTEGER NOT NULL,type TEXT NOT NULL REFERENCES signal_types(code),received_at TEXT NOT NULL,first_read_at TEXT NOT NULL,last_read_at TEXT NOT NULL,text TEXT NOT NULL,source_url TEXT NOT NULL,historical INTEGER NOT NULL DEFAULT 0,extra_json TEXT NOT NULL DEFAULT '{}',UNIQUE(chat_id,message_id,type));
CREATE TABLE IF NOT EXISTS subjects(signal_id INTEGER NOT NULL REFERENCES signals(id),kind TEXT NOT NULL,value TEXT NOT NULL,marketplace TEXT NOT NULL DEFAULT '',store TEXT NOT NULL DEFAULT '',origin TEXT NOT NULL,PRIMARY KEY(signal_id,kind,value,marketplace,store));
CREATE INDEX IF NOT EXISTS subjects_value ON subjects(value);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,signal_id INTEGER REFERENCES signals(id),key TEXT UNIQUE NOT NULL,kind TEXT NOT NULL,occurred_at TEXT,observed_at TEXT NOT NULL,actor_id TEXT,chat_id TEXT,message_id TEXT,payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS messages(chat_id TEXT NOT NULL,message_id TEXT NOT NULL,at TEXT NOT NULL,actor_id TEXT,text TEXT NOT NULL,reply_id TEXT,thread_id TEXT,is_bot INTEGER NOT NULL,PRIMARY KEY(chat_id,message_id));
CREATE TABLE IF NOT EXISTS links(chat_id TEXT NOT NULL,message_id TEXT NOT NULL,signal_id INTEGER NOT NULL REFERENCES signals(id),method TEXT NOT NULL,PRIMARY KEY(chat_id,message_id,signal_id));
CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY,chat_id TEXT NOT NULL,message_id TEXT NOT NULL,at TEXT,observed_at TEXT NOT NULL,actor_id TEXT,text TEXT NOT NULL,signal_id INTEGER REFERENCES signals(id),match_state TEXT NOT NULL,candidates_json TEXT NOT NULL,method TEXT,UNIQUE(chat_id,message_id));
CREATE TABLE IF NOT EXISTS actions(id INTEGER PRIMARY KEY,signal_id INTEGER REFERENCES signals(id),source_key TEXT NOT NULL,job_id TEXT NOT NULL,offer_id TEXT,marketplace TEXT NOT NULL DEFAULT '',cabinet TEXT NOT NULL DEFAULT '',status TEXT NOT NULL,detail TEXT NOT NULL,occurred_at TEXT,observed_at TEXT NOT NULL,evidence_json TEXT NOT NULL,UNIQUE(source_key,job_id,offer_id,marketplace,cabinet));
CREATE TABLE IF NOT EXISTS health(source TEXT PRIMARY KEY,checked_at TEXT NOT NULL,error TEXT);
CREATE VIEW IF NOT EXISTS v_signal_registry AS
SELECT s.*, (SELECT MIN(f.at) FROM feedback f WHERE f.signal_id=s.id AND f.match_state IN ('linked','manual')) feedback_at,
(SELECT COUNT(*) FROM feedback f WHERE f.signal_id=s.id AND f.match_state IN ('linked','manual')) feedback_count,
CASE WHEN EXISTS(SELECT 1 FROM feedback f WHERE f.signal_id=s.id AND f.match_state IN ('linked','manual')) THEN 'отработан: обратная связь' ELSE 'ожидает обратной связи' END handling,
(SELECT group_concat(a.marketplace||'/'||a.cabinet||': '||a.status||' — '||a.detail,'; ') FROM actions a WHERE a.signal_id=s.id) action_summary,
(SELECT MAX(f.at) FROM feedback f WHERE f.signal_id=s.id AND f.match_state IN ('linked','manual')) last_feedback_at,
CASE
 WHEN EXISTS(SELECT 1 FROM actions a WHERE a.signal_id=s.id AND a.status IN ('updated','already_equal')) AND EXISTS(SELECT 1 FROM actions a WHERE a.signal_id=s.id AND a.status NOT IN ('updated','already_equal')) THEN 'partial'
 WHEN EXISTS(SELECT 1 FROM actions a WHERE a.signal_id=s.id AND a.status IN ('pending','unknown') OR (a.signal_id=s.id AND a.status LIKE 'execution_%')) THEN 'unverified'
 WHEN EXISTS(SELECT 1 FROM actions a WHERE a.signal_id=s.id AND a.status='failed') THEN 'failed'
 WHEN EXISTS(SELECT 1 FROM actions a WHERE a.signal_id=s.id AND a.status='simulation') THEN 'simulation'
 WHEN EXISTS(SELECT 1 FROM actions a WHERE a.signal_id=s.id AND a.status IN ('updated','already_equal')) THEN 'confirmed_results_available'
 ELSE 'not_started_or_not_recorded' END execution_summary
FROM signals s;
'''
def now():return datetime.now(timezone.utc).isoformat(timespec='seconds')
def js(v):return json.dumps(v,ensure_ascii=False,sort_keys=True)
def digest(v):return hashlib.sha256(js(v).encode()).hexdigest()
def connect(path=DB):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 c=sqlite3.connect(p,timeout=20);c.row_factory=sqlite3.Row
 c.execute('PRAGMA foreign_keys=ON');c.execute('PRAGMA journal_mode=WAL');c.execute('PRAGMA busy_timeout=20000');c.executescript(DDL)
 c.execute('INSERT OR IGNORE INTO meta VALUES(?,?)',('activated_at',now()))
 c.executemany('INSERT OR IGNORE INTO signal_types VALUES(?,?)',[(a,b) for a,b,_ in RULES]);c.commit();os.chmod(p,0o600)
 return c
def read(path,sql,args=()):
 if not Path(path).is_file():raise FileNotFoundError(str(path))
 with closing(sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True,timeout=15)) as c:
  c.row_factory=sqlite3.Row;c.execute('PRAGMA query_only=ON')
  return [dict(r) for r in c.execute(sql,args)]
def event(c,key,kind,payload,sid=None,at=None,actor=None,chat=None,mid=None):
 c.execute('INSERT OR IGNORE INTO events(signal_id,key,kind,occurred_at,observed_at,actor_id,chat_id,message_id,payload_json) VALUES(?,?,?,?,?,?,?,?,?)',(sid,key,kind,at,now(),actor,chat,str(mid) if mid is not None else None,js(payload)))
def classify(text):
 t=text.lower().replace('ё','е')
 return [code for code,_,pat in RULES if re.search(pat,t)]
def sid_for(c,post,code=None):
 q='SELECT id FROM signals WHERE chat_id=? AND message_id=?';args=[SOURCE,post]
 if code:q+=' AND type=?';args.append(code)
 return [r[0] for r in c.execute(q,args)]
def subject(c,sid,kind,value,market='',store='',origin='source'):
 c.execute('INSERT OR IGNORE INTO subjects VALUES(?,?,?,?,?,?)',(sid,kind,str(value),str(market or ''),str(store or ''),origin))
def ingest_signal(c,m,historical=False):
 ids=[]
 for code in classify(m['text']):
  c.execute('INSERT INTO signals(chat_id,message_id,type,received_at,first_read_at,last_read_at,text,source_url,historical) VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(chat_id,message_id,type) DO UPDATE SET text=excluded.text,last_read_at=excluded.last_read_at',(SOURCE,m['message_id'],code,m['date_utc'],now(),now(),m['text'],f"https://t.me/c/3375632914/{m['message_id']}",int(historical)))
  sid=sid_for(c,m['message_id'],code)[0];ids.append(sid)
  event(c,'signal:'+str(sid)+':'+digest(m['text']),'signal_read',m,sid,m['date_utc'])
  for value in re.findall(r'\(\s*(?:арт(?:икул)?\.?\s*[:№]?\s*)?(\d{5,15})\s*\)',m['text'],re.I):subject(c,sid,'sku',value)
  for value in re.findall(r'(?<![\w.])[A-Za-zА-Яа-я][\w-]*\.\d[\w.-]*(?![\w.])',m['text']):subject(c,sid,'internal_article',value)
 return ids
def add_link(c,chat,mid,sid,method):
 if mid is not None:c.execute('INSERT OR IGNORE INTO links VALUES(?,?,?,?)',(str(chat),str(mid),sid,method))
def candidates(c,text,code=None,before=None):
 # Exact token match only. No fuzzy product-name guessing.
 found=set()
 for r in c.execute('SELECT DISTINCT x.signal_id,x.value,s.type,s.received_at FROM subjects x JOIN signals s ON s.id=x.signal_id'):
  if code and r['type']!=code:continue
  if before and datetime.fromisoformat(r['received_at'].replace('Z','+00:00'))>datetime.fromisoformat(before.replace('Z','+00:00')):continue
  if re.search(r'(?<![\w.])'+re.escape(r['value'])+r'(?![\w.])',text,re.I):found.add(r['signal_id'])
 return sorted(found)
def match_feedback(c,m):
 if m['is_bot']:return
 if m['chat_id'] not in (REMOTE,GROUP,OWNER):return
 if m['chat_id']==REMOTE and str(m.get('thread_id'))!='758':return
 # Capture is not authorization to execute. Owner in remote/DM, all participants in Group.
 if m['chat_id']!=GROUP and str(m.get('actor_id'))!=OWNER:return
 explicit=[r[0] for r in c.execute('SELECT signal_id FROM links WHERE chat_id=? AND message_id=?',(m['chat_id'],str(m.get('reply_id'))))] if m.get('reply_id') else []
 explicit+= [r[0] for r in c.execute('SELECT signal_id FROM links WHERE chat_id=? AND message_id=?',(m['chat_id'],m['message_id']))]
 codes=classify(m['text'])
 if not codes and re.search(r'размер|габарит|\bвес\b',m['text'],re.I):codes=['SIG-032']
 linked=sorted(set(explicit));method='reply'
 if not linked:
  linked=candidates(c,m['text'],codes[0] if len(codes)==1 else None,m['at']);method='exact_subject'
 if not linked and not explicit:return
 state='linked' if len(linked)==1 else 'ambiguous';sid=linked[0] if state=='linked' else None
 old=c.execute('SELECT match_state FROM feedback WHERE chat_id=? AND message_id=?',(m['chat_id'],m['message_id'])).fetchone()
 if old and old[0]=='manual':return
 if old and old[0]=='linked':
  c.execute('UPDATE feedback SET text=? WHERE chat_id=? AND message_id=?',(m['text'],m['chat_id'],m['message_id']))
  return
 c.execute('INSERT INTO feedback(chat_id,message_id,at,observed_at,actor_id,text,signal_id,match_state,candidates_json,method) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(chat_id,message_id) DO UPDATE SET text=excluded.text,signal_id=excluded.signal_id,match_state=excluded.match_state,candidates_json=excluded.candidates_json,method=excluded.method',(m['chat_id'],m['message_id'],m['at'],now(),m.get('actor_id'),m['text'],sid,state,js(linked),method))
 if sid is not None:add_link(c,m['chat_id'],m['message_id'],sid,'linked_feedback')
 event(c,'feedback:'+m['chat_id']+':'+m['message_id']+':'+digest([m['text'],linked]),'feedback',{'text':m['text'],'candidates':linked,'method':method,'match_state':state},sid,m['at'],m.get('actor_id'),m['chat_id'],m['message_id'])
def capture_message(c,m):
 c.execute('INSERT INTO messages VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(chat_id,message_id) DO UPDATE SET text=excluded.text,reply_id=excluded.reply_id',(str(m['chat_id']),str(m['message_id']),m['at'],str(m.get('actor_id') or ''),m['text'],str(m['reply_id']) if m.get('reply_id') is not None else None,str(m['thread_id']) if m.get('thread_id') is not None else None,int(m.get('is_bot',False))))
 match_feedback(c,dict(c.execute('SELECT * FROM messages WHERE chat_id=? AND message_id=?',(str(m['chat_id']),str(m['message_id']))).fetchone()))
def feedback_record(c,key,sids,text,at,actor=None,chat=REMOTE,mid=None):
 # Legacy records with missing event time preserve NULL, never ingestion time.
 for sid in sids:
  event(c,key+':'+str(sid),'feedback',{'text':text,'legacy_time_unknown':at is None},sid,at,actor,chat,mid)
  c.execute('INSERT INTO feedback(chat_id,message_id,at,observed_at,actor_id,text,signal_id,match_state,candidates_json,method) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(chat_id,message_id) DO UPDATE SET at=COALESCE(feedback.at,excluded.at),actor_id=COALESCE(feedback.actor_id,excluded.actor_id)',(str(chat),(str(mid) if mid is not None and key.startswith(('workflow_reply:','direct:')) else key+':'+str(sid)),at,now(),str(actor) if actor else None,text,sid,'linked',js([sid]),'executor_receipt'))
def unpack(v):return v.get('data',v) if isinstance(v,dict) else {}
def evidence_error(value):
 if isinstance(value,dict):
  if value.get('success') is False or value.get('isError') is True:return True
  if any(value.get(k) for k in ('error','errors','error_text')):return True
  return any(evidence_error(x) for x in value.values())
 if isinstance(value,list):return any(evidence_error(x) for x in value)
 return False
def result(c,key,sids,offer,payload,at=None,expected_jobs=None):
 v=unpack(payload);job=v.get('job_id')
 if not job:return
 if expected_jobs is not None and job not in expected_jobs:return
 for item in v.get('results') or [{}]:
  if item.get('offer_id',offer)!=offer:continue
  error=item.get('error') or v.get('error') or v.get('errors') or v.get('error_text')
  status='unknown';vendor=item.get('status')
  if v.get('status')=='completed' and not evidence_error({k:x for k,x in payload.items() if k not in ('data','results')}) and not evidence_error({k:x for k,x in v.items() if k!='results'}) and not evidence_error(item) and vendor in ('OK','NOT'):
   status='updated' if vendor=='OK' else 'already_equal'
  elif vendor=='ERR' or v.get('status')=='failed':status='failed'
  elif v.get('status') in ('queued','processing','waiting_vendor'):status='pending'
  market=str(item.get('marketplace') or v.get('marketplace') or '')
  cabinet=str(item.get('blockid',v.get('blockid')) or '')
  detail=str(item.get('tooltip') or error or 'Результат не подтверждён')
  for sid in sids or [None]:
   src=key+':'+str(sid)
   c.execute('INSERT INTO actions(signal_id,source_key,job_id,offer_id,marketplace,cabinet,status,detail,occurred_at,observed_at,evidence_json) VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source_key,job_id,offer_id,marketplace,cabinet) DO UPDATE SET status=excluded.status,detail=excluded.detail,occurred_at=excluded.occurred_at,observed_at=excluded.observed_at,evidence_json=excluded.evidence_json',(sid,src,job,offer,market,cabinet,status,detail,at,now(),js(payload)))
   event(c,'result:'+src+':'+digest(payload),'action_result',payload,sid,at)
def checked(c,name,fn):
 try:fn();error=None
 except Exception as ex:error=type(ex).__name__+': '+str(ex)
 c.execute('INSERT INTO health VALUES(?,?,?) ON CONFLICT(source) DO UPDATE SET checked_at=excluded.checked_at,error=excluded.error',(name,now(),error))
 if error:print(js({'source':name,'error':error}),flush=True)
def sync(c):
 def source():
  activation=c.execute("SELECT value FROM meta WHERE key='activated_at'").fetchone()[0]
  for m in read(ARCHIVE,'SELECT * FROM messages WHERE chat_id=?',(SOURCE,)):
   historical=datetime.fromisoformat(m['date_utc'].replace('Z','+00:00'))<datetime.fromisoformat(activation)
   ingest_signal(c,m,historical=historical)
 checked(c,'channel_archive',source)
 def mappings():
  rows=read(DATA,'SELECT marketplace,store,marketplace_sku,internal_article FROM product_listing')
  by={}
  for r in rows:by.setdefault(r['marketplace_sku'],[]).append(r)
  for x in c.execute("SELECT * FROM subjects WHERE kind='sku'").fetchall():
   for r in by.get(x['value'],[]):
    subject(c,x['signal_id'],'sku',x['value'],r['marketplace'],r['store'],'product_listing')
    if r['internal_article']:subject(c,x['signal_id'],'internal_article',r['internal_article'],r['marketplace'],r['store'],'product_listing')
 checked(c,'product_mapping',mappings)
 def notifications():
  for r in read(NOTIFY,'SELECT * FROM notifications'):
   for sid in sid_for(c,r['message_id']):
    add_link(c,REMOTE,r['telegram_message_id'],sid,'notifier')
    event(c,'notification:'+str(sid)+':'+str(r['telegram_message_id']),'notification',r,sid,r['sent_utc'],chat=REMOTE,mid=r['telegram_message_id'])
 checked(c,'notifications',notifications)
 def buttons():
  for r in read(BUTTONS,'SELECT * FROM price_buttons'):
   sids=sid_for(c,r['source_message_id'],'SIG-002')
   for sid in sids:
    subject(c,sid,'sku',r['sku'],origin='price_button');add_link(c,REMOTE,r['sent_message_id'],sid,'price_button')
    event(c,'price_state:'+r['token']+':'+digest(r),'price_execution_observed',r,sid)
    if r['command_id']:
     c.execute('INSERT INTO actions(signal_id,source_key,job_id,offer_id,marketplace,cabinet,status,detail,observed_at,evidence_json) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source_key,job_id,offer_id,marketplace,cabinet) DO UPDATE SET status=excluded.status,detail=excluded.detail,observed_at=excluded.observed_at,evidence_json=excluded.evidence_json',(sid,'price:'+r['token'],str(r['command_id']),r['sku'],'','','execution_'+r['state'],'Orgobot: '+r['state']+'. Фактическое изменение цены не подтверждено.',now(),js(r)))
   if r['answer']:feedback_record(c,'decision:price:'+r['token'],sids,r['answer'],None,mid=r['sent_message_id'])
 checked(c,'price_buttons',buttons)
 def price_history():
  path=Path('/opt/mcp/data/msp/msp_sig002_price_journal.sqlite3')
  for r in read(path,'SELECT * FROM items'):
   for sid in sid_for(c,r['source_message_id'],'SIG-002'):
    if r['response_at_utc'] and r['decided_by_user_id']:
     matches=read(BUTTONS,'SELECT token FROM price_buttons WHERE source_message_id=? AND sku=? AND sent_message_id=?',(r['source_message_id'],r['sku'],r['card_message_id']))
     for match in matches:feedback_record(c,'decision:price:'+match['token'],[sid],r['response_status'],r['response_at_utc'],r['decided_by_user_id'],mid=r['card_message_id'])
    if r['orgobot_command_id']:
     # Actual confirmation and source fields are preserved as supplied, never inferred from done.
     payload={'sku':r['sku'],'command_id':r['orgobot_command_id'],'command_status':r['command_status'],'price_result':r['price_result'],'before':r['price_before'],'after':r['price_after'],'checked_at':r['price_checked_utc'],'evidence':r['price_evidence']}
     event(c,'price_journal:'+str(r['id'])+':'+digest(payload),'price_result_evidence',payload,sid,r['price_checked_utc'])
 checked(c,'price_journal',price_history)

 def workflow():
  cases=read(WORKFLOW,'SELECT * FROM cases')
  for r in cases:
   sids=sid_for(c,r['post'],'SIG-032')
   for sid in sids:
    subject(c,sid,'internal_article',r['offer'],origin='dimensions_case');add_link(c,REMOTE,r['source_mid'],sid,'dimensions_case')
    event(c,'dimensions_state:'+r['token']+':'+digest(r),'dimensions_execution_observed',r,sid)
   state_data=json.loads(r['result'] or '{}');expected=state_data.get('jobs',[])
   direct_source=state_data.get('direct_source')
   if isinstance(direct_source,dict) and direct_source.get('chat_id') and direct_source.get('message_id'):
    for sid in sids:add_link(c,direct_source['chat_id'],direct_source['message_id'],sid,'verified_executor_direct_link')
   for e in read(WORKFLOW,'SELECT rowid,* FROM events WHERE token=?',(r['token'],)):
    p=json.loads(e['payload'])
    for sid in sids:event(c,'workflow:'+str(e['rowid'])+':'+str(sid),e['kind'],p,sid,e['utc'],str(r.get('actor') or '') or None)
    if e['kind'] in ('owner_reply_received','native_reply_received'):feedback_record(c,'workflow_reply:'+str(e['rowid']),sids,p.get('text','Ответ получен'),e['utc'],r.get('actor'),mid=p.get('message_id'))
    if e['kind'] in ('job_status','final_audit_job_status'):result(c,'workflow:'+r['token'],sids,r['offer'],p,e['utc'],expected)
 checked(c,'dimensions_workflow',workflow)
 def direct():
  for r in read(DIRECT,'SELECT * FROM direct_dimensions_command'):
   # Only associate a direct instruction with a unique exact signal; keep ambiguous standalone.
   exact=[x[0] for x in c.execute("SELECT l.signal_id FROM links l JOIN signals s ON s.id=l.signal_id WHERE l.chat_id=? AND l.message_id=? AND s.type='SIG-032'",(r['chat_id'],str(r['message_id'])))]
   sids=exact or candidates(c,r['offer_id'],'SIG-032',r['created_utc']);sids=sids if len(sids)==1 else []
   for sid in sids:feedback_record(c,'direct:'+r['chat_id']+':'+str(r['message_id']),[sid],'Прямая команда размеров/веса: '+r['offer_id'],r['created_utc'],r['user_id'],r['chat_id'],r['message_id'])
   event(c,'direct_state:'+r['chat_id']+':'+str(r['message_id'])+':'+digest(r),'direct_execution_observed',{'command':r,'candidate_signals':candidates(c,r['offer_id'],'SIG-032',r['created_utc'])},sids[0] if sids else None,actor=str(r['user_id']),chat=r['chat_id'],mid=r['message_id'])
   for e in read(DIRECT,"SELECT rowid,* FROM direct_events WHERE chat_id=? AND message_id=? AND kind='job_status'",(r['chat_id'],r['message_id'])):
    result(c,'direct:'+r['chat_id']+':'+str(r['message_id']),sids,r['offer_id'],json.loads(e['payload']),None,json.loads(r['jobs_json'] or '[]'))
 checked(c,'dimensions_direct',direct)
 # Resolve messages after links/mappings have been imported; old unambiguous matches
 # may become ambiguous when a second matching signal arrives, rather than silently close it.
 for m in c.execute('SELECT * FROM messages').fetchall():match_feedback(c,dict(m))
 c.commit()
def ingest_update(update,path=DB):
 m=update.get('message') or update.get('edited_message') or update.get('channel_post') or update.get('edited_channel_post');q=update.get('callback_query')
 with closing(connect(path)) as c,c:
  if m and str(m.get('chat',{}).get('id'))==SOURCE:
   ingest_signal(c,{'message_id':m['message_id'],'date_utc':datetime.fromtimestamp(m['date'],timezone.utc).isoformat(),'text':m.get('text') or m.get('caption') or ''})
  elif m and str(m.get('chat',{}).get('id')) in (REMOTE,GROUP,OWNER) and (str(m.get('chat',{}).get('id'))!=REMOTE or m.get('message_thread_id')==758):
   user=m.get('from',{})
   capture_message(c,{'chat_id':str(m['chat']['id']),'message_id':str(m['message_id']),'at':datetime.fromtimestamp(m['date'],timezone.utc).isoformat(),'actor_id':str(user.get('id','')),'text':m.get('text') or m.get('caption') or ('[voice]' if m.get('voice') else '[media]'),'reply_id':m.get('reply_to_message',{}).get('message_id'),'thread_id':m.get('message_thread_id'),'is_bot':user.get('is_bot',False)})
  if q and re.fullmatch(r'(?:msp2|mspdim2):[0-9a-f]{24}:[yn]',q.get('data','')):
   msg=q.get('message',{});chat=str(msg.get('chat',{}).get('id',''));actor=str(q.get('from',{}).get('id',''))
   if actor==OWNER and chat==REMOTE and msg.get('message_thread_id')==758:
    sids=[r[0] for r in c.execute('SELECT signal_id FROM links WHERE chat_id=? AND message_id=?',(chat,str(msg.get('message_id'))))]
    at=now();event(c,'callback:'+str(q['id']),'button_received',q,sids[0] if len(sids)==1 else None,at,actor,chat,msg.get('message_id'))
    feedback_record(c,'decision:'+('price:' if q['data'].startswith('msp2:') else 'dimensions:')+q['data'].split(':')[1],sids,'Да' if q['data'].endswith(':y') else 'Нет',at,actor,chat,msg.get('message_id'))
def record_action(c,sid,key,offer,market,cabinet,status,detail,evidence,at=None):
 if status not in ('updated','already_equal','failed','pending','unknown','simulation','declined'):raise ValueError('Explicit status required')
 if at:
  parsed=datetime.fromisoformat(at.replace('Z','+00:00'))
  if parsed.tzinfo is None:raise ValueError('Timestamp needs timezone')
 if not c.execute('SELECT 1 FROM signals WHERE id=?',(sid,)).fetchone():raise ValueError('Unknown signal')
 if status in ('updated','already_equal') and not evidence:raise ValueError('Confirmation evidence required')
 if not key or not detail or not offer or not market:raise ValueError('key, detail, offer and marketplace required')
 payload={'offer':offer,'marketplace':market,'cabinet':cabinet,'status':status,'detail':detail,'evidence':evidence}
 event(c,'manual_action:'+key+':'+digest(payload),'action_result_manual',payload,sid,at)
 c.execute('INSERT INTO actions(signal_id,source_key,job_id,offer_id,marketplace,cabinet,status,detail,occurred_at,observed_at,evidence_json) VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source_key,job_id,offer_id,marketplace,cabinet) DO UPDATE SET status=excluded.status,detail=excluded.detail,evidence_json=excluded.evidence_json,occurred_at=excluded.occurred_at,observed_at=excluded.observed_at',(sid,'manual:'+key,key,offer,market,cabinet or '',status,detail,at,now(),js(payload)))
def status(c):
 return {'db':c.execute('PRAGMA database_list').fetchone()[2],'signals':c.execute('SELECT count(*) FROM signals').fetchone()[0],'by_type':dict(c.execute('SELECT type,count(*) FROM signals GROUP BY type')),'feedback':dict(c.execute('SELECT match_state,count(*) FROM feedback GROUP BY match_state')),'actions':dict(c.execute('SELECT status,count(*) FROM actions GROUP BY status')),'unlinked_actions':c.execute('SELECT count(*) FROM actions WHERE signal_id IS NULL').fetchone()[0],'health':[dict(x) for x in c.execute('SELECT * FROM health')]}
def main():
 p=argparse.ArgumentParser();p.add_argument('--db',default=str(DB));p.add_argument('command',choices=['sync','watch','status','list','show','link','record-action']);p.add_argument('--id',type=int);p.add_argument('--chat');p.add_argument('--message');p.add_argument('--limit',type=int,default=30);p.add_argument('--offer');p.add_argument('--marketplace');p.add_argument('--cabinet');p.add_argument('--status',choices=['updated','already_equal','failed','pending','unknown','simulation','declined']);p.add_argument('--detail');p.add_argument('--evidence');p.add_argument('--at');p.add_argument('--key');a=p.parse_args()
 with closing(connect(a.db)) as c:
  if a.command=='watch':
   while True:sync(c);time.sleep(10)
  elif a.command=='sync':sync(c);print(js(status(c)))
  elif a.command=='record-action':
   record_action(c,a.id,a.key,a.offer,a.marketplace,a.cabinet,a.status,a.detail,a.evidence,a.at);c.commit();print('recorded')
  elif a.command=='status':print(js(status(c)))
  elif a.command=='list':print(js([dict(r) for r in c.execute('SELECT * FROM v_signal_registry ORDER BY received_at DESC LIMIT ?',(a.limit,))]))
  elif a.command=='show':
   print(js({t:[dict(r) for r in c.execute('SELECT * FROM '+t+' WHERE '+('id' if t=='signals' else 'signal_id')+'=?',(a.id,))] for t in ('signals','subjects','feedback','actions','events')}))
  elif a.command=='link':
   if not a.id or not a.chat or not a.message:p.error('link requires --id --chat --message')
   if not c.execute('SELECT 1 FROM signals WHERE id=?',(a.id,)).fetchone():p.error('signal not found')
   r=c.execute('SELECT * FROM feedback WHERE chat_id=? AND message_id=?',(a.chat,a.message)).fetchone()
   if not r:
    m=c.execute('SELECT * FROM messages WHERE chat_id=? AND message_id=?',(a.chat,a.message)).fetchone()
    if not m:p.error('message not found')
    c.execute("INSERT INTO feedback(chat_id,message_id,at,observed_at,actor_id,text,signal_id,match_state,candidates_json,method) VALUES(?,?,?,?,?,?,?,'manual',?,'manual_exact')",(a.chat,a.message,m['at'],now(),m['actor_id'],m['text'],a.id,js([a.id])))
    r=c.execute('SELECT * FROM feedback WHERE chat_id=? AND message_id=?',(a.chat,a.message)).fetchone()
   c.execute("UPDATE feedback SET signal_id=?,match_state='manual',method='manual_exact' WHERE chat_id=? AND message_id=?",(a.id,a.chat,a.message));event(c,'manual_link:'+str(r['id'])+':'+str(a.id),'manual_link',dict(r),a.id);add_link(c,a.chat,a.message,a.id,'manual_exact');c.commit();print('linked')
if __name__=='__main__':main()
