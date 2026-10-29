"""Observe the existing Telegram receiver before scoped action handlers. Never send/stop."""
import asyncio, importlib.util, json, logging, os, hashlib
from pathlib import Path
ROOT=Path('/home/hermes/.local/share/msp/signal-registry')
log=logging.getLogger('msp_signal_registry')
def register(ctx):
 def wire_signal_registry_v4(application,adapter):
  from telegram import Update
  from telegram.ext import TypeHandler
  spec=importlib.util.spec_from_file_location('msp_signal_registry_live_v4',ROOT/'registry.py')
  ledger=importlib.util.module_from_spec(spec);spec.loader.exec_module(ledger)
  async def observe_signal_registry(update,context):
   try:
    await asyncio.to_thread(ledger.ingest_update,update.to_dict())
    (ROOT/'last_ingress.json').write_text(json.dumps({'pid':os.getpid(),'at':ledger.now(),'update_id':update.update_id}))
   except Exception:log.exception('Signal registry capture failed; existing action routing unchanged')
  for handler in list(application.handlers.get(-20000,[])):
   callback=getattr(handler,'callback',None);callback=getattr(callback,'__wrapped__',callback)
   if getattr(callback,'__name__','')=='observe_signal_registry':application.remove_handler(handler,group=-20000)
  application.add_handler(TypeHandler(Update,observe_signal_registry,block=True),group=-20000)
  (ROOT/'gateway_ready.json').write_text(json.dumps({'pid':os.getpid(),'at':ledger.now(),'revision':4,'handler_group':-20000,'observer_count':sum(getattr(getattr(getattr(h,'callback',None),'__wrapped__',getattr(h,'callback',None)),'__name__','')=='observe_signal_registry' for h in application.handlers.get(-20000,[])),'module_sha256':hashlib.sha256((ROOT/'registry.py').read_bytes()).hexdigest(),'sends_messages':False,'executes_actions':False}))
 ctx.register_platform_handler('telegram',wire_signal_registry_v4)
