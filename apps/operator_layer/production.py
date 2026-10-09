"""Scoped production ingress and at-most-once outbox. No polling, shell or Codex launch."""
import json,os
from .tasks import Journal
from .multipart import Collector,scope_key
from .multipart_ingress import Ingress
from .queue import TaskQueue
from .worker_service import Outbox

def receive(config,message_id,update_id,text):
 j=Journal(config['root'])
 try:
  q=TaskQueue(j,allowed_scope=tuple(config['scope']));c=Collector(j)
  if text.strip().lower()=='/task status':
   return linked_status(j,c,q,tuple(config['scope']))
  r=Ingress(c).receive(tuple(config['scope']),str(message_id),update_id,text)
  if r.get('status')=='ASSEMBLED':
   q.enqueue_multipart(c);r=c.status(r['multipart_task_id'])
  return r
 finally:j.close()
def linked_status(j,c,q,scope):
 import subprocess
 opened=c._open(scope_key(scope))
 if opened:return c.status(opened['multipart_task_id'])
 rows=j.db.execute("SELECT body FROM multipart WHERE scope=? AND json_extract(body,'$.durable_task_id') IS NOT NULL ORDER BY json_extract(body,'$.created_at') DESC LIMIT 1",(scope_key(scope),)).fetchone()
 if not rows:return {'consumed':True,'reason':'no_collection'}
 m=json.loads(rows[0]);result=c.status(m['multipart_task_id']);tid=m.get('durable_task_id')
 if not tid:return result
 d=j.get(tid);ex=j.db.execute('SELECT request,state,started,reconciliation FROM task_executions WHERE task=? ORDER BY started DESC LIMIT 1',(tid,)).fetchone()
 o=j.db.execute('SELECT status,delivered,delivery_receipt FROM outbox WHERE task=?',(tid,)).fetchone()
 execution_count=j.db.execute('SELECT COUNT(*) FROM task_executions WHERE task=?',(tid,)).fetchone()[0]
 delivery_count=int(bool(o and o[1] and o[2]))
 try:active=subprocess.run(['systemctl','--user','is-active','hermes-durable-worker.service'],capture_output=True,text=True,timeout=2).stdout.strip()=='active'
 except (OSError,subprocess.TimeoutExpired):active=False
 return result|{'task_status':d['status'],'worker_active':active,'current_execution':ex[0] if ex else None,'execution_count':execution_count,'duplicate_execution':execution_count>1,'delivery_count':delivery_count,'execution_status':ex[1] if ex else None,'reconciliation':ex[3] if ex else None,'last_activity':d['updated_at'],'last_checkpoint':d.get('last_checkpoint'),'outbox_status':o[0] if o else 'NONE','final_result_ready':d['status']=='DONE'}
def reply_text(r):
 if 'task_status' in r:
  return '\n'.join(['Multipart: '+str(r['multipart_task_id']),'Durable Task: '+str(r['durable_task_id']),'Состояние: '+r['task_status'],'Worker: '+('active' if r['worker_active'] else 'inactive'),'Executions: '+str(r['execution_count']),'Execution: '+str(r['current_execution']),'Execution status: '+str(r['execution_status']),'Последняя активность: '+r['last_activity'],'Outbox: '+r['outbox_status'],'Delivery count: '+str(r['delivery_count']),'Duplicate execution: '+('YES' if r['duplicate_execution'] else 'NO'),'Результат готов: '+('YES' if r['final_result_ready'] else 'NO')])
 s=r.get('status')
 if s=='COLLECTING':return f"Части сохранены: {len(r.get('received_parts',[]))}/{r.get('expected_parts') or '?'}. Выполнение не запущено."
 if s=='DISPATCHED':return 'Все части собраны. Одна задача поставлена в независимую очередь.'
 if s=='CANCELLED':return 'Сборка отменена. Выполнение не запущено.'
 return 'Состояние сборки: '+str(s or r.get('reason','ERROR'))

def deliver_once(j,q,sender):
 # Historic report outbox has no admitted queue row: never deliver it accidentally.
 db=j.db;db.execute('BEGIN IMMEDIATE')
 try:
  row=db.execute("SELECT o.task,o.origin,o.body FROM outbox o JOIN task_queue q ON q.task=o.task WHERE o.status='PENDING' AND o.delivered=0 AND q.state='DONE' AND q.scope=? ORDER BY o.created_at LIMIT 1",(q._scope_json(),)).fetchone()
  if row:db.execute("UPDATE outbox SET status='DELIVERY_UNKNOWN' WHERE task=?",(row[0],))
  db.commit()
 except BaseException:db.rollback();raise
 if not row:return False
 tid,origin,raw=row
 try:
  result=json.loads(raw).get('result',{});evidence=result.get('evidence',{})
  answer=evidence.get('answer') or evidence.get('result') or 'Задача выполнена. Подтверждение: '+json.dumps(evidence,ensure_ascii=False)
  text='Результат задачи '+tid+'\n'+str(answer)
  if len(text)>3500:text=text[:3400]+'\nПолный результат сохранён в Task Journal.'
  receipt=sender(origin,text)
  if receipt is None:return True
  Outbox(j).ack(tid,receipt)
 except Exception:
  # Transport exception has unknown effects. NO resend and NO business retry.
  pass
 return True

def telegram_sender(origin,text):
 if not origin.startswith('telegram:'):raise ValueError('unsupported_origin')
 chat=origin.split(':',1)[1]
 if not chat.isdigit():raise ValueError('invalid_private_origin')
 from hermes_cli.config import load_env
 import httpx
 token=load_env().get('TELEGRAM_BOT_TOKEN') or os.environ.get('TELEGRAM_BOT_TOKEN')
 if not token:raise RuntimeError('telegram_delivery_not_configured')
 # Never log the URL/token or exception body.
 response=httpx.post('https://api.telegram.org/bot'+token+'/sendMessage',json={'chat_id':chat,'text':text,'disable_notification':False,'link_preview_options':{'is_disabled':True}},timeout=20)
 body=response.json()
 if body.get('ok') is not True:raise RuntimeError('telegram_delivery_not_acknowledged')
 msg=body['result']
 if str(msg['chat']['id'])!=chat:raise RuntimeError('delivery_origin_mismatch')
 return {'platform':'telegram','chat_id':chat,'message_id':str(msg['message_id'])}
