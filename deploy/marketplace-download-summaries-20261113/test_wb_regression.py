import csv,datetime,fcntl,io,json,os,sys,tempfile,unittest,urllib.parse
from pathlib import Path
from unittest.mock import patch
P=Path(os.environ.get('WB_TEST_PAYLOAD',Path(__file__).parent/'payload'));sys.path.insert(0,str(P))
import catalog as a,plan,worker as w,controller as c,notify
TMP='/home/hermes/.hermes/cache/scratch'
CAB=plan.CABINETS[0]
def record(rid,period='daily',typ=1,start='2026-11-02',end=None,currency='RUB'):
 return dict(report_id=str(rid),report_type=typ,period=period,from_=start,to=end or start,currency=currency)
def report(rid,period='daily',typ=1,start='2026-11-02',end=None,currency='RUB'):
 r=record(rid,period,typ,start,end,currency);r['from']=r.pop('from_');return r
def scope(period='daily',bootstrap=False):
 return dict(cabinet=CAB,period=period,date_from='2026-11-02',date_to='2026-11-02' if period=='daily' else '2026-11-08',cycle_id='a'*32,nonce='b'*32,attempt=1,bootstrap=bootstrap)
def row(rid=9007199254740993,typ=1,start='2026-11-02',end=None):
 return dict(reportId=rid,rrdId=1,reportType=typ,dateFrom=start,dateTo=end or start,currency='RUB',sellerFinanceName='seller',retailAmount=11)
