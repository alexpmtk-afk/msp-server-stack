import csv,datetime,gzip,io,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
P=Path(os.environ.get('MP_TEST_PAYLOAD',Path(__file__).parent/'payload'));sys.path.insert(0,str(P))
import catalog as a,cleanup,plan,controller
CAB=plan.CABINETS[0]
class CleanupTests(unittest.TestCase):
 def fixture(self,t,weekly=True,weekly_typ=1,currency='RUB'):
  archive=Path(t);base=a.root(CAB,archive);(base/'documents').mkdir(parents=True);(base/'generations').mkdir();index=dict(cabinet=CAB,schema=1,baseline_seeded=True,reports={})
  for rid,period,typ,start,end,cur in [('1','daily',1,'2026-11-09','2026-11-09','RUB')]+([('2','weekly',weekly_typ,'2026-11-09','2026-11-15',currency)] if weekly else []):
   path=base/'documents'/(period+'-'+str(typ)+'-'+rid+'.csv');row=dict(reportId=int(rid),rrdId=1,reportType=typ,dateFrom=start,dateTo=end,currency=cur,retailAmount=10);out=io.StringIO(newline='');headers=list(row)+['_raw_json'];w=csv.DictWriter(out,fieldnames=headers,delimiter=';');w.writeheader();w.writerow(dict(row,_raw_json=json.dumps(row)));a.save(path,out.getvalue().encode('utf-8-sig'))
   r=dict(report_id=rid,report_type=typ,period=period,currency=cur,csv=str(path),sha256=a.filehash(path),rows=1,baseline=False,**{'from':start,'to':end});index['reports'][period+'|'+str(typ)+'|'+rid]=r
  a.store_index(index,archive);a.publish(index,archive);return archive,index,base/'documents/daily-1-1.csv'
 def test_equivalent_weekly_removes_working_file_preserves_exact_audit(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
   root,idx,daily=self.fixture(t);raw=daily.read_bytes();cleanup.prune(idx,root);self.assertFalse(daily.exists());mark=idx['reports']['daily|1|1']['cleanup'];self.assertEqual(gzip.decompress(Path(mark['archive']).read_bytes()),raw);self.assertTrue(Path(mark['tombstone']).exists());self.assertEqual(len(list(a.iter_view(a.snapshot(CAB,1,None,root)))),1)
 def test_repeat_cleanup_keeps_same_archive(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
   root,idx,daily=self.fixture(t);first=cleanup.prune(idx,root);self.assertEqual(cleanup.prune(idx,root),first)
 def test_no_weekly_keeps_daily(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
   root,idx,daily=self.fixture(t,False);cleanup.prune(idx,root);self.assertTrue(daily.exists())
 def test_other_type_does_not_remove_daily(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
   root,idx,daily=self.fixture(t,weekly_typ=2);cleanup.prune(idx,root);self.assertTrue(daily.exists())
 def test_other_currency_does_not_remove_daily(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
   root,idx,daily=self.fixture(t,currency='USD');cleanup.prune(idx,root);self.assertTrue(daily.exists())
 def test_corrupt_weekly_blocks_delete(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
   root,idx,daily=self.fixture(t);Path(idx['reports']['weekly|1|2']['csv']).write_text('corrupt')
   with self.assertRaises(ValueError):cleanup.prune(idx,root)
   self.assertTrue(daily.exists())
 def test_corrupt_daily_blocks_delete(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
   root,idx,daily=self.fixture(t);daily.write_text('corrupt')
   with self.assertRaises(ValueError):cleanup.prune(idx,root)
   self.assertTrue(daily.exists())
 def test_failed_audit_write_keeps_daily(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
   root,idx,daily=self.fixture(t)
   with patch.object(a,'save',side_effect=OSError('fixture crash')),self.assertRaises(OSError):cleanup.prune(idx,root)
   self.assertTrue(daily.exists())
 def test_crash_after_unlink_resumes_with_audit_without_duplicate(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
   root,idx,daily=self.fixture(t)
   with patch.object(a,'store_index',side_effect=OSError('fixture crash')),self.assertRaises(OSError):cleanup.prune(idx,root)
   cleanup.prune(a.load_index(CAB,root),root);self.assertFalse(daily.exists());self.assertEqual(len(list((root/'wb-daily-audit'/CAB).glob('*.gz'))),1)
class PlanTests(unittest.TestCase):
 def test_monday_daily_jobs_before_weekly(self):
  coverage={c:[dict(report_type=1,to='2026-11-08')] for c in plan.CABINETS};cyc=plan.make_cycle(datetime.datetime(2026,11,16,8,45,tzinfo=plan.TZ),{},coverage)
  kinds=[j['period'] for j in cyc['jobs']];self.assertEqual(kinds,sorted(kinds));self.assertEqual(sum(k=='weekly' for k in kinds),3)
 def test_weekly_waits_until_last_daily_retry_finishes(self):
  day=plan.make_job(CAB,'daily','2026-11-15','2026-11-15');day.update(status='WAITING_DATA',next_due=200);week=plan.make_job(CAB,'weekly','2026-11-09','2026-11-15');week['next_due']=0;cyc=dict(jobs=[week,day]);self.assertIsNone(plan.due_job(cyc,100));day['status']='WAITING_NEXT_RUN';self.assertIs(plan.due_job(cyc,100),week)
 def test_old_per_cabinet_notices_disabled_by_approved_config(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:
   base=Path(t);(base/'schedule.json').write_text('{"consolidated_notices":true}')
   with patch.object(controller,'BASE',base),patch.object(controller.r,'run',side_effect=AssertionError('NO DUPLICATE MESSAGE')):controller.notice({},dict(status='WAITING_NEXT_RUN'))
 def test_nonroot_upgrade_refuses_before_privileged_read(self):
  import summary_upgrade
  with self.assertRaises(PermissionError):summary_upgrade.main()
if __name__=='__main__':unittest.main()
