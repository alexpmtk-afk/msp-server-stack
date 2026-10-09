"""Native PTB ingress. Exact private owner/chat scope; ordinary path untouched."""
import asyncio,json,logging,os,sys,time
from pathlib import Path
log=logging.getLogger('durable_tasks')
CODE_ROOT='/home/hermes/projects/hermes-operator-layer'
CONFIG=Path('/home/hermes/.hermes/operator-tasks/worker-config.json')
def wire_status_v3(native,adapter=None,config=None):
 if adapter is None:raise RuntimeError('telegram_adapter_required')
 if config is None:config=json.loads(CONFIG.read_text())
 sys.path.insert(0,CODE_ROOT)
 import importlib
 from apps.operator_layer import production
 importlib.reload(production)
 receive,reply_text=production.receive,production.reply_text
 from apps.operator_layer.tasks import Journal
 from telegram import Update
 from telegram.ext import TypeHandler,ApplicationHandlerStop
 scope=tuple(config['scope']);owner=scope[1];chat=scope[2].split(':',1)[1]
 async def ingress(update,context):
  msg=getattr(update,'message',None)
  if msg is None or not getattr(msg,'text',None):return
  if str(msg.chat.id)!=chat or msg.chat.type!='private' or str(getattr(msg.from_user,'id',''))!=owner:return
  if getattr(msg,'message_thread_id',None) is not None:return
  if not adapter._is_user_authorized_from_message(msg):return
  if not adapter._should_process_message(msg,is_command=msg.text.startswith('/')):return
  try:r=await asyncio.to_thread(receive,config,str(msg.message_id),update.update_id,msg.text)
  except Exception:
   # For exact authorized scope, storage errors must not execute partial input.
   from apps.operator_layer.multipart import HEADER
   if HEADER.fullmatch(msg.text.split('\n',1)[0]) or msg.text.startswith('/task'):
    await context.bot.send_message(chat_id=chat,text='Сборщик временно недоступен; выполнение не запущено.')
    raise ApplicationHandlerStop
   # Unknown manual collection state: fail closed, never silently bypass storage.
   raise ApplicationHandlerStop
  if not r.get('consumed'):return
  log.info('multipart ingress chat=%s message=%s status=%s',chat,msg.message_id,r.get('status') or r.get('reason'))
  await context.bot.send_message(chat_id=chat,text=reply_text(r))
  raise ApplicationHandlerStop
 for old in list(getattr(native,'handlers',{}).get(-96,[])):
  cb=getattr(old,'callback',None);cb=getattr(cb,'__wrapped__',cb)
  if getattr(cb,'__module__',None)==__name__:native.remove_handler(old,group=-96)
 native.add_handler(TypeHandler(Update,ingress),group=-96)
 j=Journal(config['root'])
 try:
  with j.db:
   j.db.execute('CREATE TABLE IF NOT EXISTS integration_metadata(key TEXT PRIMARY KEY,value TEXT)')
   for k,v in [('native_attached_pid',str(os.getpid())),('native_attached_at',str(time.time())),('scope',json.dumps(scope))]:j.db.execute('INSERT OR REPLACE INTO integration_metadata VALUES (?,?)',(k,v))
 finally:j.close()
 log.info('Multipart native ingress attached pid=%s private_chat=%s',os.getpid(),chat)
wire=wire_status_v3
def register(ctx):ctx.register_telegram_handler(wire_status_v3)
