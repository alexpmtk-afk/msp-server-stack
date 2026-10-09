import tempfile,unittest,time
from pathlib import Path
from apps.operator_layer.tasks import Journal
from apps.operator_layer.production import receive,deliver_once
from apps.operator_layer.worker_service import Outbox
from test_queue import SCOPE,PLAN
class ProductionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)/'private';self.config={'root':str(self.root),'scope':SCOPE}
 def test_ordinary_begin_cancel_incomplete_no_execution(self):
  self.assertFalse(receive(self.config,'plain',None,'обычный вопрос')['consumed'])
  a=receive(self.config,'begin',None,'/task begin');self.assertEqual(a['status'],'COLLECTING')
  self.assertEqual(receive(self.config,'cancel',None,'/task cancel')['status'],'CANCELLED')
  self.assertEqual(receive(self.config,'one',None,'TASK 1/3\nsmoke incomplete')['status'],'COLLECTING')
  j=Journal(self.root);self.addCleanup(j.close)
  self.assertEqual(j.db.execute('select count(*) from task_queue').fetchone()[0],0)
  self.assertEqual(j.db.execute('select count(*) from task_executions').fetchone()[0],0)
 def test_old_outbox_excluded_and_unknown_not_resent(self):
  j=Journal(self.root);self.addCleanup(j.close)
  from apps.operator_layer.queue import TaskQueue
  q=TaskQueue(j,allowed_scope=SCOPE)
  old=j.create(SCOPE[2],'old',PLAN);j.db.execute('insert into outbox(task,origin,body) values (?,?,?)',(old,SCOPE[2],'{}'));j.db.commit()
  self.assertFalse(deliver_once(j,q,lambda *a:None))
  tid=j.create(SCOPE[2],'new',PLAN);q.submit(dict(task_id=tid,request_id='new',profile=SCOPE[0],owner=SCOPE[1],origin_chat=SCOPE[2],session_key=SCOPE[3],origin_platform='telegram'))
  with j.db:q._transition(tid,'DONE');j.db.execute('insert into outbox(task,origin,body) values (?,?,?)',(tid,SCOPE[2],'{}'))
  calls=[]
  def unknown(*args):calls.append(args);raise OSError('unknown delivery')
  self.assertTrue(deliver_once(j,q,unknown));self.assertFalse(deliver_once(j,q,unknown));self.assertEqual(len(calls),1)
  self.assertEqual(q.status(tid)['state'],'DONE');self.assertEqual(j.db.execute('select status from outbox where task=?',(tid,)).fetchone()[0],'DELIVERY_UNKNOWN')
 def test_telegram_cutover_delivers_only_new_done_task(self):
  j=Journal(self.root);self.addCleanup(j.close)
  from apps.operator_layer.queue import TaskQueue
  q=TaskQueue(j,allowed_scope=SCOPE)
  def admitted(name,created_at):
   tid=j.create(SCOPE[2],name,PLAN)
   q.submit(dict(task_id=tid,request_id=name,profile=SCOPE[0],owner=SCOPE[1],origin_chat=SCOPE[2],session_key=SCOPE[3],origin_platform='telegram'))
   with j.db:
    q._transition(tid,'DONE')
    j.db.execute('insert into outbox(task,origin,body) values (?,?,?)',(tid,SCOPE[2],'{}'))
    j.db.execute('update outbox set created_at=? where task=?',(created_at,tid))
   return tid
  old=admitted('old_done',100)
  calls=[]
  def sender(origin,text):
   calls.append((origin,text))
   return {'platform':'telegram','chat_id':SCOPE[2],'message_id':'cutover-test'}
  self.assertFalse(deliver_once(j,q,sender,min_created_at=200))
  self.assertEqual(len(calls),0)
  new=admitted('new_done',300)
  self.assertTrue(deliver_once(j,q,sender,min_created_at=200))
  self.assertEqual(len(calls),1)
  states=dict(j.db.execute('select task,status from outbox').fetchall())
  self.assertEqual(states[old],'PENDING')
  self.assertEqual(states[new],'DELIVERED')
  self.assertFalse(deliver_once(j,q,sender,min_created_at=200))
  with self.assertRaises(ValueError):deliver_once(j,q,sender,min_created_at=-1)
class NativeTests(unittest.IsolatedAsyncioTestCase):
 async def test_exact_auth_ordinary_passthrough_and_predebounce_consume(self):
  import importlib.util,sys
  from types import SimpleNamespace as N
  from unittest.mock import AsyncMock
  path=Path('deploy/hermes_plugins/durable_tasks/__init__.py');spec=importlib.util.spec_from_file_location('durable_test_plugin',path);plugin=importlib.util.module_from_spec(spec);spec.loader.exec_module(plugin)
  with tempfile.TemporaryDirectory() as tmp:
   class Native:
    handlers={}
    def add_handler(self,h,group):self.handlers[group]=[h]
   native=Native();adapter=N(_is_user_authorized_from_message=lambda m:True,_should_process_message=lambda *a,**k:True)
   config={'root':str(Path(tmp)/'private'),'scope':('default','123','telegram:123','agent:main:telegram:dm:123')}
   plugin.wire(native,adapter,config);cb=native.handlers[-96][0].callback;bot=N(send_message=AsyncMock());context=N(bot=bot)
   msg=N(text='обычный запрос',chat=N(id=123,type='private'),from_user=N(id=123),message_id=1,message_thread_id=None)
   await cb(N(message=msg,update_id=1),context);bot.send_message.assert_not_awaited()
   msg.text='TASK 1/3\nfixture';msg.message_id=2
   from telegram.ext import ApplicationHandlerStop
   with self.assertRaises(ApplicationHandlerStop):await cb(N(message=msg,update_id=2),context)
   bot.send_message.assert_awaited_once()
   msg.from_user.id=999;bot.send_message.reset_mock();await cb(N(message=msg,update_id=3),context);bot.send_message.assert_not_awaited()
