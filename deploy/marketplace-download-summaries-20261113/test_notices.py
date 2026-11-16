import datetime,importlib.util,io,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
P=Path(os.environ.get('MP_TEST_PAYLOAD',Path(__file__).parent/'payload'));sys.path.insert(0,str(P/'notices'))
import model,sender
s=importlib.util.spec_from_file_location('notices_controller',P/'notices/controller.py');nc=importlib.util.module_from_spec(s);s.loader.exec_module(nc)
DAY='2026-11-15'
def cyc(cabs,kind='daily',state='VERIFIED'):
 jobs=[]
 for cab in cabs:
  j=dict(cabinet=cab,status=state,attempts=3 if kind=='daily' else 10)
  if cab.startswith('ozon'):j['day']=DAY
  else:j.update(period=kind,**{'from':'2026-11-09' if kind=='weekly' else DAY,'to':DAY})
  jobs.append(j)
 return dict(key='2026-11-16',jobs=jobs,manual=False,bootstrap=False)
def report():return model.daily(cyc(model.WB),cyc(model.OZ),{},{},DAY)
class ModelTests(unittest.TestCase):
 def test_daily_all_six_success(self):self.assertIn('Все отчёты загружены',model.render(report()))
 def test_one_missing_names_market_cabinet_date(self):
  w=cyc(model.WB);w['jobs'][2]['status']='WAITING_NEXT_RUN';r=model.daily(w,cyc(model.OZ),{},{},DAY);text=model.render(r)
  for word in ['Wildberries','Новокшенов',DAY,'3 проверок']:self.assertIn(word,text)
 def test_ozon_failure_is_in_same_daily_message(self):
  oz=cyc(model.OZ);oz['jobs'][0]['status']='WAITING_NEXT_DAY';self.assertIn('Ozon — ИП Дмитриева',model.render(model.daily(cyc(model.WB),oz,{},{},DAY)))
 def test_availability_wait_is_not_terminal(self):self.assertIsNone(model.daily(cyc(model.WB,state='WAITING_DATA'),cyc(model.OZ),{},{},DAY))
 def test_technical_pause_is_not_success(self):self.assertIsNone(model.daily(cyc(model.WB,state='IN_FLIGHT'),cyc(model.OZ),{},{},DAY))
 def test_missing_cycle_is_unknown_not_empty_success(self):self.assertIsNone(model.daily(None,cyc(model.OZ),{},{},DAY))
 def test_hold_reason_is_not_false_missing_or_ten_checks(self):
  text=model.render(model.daily(cyc(model.WB,state='HOLD'),cyc(model.OZ),{},{},DAY));self.assertIn('техническая неопределённость',text);self.assertNotIn('10 проверок',text)
 def test_unplanned_yesterday_is_not_assumed_success(self):
  r=model.daily(dict(jobs=[]),dict(jobs=[]),{},{},DAY);self.assertTrue(all(j['status']=='UNCONFIRMED' for j in r['items']))
 def test_known_ready_is_reused(self):
  wk={'|'.join((c,'daily',DAY,DAY)):dict(status='VERIFIED') for c in model.WB};ok={c+'|'+DAY:dict(status='VERIFIED') for c in model.OZ}
  self.assertTrue(all(r['status']=='VERIFIED' for r in model.daily(dict(jobs=[]),dict(jobs=[]),wk,ok,DAY)['items']))
 def test_weekly_success_three_cabinets(self):self.assertIn('Недельные отчёты',model.render(model.weekly(cyc(model.WB,'weekly'),{},DAY)))
 def test_weekly_absence_after_ten_checks(self):self.assertIn('10 проверок',model.render(model.weekly(cyc(model.WB,'weekly','WAITING_NEXT_RUN'),{},DAY)))
 def test_duplicate_scope_rejected(self):
  r=report();r['items'].append(r['items'][0])
  with self.assertRaises(ValueError):model.render(r)
 def test_foreign_cabinet_rejected(self):
  r=report();r['items'][0]['cabinet']='foreign'
  with self.assertRaises(ValueError):model.render(r)
 def test_incomplete_daily_cabinet_set_rejected(self):
  r=report();r['items'].pop()
  with self.assertRaises(ValueError):model.render(r)
 def test_successful_old_tails_omitted_but_missing_tails_reported(self):
  w=cyc(model.WB);tail=dict(w['jobs'][0]);tail.update(status='WAITING_NEXT_RUN',**{'from':'2026-11-14','to':'2026-11-14'});w['jobs'].append(tail)
  self.assertIn('2026-11-14',model.render(model.daily(w,cyc(model.OZ),{},{},DAY)))
