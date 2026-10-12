"""Tests real plugin handler registration against a stub Telegram runtime."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType,SimpleNamespace
from unittest.mock import AsyncMock,patch

class HotRewireTests(unittest.IsolatedAsyncioTestCase):
 async def test_native_handler_gets_fresh_natural_collector(self):
  stub=ModuleType("telegram")
  stub.Update=type("Update",(),{})
  ext=ModuleType("telegram.ext")
  class HandlerStop(Exception):pass
  class TypeHandler:
   def __init__(self,type_,callback):
    self.callback=callback
  ext.TypeHandler=TypeHandler
  ext.ApplicationHandlerStop=HandlerStop
  with tempfile.TemporaryDirectory() as tmp,patch.dict(sys.modules,{"telegram":stub,"telegram.ext":ext}):
   path=Path("deploy/hermes_plugins/durable_tasks/__init__.py")
   spec=importlib.util.spec_from_file_location("durable_plugin_test_natural",path)
   plugin=importlib.util.module_from_spec(spec)
   spec.loader.exec_module(plugin)
   class Native:
    def __init__(self):self.handlers={}
    def add_handler(self,handler,group):self.handlers.setdefault(group,[]).append(handler)
    def remove_handler(self,handler,group):self.handlers[group].remove(handler)
   class Adapter:
    def _is_user_authorized_from_message(self,msg):return True
    def _should_process_message(self,msg,*,is_command):return True
   config={"root":str(Path(tmp)/"private"),"scope":("default","123","telegram:123","fixture"),"natural_multipart_enabled":True}
   native=Native()
   plugin.wire(native,Adapter(),config)
   assert len(native.handlers[-96])==1
   callback=native.handlers[-96][0].callback
   bot=SimpleNamespace(send_message=AsyncMock())
   context=SimpleNamespace(bot=bot)
   def update(n,text):
    m=SimpleNamespace(text=text,chat=SimpleNamespace(id=123,type="private"),from_user=SimpleNamespace(id=123),message_id=n,message_thread_id=None)
    return SimpleNamespace(message=m,update_id=n)
   await callback(update(1,"Всё, приступай"),context)
   bot.send_message.assert_not_awaited()
   with self.assertRaises(HandlerStop):
    await callback(update(2,"Сейчас отправлю задание частями"),context)
   self.assertIn("0/?",bot.send_message.await_args.kwargs["text"])
   with self.assertRaises(HandlerStop):
    await callback(update(3,"Прочитай документ"),context)
   with self.assertRaises(HandlerStop):
    await callback(update(4,"Всё, приступай"),context)
   self.assertIn("независимую очередь",bot.send_message.await_args.kwargs["text"])
   plugin.wire(native,Adapter(),config)
   self.assertEqual(len(native.handlers[-96]),1)
   with self.assertRaises(HandlerStop):
    await native.handlers[-96][0].callback(update(4,"Всё, приступай"),context)
   self.assertEqual(native.handlers[-96][0].callback.__module__,plugin.__name__)

if __name__=="__main__":unittest.main()