class WBTests(unittest.TestCase):
 def now(self,day=13):return datetime.datetime(2026,11,day,8,45,tzinfo=plan.TZ)
 def coverage(self):return {c:[report(1,'weekly',1,end='2026-11-01',start='2026-10-26'),report(2,'weekly',2,end='2026-11-01',start='2026-10-26')] for c in plan.CABINETS}
 def test_daily_backlog_includes_all_uncovered_days_and_cabinets(self):
  cycle=plan.make_cycle(self.now(),{},self.coverage());self.assertEqual(len(cycle['jobs']),33);self.assertEqual({j['from'] for j in cycle['jobs']},{'2026-11-%02d'%i for i in range(2,13)});self.assertTrue(all(j['max_attempts']==3 for j in cycle['jobs']))
 def test_monday_weekly_first_ten_checks(self):
  cycle=plan.make_cycle(self.now(16),{},self.coverage());self.assertEqual([j['period'] for j in cycle['jobs'][:3]],['daily']*3);self.assertTrue(all(j['max_attempts']==10 and j['from']=='2026-11-09' and j['to']=='2026-11-15' for j in cycle['jobs'] if j['period']=='weekly'))
 def test_weekly_not_checked_tuesday(self):self.assertTrue(all(j['period']=='daily' for j in plan.make_cycle(self.now(17),{},self.coverage())['jobs']))
 def test_initial_fresh_weekly_discovery_includes_new_year_tail(self):
  c=plan.make_cycle(self.now(),{},self.coverage(),True);self.assertEqual(len(c['jobs']),3);self.assertTrue(all(j['from']=='2025-12-29' and j['to']=='2026-11-12' for j in c['jobs']))
 def test_attempt_intervals_and_limits(self):
  for period,total in [('daily',3),('weekly',10)]:
   j=plan.make_job(CAB,period,'2026-11-02','2026-11-02');now=100
   for i in range(1,total+1):
    j['attempts']=i;plan.settle(j,dict(status='WAITING_DATA',cabinet=CAB,period=period,date_from=j['from'],date_to=j['to']),now);self.assertEqual(j['next_due'],now+1200);self.assertEqual(j['status'],'WAITING_NEXT_RUN' if i==total else 'WAITING_DATA');now+=1200
   self.assertIsNone(plan.due_job({'jobs':[j]},now+999999))
 def test_verified_and_hold_not_repeated(self):
  jobs=plan.make_cycle(self.now(),{},self.coverage())['jobs'];known={jobs[0]['key']:{'status':'VERIFIED'},jobs[1]['key']:{'status':'HOLD'}};new=plan.make_cycle(self.now(),known,self.coverage())['jobs'];self.assertNotIn(jobs[0]['key'],[j['key'] for j in new]);self.assertEqual(new[0]['status'],'HOLD')
 def test_ready_cabinet_does_not_block_others(self):
  c=plan.make_cycle(self.now(),{},self.coverage());c['jobs'][0]['status']='VERIFIED';self.assertEqual(plan.due_job(c,self.now().timestamp())['key'],c['jobs'][1]['key'])
 def test_mismatched_receipt_refused(self):
  with self.assertRaises(ValueError):plan.settle(plan.make_job(CAB,'daily','2026-11-02','2026-11-02'),dict(status='VERIFIED'),1)
 def active(self,reports):return a.active_reports({'reports':{str(i):r for i,r in enumerate(reports)}})
 def test_weekly_replaces_only_same_type_currency_dates(self):
  daily=[report(1),report(2,typ=2),report(3,currency='USD'),report(4,start='2026-11-09')];weekly=report(5,'weekly',start='2026-11-02',end='2026-11-08');active,old=self.active(daily+[weekly]);self.assertEqual([r['report_id'] for r in old],['1']);self.assertEqual(len(active),4)
 def test_month_split_waits_for_complete_coverage(self):
  d=report(1,start='2026-10-31',end='2026-11-01');first=report(2,'weekly',start='2026-10-26',end='2026-10-31')
  with self.assertRaises(ValueError):self.active([d,first])
  active,old=self.active([d,first,report(3,'weekly',start='2026-11-01')]);self.assertEqual(len(old),1)
 def test_new_year_tail_preserved(self):
  active,old=self.active([report(1,start='2026-01-01'),report(2,'weekly',start='2025-12-29',end='2026-01-04')]);self.assertEqual(active[0]['from'],'2025-12-29');self.assertEqual(len(old),1)
 def fixture(self,root,rid=9007199254740993,period='daily',typ=1):
  folder=root/'wb-current-catalog'/CAB;folder.mkdir(parents=True,exist_ok=True);(folder/'generations').mkdir(exist_ok=True)
  rr=row(rid,typ);path=folder/(str(rid)+'.csv');fields=list(rr)+['_raw_json']
  with path.open('w',encoding='utf-8-sig',newline='') as f:
   out=csv.DictWriter(f,fieldnames=fields,delimiter=';');out.writeheader();out.writerow(dict(rr,_raw_json=json.dumps(rr)))
  return dict(report(rid,period,typ),rows=1,csv=str(path),sha256=a.filehash(path),baseline=False)
 def test_atomic_idempotent_view_and_streaming_integrity(self):
  with tempfile.TemporaryDirectory(dir=TMP) as t:
   root=Path(t);r=self.fixture(root);index=dict(cabinet=CAB,reports={'one':r});pin=a.publish(index,root);self.assertFalse(a.publish(index,root)['changed']);snap=a.snapshot(CAB,1,2026,root);self.assertEqual(list(a.iter_view(snap))[0]['reportId'],'9007199254740993');self.assertEqual(pin['generation'],snap['generation']);Path(r['csv']).write_text('changed')
   with self.assertRaises(ValueError):list(a.iter_view(snap))
 def test_empty_year_is_unknown_not_zero(self):
  with tempfile.TemporaryDirectory(dir=TMP) as t:
   root=Path(t);r=self.fixture(root);a.publish(dict(cabinet=CAB,reports={'x':r}),root)
   with self.assertRaises(ValueError):a.snapshot(CAB,1,2027,root)
 def test_pointer_tamper_and_change_refused(self):
  with tempfile.TemporaryDirectory(dir=TMP) as t:
   root=Path(t);r=self.fixture(root);a.publish(dict(cabinet=CAB,reports={'x':r}),root);snap=a.snapshot(CAB,1,2026,root);Path(snap['pointer']).write_text('{}')
   with self.assertRaises(ValueError):list(a.iter_view(snap))
 def test_failed_publication_keeps_old_view(self):
  with tempfile.TemporaryDirectory(dir=TMP) as t:
   root=Path(t);r=self.fixture(root);index=dict(cabinet=CAB,reports={'x':r});a.publish(index,root);pin=(a.root(CAB,root)/'CURRENT.json').read_bytes();index['reports']['y']=dict(r,report_id='99');real=a.save
   def crash(path,raw,*args):
    if path.name=='CURRENT.json':raise OSError('injected')
    return real(path,raw,*args)
   with patch.object(a,'save',side_effect=crash),self.assertRaises(OSError):a.publish(index,root)
   self.assertEqual((a.root(CAB,root)/'CURRENT.json').read_bytes(),pin);self.assertTrue(Path(r['csv']).exists())
 def test_204_absence_not_error(self):self.assertEqual(w.Transport(scope(),Path('/unused')).parse(204,b''),(204,None))
 def test_nonabsence_http_and_malformed_json_hold(self):
  for status,body in [(429,b'[]'),(503,b'[]'),(204,b'[]'),(200,b'{}'),(200,b'[{"x":1,"x":2}]')]:
   with self.assertRaises(ValueError):w.Transport(scope(),Path('/unused')).parse(status,body)
 def test_big_ids_stay_integer(self):
  rid=9007199254740993123;v=w.strict(json.dumps([dict(row(rid))]).encode());self.assertEqual(v[0]['reportId'],rid)
  for bad in [float(rid),'123']:
   with self.assertRaises(ValueError):w.discover(scope(),lambda *args:(200,[dict(row(),reportId=bad)]))
 def test_unknown_http_entry_never_resends(self):
  with tempfile.TemporaryDirectory(dir=TMP) as t:
   state=Path(t);(state/'list-000.entry.json').write_text('{}');sender=w.Transport(scope(),state)
   with patch.object(w,'read_job'),patch.object(w,'load_credentials',side_effect=AssertionError('NO CREDENTIAL OR NETWORK')),self.assertRaises(ValueError):w.discover(scope(),sender)
 def test_retained_204_replays_without_credentials(self):
  with tempfile.TemporaryDirectory(dir=TMP) as t:
   state=Path(t);body=dict(dateFrom='2026-11-02',dateTo='2026-11-02',period='daily',limit=1000,offset=0);key='list-000'
   for suffix,value in [('.entry.json',a.doc(dict(cabinet=CAB,path=w.WB_LIST,body=body))),('.response',b''),('.meta.json',a.doc(dict(status=204,sha256=a.digest(b''),bytes=0,truncated=False)))]: (state/(key+suffix)).write_bytes(value)
   with patch.object(w,'read_job'),patch.object(w,'load_credentials',side_effect=AssertionError('NO SEND')):self.assertEqual(w.discover(scope(),w.Transport(scope(),state)),{})
 def test_known_source_reused_without_detail_request(self):
  with tempfile.TemporaryDirectory(dir=TMP) as t:
   root=Path(t);r=self.fixture(root);sender=w.Transport(scope(),root);index=dict(reports={'daily|1|'+r['report_id']:r})
   self.assertEqual(w.capture_report(scope(),sender,row(),index),r);self.assertEqual(len(sender.verified_files),1)
 def test_listed_without_detail_does_not_replace_daily(self):
  with tempfile.TemporaryDirectory(dir=TMP) as t:
   class Sender:
    allowed=set();state=Path(t)
    def __call__(self,*args):return (204,None)
   self.assertIsNone(w.capture_report(scope(),Sender(),row(),{'reports':{}}))
 def test_empty200_detail_is_not_terminal(self):
  class Sender:
   allowed=set()
   def __call__(self,*args):return (200,[])
  with self.assertRaises(ValueError):w.capture_report(scope(),Sender(),row(),{'reports':{}})
 def test_notice_target_scope_and_unknown_delivery(self):
  text=notify.message('daily',CAB,'2026-11-02','2026-11-02',3,'2');self.assertIn('Wildberries',text);self.assertIn('ИП Дмитриева',text);self.assertIn('выкупы WB',text)
  class Reply(io.BytesIO):pass
  def opener(req,timeout):
   data=urllib.parse.parse_qs(req.data.decode());self.assertEqual(data['chat_id'],['-1002485321031']);self.assertEqual(data['message_thread_id'],['758']);return Reply(json.dumps(dict(ok=True,result=dict(chat=dict(id=notify.CHAT),message_thread_id=758,message_id=123,text=text))).encode())
  self.assertEqual(notify.send('daily',CAB,'2026-11-02','2026-11-02',3,'2',opener=opener,bot_token='1:fake')['status'],'SENT')
  with self.assertRaises(RuntimeError):notify.send('daily',CAB,'2026-11-02','2026-11-02',3,'2',opener=lambda *args,**kwargs:(_ for _ in ()).throw(OSError()),bot_token='1:fake')
 def test_notice_uncertain_intent_not_replayed(self):
  with tempfile.TemporaryDirectory(dir=TMP) as t:
   root=Path(t);(root/'notices').mkdir();cycle=dict(key='fixture');j=plan.make_job(CAB,'daily','2026-11-02','2026-11-02');j.update(status='WAITING_NEXT_RUN',attempts=3);p=root/'notices'/('fixture-'+c.r.sha(j['key'].encode())[:20]+'.json');p.write_text('{"status":"SENDING"}')
   with patch.object(c,'BASE',root),patch.object(c,'mkdir'),patch.object(c.r,'run',side_effect=AssertionError('NO RETRY')):c.notice(cycle,j)
 def test_shared_slot_released_after_worker_step(self):
  with tempfile.TemporaryDirectory(dir=TMP) as t:
   root=Path(t);lock=root/'slot';lock.touch()
   def inside(*args):
    with lock.open('rb') as f:
     with self.assertRaises(BlockingIOError):fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
    return 42
   with patch.object(c,'FINANCE_LOCK',lock),patch.object(c,'context'),patch.object(c,'LEDGER',root),patch.object(c.r,'trust'),patch.object(c,'state',return_value={'ActiveState':'inactive'}),patch.object(c,'run_one_inner',side_effect=inside):self.assertEqual(c.run_one({},{}),42)
   with lock.open('rb') as f:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
 def test_foreign_worker_never_started_or_stopped(self):
  with tempfile.TemporaryDirectory(dir=TMP) as t:
   root=Path(t);lock=root/'slot';lock.touch()
   with patch.object(c,'FINANCE_LOCK',lock),patch.object(c,'context'),patch.object(c,'LEDGER',root),patch.object(c.r,'trust'),patch.object(c,'state',return_value={'ActiveState':'active'}),patch.object(c,'run_one_inner',side_effect=AssertionError('FOREIGN WORKER')),self.assertRaises(c.Paused):c.run_one({},{})
