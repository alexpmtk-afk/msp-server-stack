import datetime,importlib.util,io,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
P=Path(os.environ.get('NOTICE_PAYLOAD',Path(__file__).parent/'payload'));sys.path.insert(0,str(P/'notices'))
import model,sender
spec=importlib.util.spec_from_file_location('notice_controller',P/'notices/controller.py');nc=importlib.util.module_from_spec(spec);spec.loader.exec_module(nc)
DAY='2026-11-15'
def cycles(state='VERIFIED',attempts=1):
 w={'key':'2026-11-16','jobs':[dict(cabinet=c,period='daily',status=state,attempts=attempts,**{'from':DAY,'to':DAY}) for c in model.WB]}
 o={'key':'2026-11-16','jobs':[dict(cabinet=c,day=DAY,status='VERIFIED',attempts=1) for c in model.OZ]}
 return w,o
class FormatTests(unittest.TestCase):
 def test_success_is_grouped_with_one_legal_entity_per_line(self):
  text=model.render(model.daily(*cycles(),{},{},DAY))
  self.assertIn('Загружены:\n\nWildberries\n• ИП Дмитриева\n• Лазер-мастер\n• ИП Новокшенов',text)
  self.assertIn('\n\nOzon\n• ИП Дмитриева\n• Лазер-мастер\n• ИП Новокшенов',text)
class LifecycleTests(unittest.TestCase):
 def test_first_empty_check_emits_waiting_then_no_attempt_two_spam(self):
  w,o=cycles();w['jobs'][2].update(status='WAITING_DATA',attempts=1,next_due=1794809400)
  first=model.daily(w,o,{},{},DAY);self.assertIsNotNone(first);self.assertIn('Следующая проверка',model.render(first))
  signature=model.signature(first);w['jobs'][2]['attempts']=2
  self.assertEqual(model.signature(model.daily(w,o,{},{},DAY)),signature)
 def test_third_failure_final_has_count_and_exact_check_time(self):
  w,o=cycles();w['jobs'][2].update(status='WAITING_NEXT_RUN',attempts=3,last_checked_at='2026-11-16T09:30:00+03:00')
  text=model.render(model.daily(w,o,{},{},DAY));self.assertIn('после 3 проверок',text);self.assertIn('09:30 МСК',text);self.assertIn('Проверки на сегодня завершены',text)
 def test_later_success_changes_signature(self):
  w,o=cycles();w['jobs'][2]['status']='WAITING_DATA';old=model.daily(w,o,{},{},DAY)
  w['jobs'][2]['status']='VERIFIED';new=model.daily(w,o,{},{},DAY);self.assertNotEqual(model.signature(old),model.signature(new))
 def test_weekly_covers_old_hold_without_claiming_daily_download(self):
  w,o=cycles();w['jobs'][2]['status']='HOLD';idx={model.WB[2]:{'reports':{'1':dict(period='weekly',report_type=1,**{'from':'2026-11-09','to':DAY})}}}
  report=model.daily(w,o,{},{},DAY,idx);self.assertTrue(all(r['status']=='VERIFIED' for r in report['items']));self.assertIn('дневной отдельно не докачивался',model.render(report))
 def test_inflight_first_check_is_not_final_summary(self):
  w,o=cycles();w['jobs'][2]['status']='IN_FLIGHT';self.assertIsNone(model.daily(w,o,{},{},DAY))
 def test_unknown_day_never_full_success(self):
  r=model.daily({'jobs':[]},{'jobs':[]},{},{},DAY);self.assertFalse(all(i['status']=='VERIFIED' for i in r['items']))
 def test_429_is_explicit_technical_stop_not_missing_report(self):
  w,o=cycles();w['jobs'][2].update(status='HOLD',http_status=429)
  text=model.render(model.daily(w,o,{},{},DAY));self.assertIn('лимит запросов (HTTP 429)',text);self.assertNotIn('после 3 проверок',text)
 def test_weekly_format_unchanged(self):
  w,o=cycles();w['jobs']=[dict(j,period='weekly',**{'from':'2026-11-09'}) for j in w['jobs']]
  report=model.weekly(w,{},DAY);self.assertEqual(model.render(report),model._legacy_render(report))
