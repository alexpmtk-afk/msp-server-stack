import json,socket,sys,tempfile,threading,types,unittest,uuid
from pathlib import Path
from unittest.mock import patch
from apps.operator_layer.devexec_readonly import DevexecReadonly,validate_args
from apps.operator_layer.hermes_executor import HermesExecutor
from apps.operator_layer.tasks import Journal

def ctx(mutations=None):return {'task_id':str(uuid.uuid4()),'current_block':0,'block':{'allowed_mutations':[] if mutations is None else mutations}}
class BridgeTests(unittest.TestCase):
 def test_denies_mutations_and_escape(self):
  for op in ('dev.write_file','dev.apply_patch','dev.run_tests','dev.git_add','dev.git_commit'):
   with self.assertRaises(ValueError):validate_args(op,{})
  for p in ('../secret','/opt/mcp/secrets/key','.git/config','a/../b','key.pem'):
   with self.assertRaises(ValueError):validate_args('dev.read_file',{'path':p})
  with self.assertRaises(ValueError):DevexecReadonly(ctx(['dev.write_file']))
 def test_disabled_default(self):
  with tempfile.TemporaryDirectory() as td:
   j=Journal(Path(td)/'private')
   try:self.assertFalse(HermesExecutor(j.root,profile='default').devexec_readonly_enabled)
   finally:j.close()
 def test_unix_contract(self):
  with tempfile.TemporaryDirectory() as td:
   path=str(Path(td)/'sock');ls=socket.socket(socket.AF_UNIX);ls.bind(path);ls.listen(1);received=[]
   def serve():
    with ls:
     c,_=ls.accept()
     with c:
      data=b''
      while not data.endswith(b'\n'):data+=c.recv(8192)
      received.append(json.loads(data));c.sendall(b'{"result":{"status":"PASS","relative_paths":[]}}\n')
   t=threading.Thread(target=serve,daemon=True);t.start();c=ctx()
   self.assertEqual(DevexecReadonly(c,socket_path=path).call('dev.list_files',{})['status'],'PASS')
   t.join(2);self.assertFalse(t.is_alive());self.assertEqual(received[0]['contract']['task_id'],c['task_id']);self.assertEqual(received[0]['contract']['workspace_id'],'operator')
 def test_registry_exact_ro_only(self):
  p=types.ModuleType('tools');p.__path__=[];m=types.ModuleType('tools.registry');registered={}
  class Registry:
   def register(self,**kwargs):registered[kwargs['name']]=kwargs
  m.registry=Registry()
  with patch.dict(sys.modules,{'tools':p,'tools.registry':m}):DevexecReadonly(ctx()).register()
  self.assertEqual(set(registered),{'devexec_list_files','devexec_read_file','devexec_git_status','devexec_git_diff'})
  self.assertTrue(all(v['toolset']=='operator-devexec-ro' for v in registered.values()))