class IntegrationTests(WBTests):
 # Inherit fixtures, but only collect the new class's unique cases below by
 # using a separate explicit suite in the release verifier.
 def test_full_daily_capture_then_weekly_replacement_preserves_originals(self):
  with tempfile.TemporaryDirectory(dir=TMP) as t:
   root=Path(t);base=root/'wb-current-catalog';base.mkdir();folder=base/CAB;folder.mkdir();(folder/'generations').mkdir()
   index=dict(schema=1,cabinet=CAB,reports={},baseline_seeded=True)
   def seed(*args):return a.load_index(CAB,root) if (folder/'sources.json').exists() else index
   class Sender:
    def __init__(self,job,state):self.job=job;self.state=state;self.allowed=set();self.verified_files={}
    def __call__(self,key,path,body):
     if path==w.WB_LIST:
      return 200,[dict(row(9007199254740993+typ,typ,self.job['date_from'],self.job['date_to'])) for typ in (1,2)]
     rid=int(path[len(w.WB_DETAIL):]);typ=rid-9007199254740993
     if body['rrdId']:return 204,None
     value=[dict(row(rid,typ,self.job['date_from'],self.job['date_to']))];(self.state/(key+'.response')).write_bytes(a.doc(value));return 200,value
   for period in ('daily','weekly'):
    job=scope(period);state=root/period;state.mkdir()
    with patch.object(w,'ARCHIVE',root),patch.object(a,'seed_baseline',side_effect=seed),patch.object(w,'Transport',Sender):result=w.execute(job,state)
    self.assertEqual(result['status'],'VERIFIED');self.assertEqual([part['status'] for part in result['parts']],['VERIFIED']*2)
   active,old=a.active_reports(a.load_index(CAB,root));self.assertEqual(len(active),2);self.assertEqual(len(old),2);self.assertTrue(all(r['period']=='weekly' for r in active));self.assertTrue(all(Path(r['csv']).exists() for r in old))
   for typ in (1,2):self.assertEqual(len(list(a.iter_view(a.snapshot(CAB,typ,2026,root)))),1)
 def test_real_transport_durable_entry_precedes_sender_and_replay(self):
  with tempfile.TemporaryDirectory(dir=TMP) as t:
   root=Path(t);sender=w.Transport(scope(),root);sender.credential={'token':'fake'}
   class Gate:
    def __init__(self,*args):pass
    def reserve(self,*args):return []
   class Opener:
    def open(self,*args,**kwargs):
     if not (root/'list-000.entry.json').exists():raise AssertionError('entry must precede sender')
     class Reply(io.BytesIO):status=204
     return Reply(b'')
   with patch.object(w,'read_job'),patch.object(w.q,'SharedQuota',Gate),patch.object(w.urllib.request,'build_opener',return_value=Opener()):self.assertEqual(w.discover(scope(),sender),{})
   with patch.object(w,'read_job'),patch.object(w.urllib.request,'build_opener',side_effect=AssertionError('NO RETRY')):self.assertEqual(w.discover(scope(),w.Transport(scope(),root)),{})
 def test_unknown_sender_failure_keeps_intent_and_forbids_replay(self):
  with tempfile.TemporaryDirectory(dir=TMP) as t:
   root=Path(t);sender=w.Transport(scope(),root);sender.credential={'token':'fake'}
   class Gate:
    def __init__(self,*args):pass
    def reserve(self,*args):return []
   class Opener:
    def open(self,*args,**kwargs):raise TimeoutError('injected unknown')
   with patch.object(w,'read_job'),patch.object(w.q,'SharedQuota',Gate),patch.object(w.urllib.request,'build_opener',return_value=Opener()),self.assertRaises(TimeoutError):w.discover(scope(),sender)
   with patch.object(w,'read_job'),patch.object(w.urllib.request,'build_opener',side_effect=AssertionError('NO RETRY')),self.assertRaises(ValueError):w.discover(scope(),w.Transport(scope(),root))
 def test_quota_pause_does_not_create_sender(self):
  with tempfile.TemporaryDirectory(dir=TMP) as t:
   root=Path(t);sender=w.Transport(scope(),root);sender.credential={'token':'fake'}
   class Gate:
    def __init__(self,*args):pass
    def reserve(self,*args):raise w.q.QuotaBusy(20)
   with patch.object(w,'read_job'),patch.object(w.q,'SharedQuota',Gate),patch.object(w.urllib.request,'build_opener',side_effect=AssertionError('NO SEND')),self.assertRaises(w.Paused):w.discover(scope(),sender)
   self.assertFalse(list(root.glob('*.entry.json')))
 def test_restart_preserves_inflight_attempt(self):
  with tempfile.TemporaryDirectory(dir=TMP) as t:
   root=Path(t);(root/'cycles').mkdir();(root/'jobs.json').write_text('{}');job=plan.make_job(CAB,'daily','2026-11-02','2026-11-02');job.update(status='IN_FLIGHT',attempts=2);cycle=dict(key='fixture',cycle_id='a'*32,jobs=[job],through='2026-11-02',status='RUNNING')
   def replace(path,value,*args):path.write_bytes(a.doc(value))
   value=dict(status='VERIFIED',cabinet=CAB,period='daily',date_from=job['from'],date_to=job['to'])
   with patch.object(c,'BASE',root),patch.object(c,'STOP',False),patch.object(c,'replace',side_effect=replace),patch.object(c,'attach'),patch.object(c,'publish_cycle'),patch.object(c,'notice'),patch.object(c,'run_one',return_value=value):c.run_cycle(cycle)
   self.assertEqual(job['attempts'],2);self.assertEqual(cycle['status'],'VERIFIED')