class ControllerTests(unittest.TestCase):
 def fixture(self,b,state='WAITING_DATA',attempts=1):
  w,o=cycles();w['jobs'][2].update(status=state,attempts=attempts)
  for prefix,cy in (('wb',w),('oz',o)):
   (b/prefix/'cycles').mkdir(parents=True);(b/prefix/'cycles/2026-11-16.json').write_text(json.dumps(cy))
  (b/'wb/jobs.json').write_text('{}');(b/'oz/catalog.json').write_text('{}')
  n=b/'notices';n.mkdir();(n/'outbox').mkdir();(n/'deliveries').mkdir()
  (n/'config.json').write_text(json.dumps(dict(first_run_date='2026-11-16',followup_from='2026-11-16')))
  return n,w,o
 def patched(self,b):
  from contextlib import ExitStack
  stack=ExitStack()
  for name,path in (('BASE',b/'notices'),('WB',b/'wb'),('OZ',b/'oz')):stack.enter_context(patch.object(nc,name,path))
  stack.enter_context(patch.object(nc,'read_raw',side_effect=lambda p,uid=0:Path(p).read_bytes()))
  stack.enter_context(patch.object(nc,'indices',return_value={}))
  stack.enter_context(patch.object(nc,'annotate_checks',side_effect=lambda v:v))
  def fake(cmd,**kw):
   report=json.loads(Path(cmd[-1]).read_text());text=model.render(report)
   return type('Done',(),{'stdout':json.dumps(dict(status='SENT',chat_id=-1002485321031,thread_id=758,message_id=10,text_sha256=__import__('hashlib').sha256(text.encode()).hexdigest()))})()
  stack.enter_context(patch.object(nc.subprocess,'run',side_effect=fake))
  return stack
 def test_initial_waiting_then_late_success_then_no_duplicate(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
   b=Path(t);n,w,o=self.fixture(b)
   with self.patched(b):
    nc.tick(datetime.datetime(2026,11,16,9,tzinfo=nc.TZ));self.assertEqual(len(list((n/'deliveries').glob('daily*'))),1)
    w['jobs'][2].update(status='VERIFIED',attempts=2);(b/'wb/cycles/2026-11-16.json').write_text(json.dumps(w))
    nc.tick(datetime.datetime(2026,11,16,9,20,tzinfo=nc.TZ));self.assertEqual(len(list((n/'deliveries').glob('daily*'))),2)
    nc.tick(datetime.datetime(2026,11,16,9,21,tzinfo=nc.TZ));self.assertEqual(len(list((n/'deliveries').glob('daily*'))),2)
 def test_attempt_two_silent_attempt_three_sends_final(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
   b=Path(t);n,w,o=self.fixture(b)
   with self.patched(b):
    now=datetime.datetime(2026,11,16,9,tzinfo=nc.TZ);nc.tick(now)
    w['jobs'][2]['attempts']=2;(b/'wb/cycles/2026-11-16.json').write_text(json.dumps(w));nc.tick(now);self.assertEqual(len(list((n/'deliveries').glob('daily*'))),1)
    w['jobs'][2].update(status='WAITING_NEXT_RUN',attempts=3);(b/'wb/cycles/2026-11-16.json').write_text(json.dumps(w));nc.tick(now);self.assertEqual(len(list((n/'deliveries').glob('daily*'))),2)
 def test_monday_final_daily_update_precedes_unchanged_weekly_notice(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
   b=Path(t);n,w,o=self.fixture(b)
   for c in model.WB:w['jobs'].append(dict(cabinet=c,period='weekly',status='VERIFIED',attempts=1,**{'from':'2026-11-09','to':DAY}))
   (b/'wb/cycles/2026-11-16.json').write_text(json.dumps(w))
   with self.patched(b):
    now=datetime.datetime(2026,11,16,9,tzinfo=nc.TZ);nc.tick(now)
    self.assertFalse((n/('deliveries/weekly-'+DAY+'.json')).exists())
    w['jobs'][2].update(status='VERIFIED',attempts=2);(b/'wb/cycles/2026-11-16.json').write_text(json.dumps(w))
    events=[];original=nc.deliver
    def observed(report):events.append((report['kind'],bool(report.get('update_id'))));return original(report)
    with patch.object(nc,'deliver',side_effect=observed):nc.tick(now)
    self.assertEqual(events,[('daily',True),('weekly',False)])
 def test_uncertain_initial_never_sends_followup(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
   b=Path(t);n,w,o=self.fixture(b,state='VERIFIED');(n/'deliveries/daily-2026-11-15.json').write_text('{"status":"DELIVERY_UNCERTAIN"}')
   with self.patched(b),patch.object(nc.subprocess,'run',side_effect=AssertionError('NO REPLAY')):nc.tick(datetime.datetime(2026,11,16,9,tzinfo=nc.TZ))
   self.assertEqual(len(list((n/'deliveries').glob('daily*'))),1)
 def test_sender_accepts_only_exact_update_identity(self):
  report=model.daily(*cycles(),{},{},DAY);report['update_id']=model.signature(report)
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
   out=Path(t);p=out/('daily-'+DAY+'-update-'+report['update_id']+'.json');p.write_text(json.dumps(report))
   with patch.object(sender,'OUTBOX',out),patch.object(sender,'trusted_path'):
    self.assertEqual(sender.read_job(p),report)
    p.write_text(json.dumps(dict(report,update_id='0'*24)))
    with self.assertRaises(ValueError):sender.read_job(p)
class SafetyTests(unittest.TestCase):
 def test_uncertain_update_blocks_all_further_followups(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
   b=Path(t);(b/'deliveries').mkdir();(b/'outbox').mkdir();r=model.daily(*cycles(),{},{},DAY)
   (b/('deliveries/daily-'+DAY+'.json')).write_text('{"status":"SENT","message_id":1}')
   (b/('deliveries/daily-'+DAY+'-update-'+('a'*24)+'.json')).write_text('{"status":"SENDING"}')
   with patch.object(nc,'BASE',b),patch.object(nc,'read_raw',side_effect=lambda p,uid=0:Path(p).read_bytes()),patch.object(nc,'deliver',side_effect=AssertionError('NO BLIND REPLAY')):
    self.assertEqual(nc.daily_update(r),(False,0))
 def test_actual_receipt_timestamp_is_used_not_next_due_or_now(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
   archive=Path(t);cid='a'*32;cab=model.WB[0];folder=archive/'wb-scheduled-capture'/cab/cid/('daily-'+DAY+'-'+DAY)/'attempt-03';folder.mkdir(parents=True)
   p=folder/'result.json';p.write_text(json.dumps(dict(cabinet=cab,date_from=DAY,date_to=DAY,status='WAITING_DATA')));epoch=1794810000;os.utime(p,(epoch,epoch))
   cy=dict(cycle_id=cid,jobs=[dict(cabinet=cab,period='daily',attempts=3,status='WAITING_NEXT_RUN',**{'from':DAY,'to':DAY})])
   with patch.object(nc,'ARCHIVE',archive),patch.object(nc,'read_raw',side_effect=lambda p,uid=0:Path(p).read_bytes()):out=nc.annotate_checks(cy)
   self.assertEqual(datetime.datetime.fromisoformat(out['jobs'][0]['last_checked_at']).timestamp(),epoch);self.assertNotIn('last_checked_at',cy['jobs'][0])
 def test_installer_nonroot_boundary_and_drift(self):
  spec=importlib.util.spec_from_file_location('upgrade',P/'upgrade.py');u=importlib.util.module_from_spec(spec);spec.loader.exec_module(u)
  with patch.object(u.os,'geteuid',return_value=1001),patch.object(u,'verify') as verify:
   with self.assertRaises(PermissionError):u.main()
   verify.assert_not_called()
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
   p=Path(t)/'drift';p.write_text('not expected')
   with patch.object(u,'trust'),self.assertRaises(ValueError):u.pins({'files':{str(p):'0'*64}})
if __name__=='__main__':unittest.main(verbosity=2)
