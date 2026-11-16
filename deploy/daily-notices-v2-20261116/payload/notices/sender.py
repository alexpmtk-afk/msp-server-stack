"""Fixed established Remote Server topic; accepts only root-owned summary jobs."""
import hashlib,json,os,re,stat,sys,urllib.request,urllib.parse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import model
CHAT=-1002485321031
THREAD=758
OUTBOX=Path('/var/lib/msp-finance-notices/outbox')
def token():
 values={}
 for line in Path('/home/hermes/.hermes/.env').read_text().splitlines():
  key,sep,value=line.strip().removeprefix('export ').partition('=')
  if sep and key in ('MSP_ALERT_BOT_TOKEN','TELEGRAM_BOT_TOKEN'):
   value=value.strip()
   if len(value)>=2 and value[0]==value[-1] and value[0] in ('"',"'"):value=value[1:-1]
   values[key]=value
 out=values.get('MSP_ALERT_BOT_TOKEN') or values.get('TELEGRAM_BOT_TOKEN','')
 if not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+',out):raise ValueError('credential unavailable')
 return out
def trusted_path(path):
 for p in (path,*path.parents):
  st=p.lstat()
  if st.st_uid!=0 or st.st_mode&0o022 or stat.S_ISLNK(st.st_mode) or (p==path and (not stat.S_ISREG(st.st_mode) or st.st_nlink!=1)):raise ValueError('outbox trust')
def read_job(path):
 path=Path(path)
 if path.parent!=OUTBOX or not re.fullmatch(r'(daily|weekly)-20\d\d-\d\d-\d\d(?:-update-[0-9a-f]{24})?.json',path.name):raise ValueError('outbox scope')
 trusted_path(path);report=json.loads(path.read_bytes())
 update=report.get('update_id')
 if update and (report.get('kind')!='daily' or not re.fullmatch('[0-9a-f]{24}',update) or update!=model.signature(report)):raise ValueError('update identity')
 expected=report['kind']+'-'+report['day']+('-update-'+update if update else '')+'.json'
 if path.name!=expected:raise ValueError('summary identity')
 model.render(report)
 return report
def send(report,opener=None,bot_token=None):
 text=model.render(report);payload=dict(chat_id=str(CHAT),message_thread_id=str(THREAD),text=text,disable_web_page_preview='true',disable_notification='false',protect_content='false')
 req=urllib.request.Request('https://api.telegram.org/bot'+(bot_token or token())+'/sendMessage',data=urllib.parse.urlencode(payload).encode(),method='POST')
 try:
  with (opener or urllib.request.urlopen)(req,timeout=25) as r:answer=json.load(r)
 except Exception:raise RuntimeError('delivery uncertain; no blind replay') from None
 value=answer.get('result',{})
 if answer.get('ok') is not True or value.get('chat',{}).get('id')!=CHAT or value.get('message_thread_id')!=THREAD or value.get('text')!=text or type(value.get('message_id')) is not int:raise ValueError('delivery not acknowledged')
 return dict(status='SENT',chat_id=CHAT,thread_id=THREAD,message_id=value['message_id'],text_sha256=hashlib.sha256(text.encode()).hexdigest())
if __name__=='__main__':
 try:
  if os.geteuid()!=1001 or len(sys.argv)!=2:raise PermissionError('fixed Hermes sender only')
  if sys.argv[1]=='--check':token();print(json.dumps(dict(credentials_available=True,chat_id=CHAT,thread_id=THREAD)));raise SystemExit(0)
  print(json.dumps(send(read_job(sys.argv[1]))))
 except Exception as exc:print(json.dumps(dict(status='DELIVERY_UNCERTAIN',error_type=type(exc).__name__)));raise SystemExit(2)
