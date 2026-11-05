"""Real PTB objects, isolated DB/receipt folder, no bot token/network or Gateway dispatch."""
import asyncio, importlib.util,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
import importlib
class PluginIsolation(unittest.TestCase):
 def test_ptb_update_observer_rewire_and_no_sends(self):
  from telegram import Update
  spec=importlib.util.spec_from_file_location('registry_plugin_test',Path(__file__).with_name('__init__.py'));p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
  class App:
   def __init__(self):self.handlers={}
   def add_handler(self,h,group):self.handlers.setdefault(group,[]).append(h)
   def remove_handler(self,h,group):self.handlers[group].remove(h)
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as tmp:
   root=Path(tmp);p.ROOT=root
   source_text=Path(__file__).resolve().parents[1].joinpath('registry.py').read_text()
   needle="DB=Path('/opt/mcp/data/msp/msp_signal_registry.sqlite3')";self.assertEqual(source_text.count(needle),1)
   source=source_text.replace(needle,'DB=Path('+repr(str(root/'isolated.sqlite3'))+')')
   (root/'registry.py').write_text(source)
   ctx=SimpleNamespace(register_platform_handler=lambda name,f:setattr(ctx,'wire',f));p.register(ctx);app=App();ctx.wire(app,None);ctx.wire(app,None)
   self.assertEqual(len(app.handlers[-20000]),1)
   u=Update.de_json({'update_id':1,'channel_post':{'message_id':1,'date':1793250000,'chat':{'id':-1003375632914,'type':'channel','title':'fixture'},'text':'Расхождение размеров или веса\nTEST.0270'}},None)
   asyncio.run(app.handlers[-20000][0].callback(u,None))
   self.assertTrue((root/'last_ingress.json').exists())
   import sqlite3
   with sqlite3.connect(root/'isolated.sqlite3') as c:self.assertEqual(c.execute('select count(*) from signals').fetchone()[0],1)
   self.assertEqual(json.loads((root/'gateway_ready.json').read_text())['observer_count'],1)
if __name__=='__main__':unittest.main()