class DeliveryTests(unittest.TestCase):
 def test_strict_ack_and_fixed_destination(self):
  r=report();text=model.render(r)
  class Reply(io.BytesIO):pass
  reply=Reply(json.dumps(dict(ok=True,result=dict(chat=dict(id=sender.CHAT),message_thread_id=sender.THREAD,message_id=10,text=text))).encode())
  out=sender.send(r,opener=lambda req,**kw:reply,bot_token='fake');self.assertEqual(out['status'],'SENT');self.assertEqual(out['thread_id'],758)
 def test_mismatched_ack_refused(self):
  reply=io.BytesIO(b'{"ok":false}')
  with self.assertRaises(ValueError):sender.send(report(),opener=lambda *a,**kw:reply,bot_token='fake')
 def test_transport_error_is_uncertain(self):
  def fail(*a,**kw):raise TimeoutError()
  with self.assertRaises(RuntimeError):sender.send(report(),opener=fail,bot_token='fake')
 def test_durable_claim_before_sender_and_no_uncertain_replay(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as tmp:
   base=Path(tmp);(base/'deliveries').mkdir();(base/'outbox').mkdir()
   def run(*args,**kw):
    self.assertEqual(json.loads(next((base/'deliveries').glob('*.json')).read_text())['status'],'SENDING');raise TimeoutError()
   with patch.object(nc,'BASE',base),patch.object(nc.subprocess,'run',side_effect=run) as call,patch.object(nc,'read',side_effect=lambda p,*a:json.loads(Path(p).read_text())):
    self.assertEqual(nc.deliver(report())['status'],'DELIVERY_UNCERTAIN');self.assertEqual(nc.deliver(report())['status'],'DELIVERY_UNCERTAIN');self.assertEqual(call.call_count,1)
class OrderingTests(unittest.TestCase):
 def run_tick(self,tmp,daily_ack='SENT',weekly_ack='SENT'):
  base=Path(tmp);(base/'deliveries').mkdir();(base/'outbox').mkdir();(base/'config.json').write_text('{"first_run_date":"2026-11-16"}');calls=[]
  def read(p,*args):
   p=Path(p)
   return json.loads(p.read_text()) if p.is_relative_to(base) and p.exists() else {}
  def cycle(base,key):
   if base==nc.WB:
    v=cyc(model.WB);v['jobs']+=cyc(model.WB,'weekly')['jobs'];return v
   return cyc(model.OZ)
  def deliver(r):
   calls.append(r['kind']);return dict(status=daily_ack if r['kind']=='daily' else weekly_ack)
  with patch.object(nc,'BASE',base),patch.object(nc,'read',side_effect=read),patch.object(nc,'cycle',side_effect=cycle),patch.object(nc,'indices',return_value={}),patch.object(nc,'deliver',side_effect=deliver):result=nc.tick(datetime.datetime(2026,11,16,12,tzinfo=nc.TZ))
  return calls,result
 def test_monday_daily_then_weekly(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:calls,r=self.run_tick(t);self.assertEqual(calls,['daily','weekly']);self.assertEqual(r['status'],'IDLE')
 def test_uncertain_daily_blocks_weekly_not_loading(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:calls,r=self.run_tick(t,'DELIVERY_UNCERTAIN');self.assertEqual(calls,['daily']);self.assertEqual(r['queue_size'],2)
 def test_uncertain_weekly_is_not_idle(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:calls,r=self.run_tick(t,weekly_ack='DELIVERY_UNCERTAIN');self.assertEqual(r['queue_size'],1)
if __name__=='__main__':unittest.main()
