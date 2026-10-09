"""Ingress seam BEFORE debounce/commands/busy routing. Never dispatches Codex.
Requires authenticated immutable (profile, owner, chat, session) from transport.
Storage errors fail closed, including manual collection's ordinary messages.
"""
class Ingress:
 def __init__(self,collector):self.collector=collector
 def receive(self,scope,message_id,update_id,text,received_at=None):
  try:
   reply=self.collector.receive(scope,message_id,update_id,text,received_at=received_at)
   if reply.get('status')=='COMPLETE':reply=self.collector.assemble(reply['multipart_task_id'])
   return reply
  except (OSError,ValueError,RuntimeError) as exc:
   return {'consumed':True,'status':'ERROR','reason':'collector_unavailable'}
  except Exception:
   # Database failures must never fall through to ordinary agent execution.
   return {'consumed':True,'status':'ERROR','reason':'collector_unavailable'}
