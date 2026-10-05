"""Regression: production loader imports plugins under hermes_plugins.*."""
import importlib.util,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
PLUGIN=Path(__file__).resolve().parents[1]
class FactoryNamespaceTest(unittest.TestCase):
 def test_factory_works_without_top_level_package_on_path(self):
  name='hermes_plugins.channel_archive_regression'
  spec=importlib.util.spec_from_file_location(name,PLUGIN/'__init__.py',submodule_search_locations=[str(PLUGIN)])
  mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod)
  archive=sys.modules[name+'.archive']
  handlers=[]; table={}
  def add(handler,group): handlers.append((handler,group));table.setdefault(group,[]).append(handler)
  def remove(handler,group): table[group].remove(handler);handlers.remove((handler,group))
  native=SimpleNamespace(add_handler=add,remove_handler=remove,handlers=table)
  try:
   with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as folder, patch.object(archive,'home',return_value=Path(folder)),patch.dict(sys.modules,{'channel_archive':None}):
    mod._wire(native)
    with archive.connect() as c:
     self.assertIsNotNone(c.execute("SELECT value FROM metadata WHERE key='collector_attached_utc'").fetchone())
    self.assertEqual(len(handlers),1); self.assertEqual(handlers[0][1],-95)
    mod._wire(native); self.assertEqual(len(handlers),1, 'rewire must not duplicate native collector')
  finally:
   for k in list(sys.modules):
    if k==name or k.startswith(name+'.'):sys.modules.pop(k)
if __name__=='__main__':unittest.main()