class InstallTests(unittest.TestCase):
 def test_nonroot_refusal_before_production_reads(self):
  import start_root as install
  with patch.object(install.r,'verify_payload',side_effect=AssertionError('NO PRIVILEGED READ')):
   with self.assertRaises(PermissionError):install.main()
 def test_isolated_complete_install_transaction_and_lock_order(self):
  import start_root as install
  with tempfile.TemporaryDirectory(dir=TMP) as t:
   root=Path(t);base=root/'wb';obase=root/'ozon';obase.mkdir();(root/'units').mkdir();(root/'results').mkdir();archive=root/'archive';archive.mkdir();payload=root/'payload';payload.mkdir();(payload/'ozon').mkdir()
   for name in ('catalog.py','local_reports.py','guide.py'):(payload/name).write_bytes((P/name).read_bytes())
   (payload/'baseline_reader.py').write_text('old reader');(payload/'baseline_guide.py').write_text('old guide')
   reader=root/'reader.py';reader.write_bytes((P/'local_reports.py').read_bytes());guide=root/'guide.py';guide.write_bytes((P/'guide.py').read_bytes());ounit=root/'units/ozon.service';ounit.write_text('old Ozon unit');opublic=root/'results/ozon.json';opublic.write_text('{"root_release":"old","time_moscow":"08:40"}')
   for name in ('schedule.json','installation.json'):(obase/name).write_text('{"root_release":"old","time":"08:40"}')
   (obase/'installed-wiring.json').write_text('{"unit_sha256":"old"}');lock=root/'finance.lock';lock.touch();unit=root/'units/wb.service';timer=root/'units/wb.timer';public=root/'results/wb.json';target=root/'effective.py'
   baseline=dict(reader=str(reader),reader_sha256=c.r.sha(reader.read_bytes()),guide=str(guide),guide_sha256=c.r.sha(guide.read_bytes()),wiring={str(ounit):c.r.sha(ounit.read_bytes())});started=[]
   def mkdir(path,uid=0):path.mkdir()
   def save(path,raw,mode=0o600,gid=0):
    with path.open('xb') as f:f.write(raw)
    path.chmod(mode)
   def run(args,**kwargs):
    if args[:3]==['/usr/bin/systemctl','start','--no-block']:
     with lock.open('rb') as f:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
     started.append(args[-1]);return b''
    if 'show' in args and timer.name in args:return b'ActiveState=active\nUnitFileState=enabled\nNextElapseUSecRealtime=Sat 2026-11-14 05:45:00 UTC\n'
    if 'show' in args and install.TIMER in args:return b'ActiveState=active\nUnitFileState=enabled\nNextElapseUSecRealtime=Sat 2026-11-14 05:45:00 UTC\n'
    return b'ActiveState=active\n'
   import contextlib
   with patch.object(install,'preflight',return_value=(baseline,reader,unit,timer,b'new Ozon unit')),patch.object(install,'verify_ozon'),patch.object(install,'OBASE',obase),patch.object(install,'OUNIT',ounit),patch.object(install,'OPUBLIC',opublic),patch.object(install,'READER',target),patch.object(c,'BASE',base),patch.object(c,'ROOT',payload),patch.object(c,'PUBLIC',public),patch.object(c,'FINANCE_LOCK',lock),patch.object(c.r,'ARCHIVE',archive),patch.object(c,'mkdir',side_effect=mkdir),patch.object(c.r,'save',side_effect=save),patch.object(c.r,'trust'),patch.object(c.r,'run',side_effect=run),patch.object(c,'state',return_value=dict(ActiveState='inactive',PrivateNetwork='yes',DropInPaths='')),contextlib.redirect_stdout(io.StringIO()):install.main()
   self.assertEqual(started,[c.UNIT]);self.assertEqual(reader.read_bytes(),(P/'local_reports.py').read_bytes());self.assertEqual(target.read_bytes(),(P/'catalog.py').read_bytes());self.assertEqual((base/'backups/canonical-reader.py').read_text(),'old reader');self.assertEqual(json.loads((obase/'schedule.json').read_bytes())['time'],'08:40');self.assertEqual(json.loads((base/'schedule.json').read_bytes())['time'],'08:45');self.assertTrue((obase/'controller.lock').exists());self.assertEqual(ounit.read_bytes(),b'new Ozon unit');self.assertEqual(json.loads(public.read_bytes())['status'],'INSTALLED_INITIAL_BACKFILL_PENDING')
 def test_real_canonical_owner1001_read_only_preflight(self):
  import start_root as install
  install.legacy_files(json.loads((P/'baseline.json').read_bytes()))
 def test_legacy_hash_drift_stops_before_root_mutation(self):
  import start_root as install
  baseline=json.loads((P/'baseline.json').read_bytes());baseline['reader_sha256']='0'*64
  with self.assertRaises(ValueError):install.legacy_files(baseline)
 def test_legacy_symlink_is_not_trusted(self):
  import start_root as install
  with tempfile.TemporaryDirectory(dir=TMP) as t:
   root=Path(t);file=root/'file';file.write_bytes(b'pinned');link=root/'link';link.symlink_to(file);baseline=dict(reader=str(link),guide=str(file),reader_sha256=c.r.sha(b'pinned'),guide_sha256=c.r.sha(b'pinned'))
   with self.assertRaises(ValueError):install.legacy_files(baseline)
 def test_group_writable_legacy_file_is_not_trusted(self):
  import start_root as install
  with tempfile.TemporaryDirectory(dir=TMP) as t:
   file=Path(t)/'file';file.write_bytes(b'pinned');file.chmod(0o664);baseline=dict(reader=str(file),guide=str(file),reader_sha256=c.r.sha(b'pinned'),guide_sha256=c.r.sha(b'pinned'))
   with self.assertRaises(ValueError):install.legacy_files(baseline)
 def test_preflight_failure_has_no_install_side_effect(self):
  import start_root as install
  with patch.object(install,'preflight',side_effect=ValueError('drift')),patch.object(c.r,'save',side_effect=AssertionError('NO WRITE')),self.assertRaises(ValueError):install.main()

# Avoid repeating inherited tests while retaining readable fixture reuse.
for _name in list(WBTests.__dict__):
 if _name.startswith('test_') and _name not in IntegrationTests.__dict__:setattr(IntegrationTests,_name,None)
if __name__=='__main__':unittest.main()
