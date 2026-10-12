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
   # Resolve the staged checkout by this test file, never by the shell CWD.
   checkout=Path(__file__).resolve().parents[2]
   path=checkout/"deploy/hermes_plugins/durable_tasks/__init__.py"
   spec=importlib.util.spec_from_file_location("durable_plugin_test_natural",path)
   plugin=importlib.util.module_from_spec(spec)
   spec.loader.exec_module(plugin)
   # Production plugin intentionally uses a fixed live CODE_ROOT. Override
   # only in this unit-test module so an isolated pre-deploy staging run cannot
   # silently load the installed production checkout.
   plugin.CODE_ROOT=str(checkout)
   class Native:
    def __init__(self):self.handlers={}
    def add_handler(self,handler,group):self.handlers.setdefault(group,[]).append(handler)
    def remove_handler(self,handler,group):self.handlers[group].remove(handler)
   class Adapter:
    def _is_user_authorized_from_message(self,msg):return True
    def _should_process_message(self,msg,*,is_command):return True
   config={"root":str(Path(tmp)/"private"),"scope":("default","123","telegram:123","fixture"),"natural_multipart_enabled":True}
   native=Native()
   # Mimic an old v3 handler wired earlier into the same PTB group.
   async def old_ingress(update,context):return None
   old_ingress.__module__=plugin.__name__
   native.handlers[-96]=[TypeHandler(stub.Update,old_ingress)]
   self.assertIn("wire_status_v4",plugin.wire.__qualname__)
   from apps.operator_layer import queue as queue_module,production as production_module
   old_queue_class=queue_module.TaskQueue
   plugin.wire(native,Adapter(),config)
   from apps.operator_layer import multipart as multipart_module,multipart_ingress as ingress_module,tasks as tasks_module
   # A green test is meaningless if any dependency originated from the live
   # REMOTE operator checkout instead of the pinned test staging directory.
   for loaded in (queue_module,production_module,multipart_module,ingress_module,tasks_module):
    self.assertTrue(Path(loaded.__file__).resolve().is_relative_to(checkout),
                    f"stale_live_module_import:{loaded.__name__}")
   self.assertIs(production_module.TaskQueue,queue_module.TaskQueue)
   self.assertIsNot(production_module.TaskQueue,old_queue_class)
   self.assertEqual(len(native.handlers[-96]),1)
   self.assertNotEqual(native.handlers[-96][0].callback,old_ingress)
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
