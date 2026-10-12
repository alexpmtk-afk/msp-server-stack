import asyncio,ast,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from apps.operator_layer.tasks import Journal
from apps.operator_layer.multipart import Collector
from apps.operator_layer.multipart_ingress import Ingress

class IngressTests(unittest.IsolatedAsyncioTestCase):
 async def test_explicit_has_priority_and_normal_keeps_live_debounce(self):
  with tempfile.TemporaryDirectory() as tmp:
   j=Journal(Path(tmp)/'private');self.addCleanup(j.close);collector=Collector(j);gate=Ingress(collector)
   # Execute the actual installed adapter's batching methods in an isolated harness.
   source=Path('/home/hermes/.hermes/hermes-agent/gateway/platforms/base.py').read_text()
   tree=ast.parse(source)
   method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_enqueue_text_event')
   ns={'asyncio':asyncio,'_append_text':lambda a,b:(a or '')+'\n'+b}
   exec(compile(ast.Module(body=[method],type_ignores=[]),'<live-debounce>','exec'),ns)
   class Adapter:
    _enqueue_text_event=ns['_enqueue_text_event']
    def __init__(self):self._pending_text_batches={};self._pending_text_batch_tasks={};self.dispatched=[]
    def _drop_unresolved(self,e):return False
    def _text_batch_key(self,e):return 'fixture'
    async def _flush_text_batch(self,key):
     await asyncio.sleep(.01);self.dispatched.append(self._pending_text_batches.pop(key).text)
   a=Adapter();scope=('default','owner','chat','session')
   async def inbound(text,n):
    result=gate.receive(scope,str(n),n,text)
    if not result['consumed']:
     e=SimpleNamespace(text=text,media_urls=[],absorb_reply_expected=lambda other:None)
     a._enqueue_text_event(e)
    return result
   for n,text in enumerate(['TASK 1/3\nALPHA','TASK 2/3\nBRAVO','TASK 3/3 END\nCHARLIE'],1):await inbound(text,n)
   self.assertEqual(a.dispatched,[])
   self.assertEqual(len(collector.pending()),1)
   tid=collector.pending()[0]['durable_task_id']
   self.assertEqual(collector.input_for(tid),'ALPHA\n\nBRAVO\n\nCHARLIE')
   req=collector.prepare_dispatch(collector.pending()[0]['multipart_task_id'])
   collector.confirm_dispatch(req['multipart_task_id'],{'request_id':req['request_id'],'task_id':tid,'accepted':True})
   await inbound('hello',4);await inbound('world',5)
   await asyncio.gather(*a._pending_text_batch_tasks.values())
   self.assertEqual(a.dispatched,['hello\nworld'])
 async def test_storage_failure_is_closed_not_plaintext_fallback(self):
  class Broken:
   def receive(self,*a,**k):raise OSError('fixture disk failure')
  result=Ingress(Broken()).receive(('default','owner','chat','session'),'1',1,'TASK 1/2\nA')
  self.assertTrue(result['consumed']);self.assertEqual(result['reason'],'collector_unavailable')
