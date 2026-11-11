import csv,io,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
BASE=Path(__file__).parent
sys.path.insert(0,str(BASE/'payload'))
import history_worker as w
import history_root as h
import start_root
from apps.msp_marketplace_reports.generation_store import read_active

def no_net(event,args):
 if event in ('socket.connect','socket.bind','socket.getaddrinfo'):raise AssertionError('network forbidden')
sys.addaudithook(no_net)

class HistoryTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(dir=BASE);self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
 def plan(self,cab='ozon_dmitrieva',month=1):
  return {'cabinet':cab,'year':2026,'month':month,'path':'/v1/finance/realization/posting','max_send_entries':1}
 def response(self,month):
  return {'header':{'number':'FIXTURE','start_date':f'2026-{month:02d}-01','stop_date':f'2026-{month:02d}-{w.calendar.monthrange(2026,month)[1]}'},
          'rows':[{'row_number':2,'item':{'sku':'0012'},'seller_price_per_instance':1.25},
                  {'row_number':1,'item':{'sku':'0034'},'return_commission':{'amount':2}}]}
 def retain(self,state,plan,data):
  state.mkdir(parents=True)
  raw=w.doc(data)
  for n,b in [('entry.json',w.doc(plan)),('response.json',raw),('response.meta.json',w.doc({'status':200,'sha256':w.sha(raw)}))]:w.save(state/n,b)
 def test_all_thirty_month_scopes_offline_publication_values_and_replay(self):
  archive=self.root/'archive';archive.mkdir()
  for cab,month in h.JOBS:
   plan=self.plan(cab,month);state=self.root/'stage'/cab/str(month)
   self.retain(state,plan,self.response(month))
   with patch.object(w,'PLAN',plan),patch.object(w,'STATE',state),patch.object(w,'load_credentials',side_effect=AssertionError('refetch')):
    receipt=w.publish_verified(state,w.execute(state),root=archive)
    self.assertEqual(receipt['status'],'COMPLETE');self.assertEqual(receipt['rows'],2)
    generation=receipt['generation']
    second=w.publish_verified(state,w.execute(state),root=archive)
    self.assertEqual(second['generation'],generation)
  for cab in h.CABINETS:
   active=read_active(archive,'ozon_final_realization',cab,'2026')
   annual=w.business_rows(active['files']['annual.csv'])
   self.assertEqual(len(annual),20)
   self.assertEqual({k[1] for k in annual},{f'2026-{m:02d}' for m in range(1,11)})
   self.assertEqual(len([n for n in active['files'] if n.startswith('monthly/') and n.endswith('.csv')]),10)
 def test_period_mismatch_and_conflicting_publication_hold(self):
  state=self.root/'state';plan=self.plan(month=2);self.retain(state,plan,self.response(1))
  with patch.object(w,'PLAN',plan),self.assertRaises(ValueError):w.execute(state)
  state2=self.root/'valid';self.retain(state2,plan,self.response(2))
  archive=self.root/'archive';archive.mkdir()
  with patch.object(w,'PLAN',plan):
   receipt=w.publish_verified(state2,w.execute(state2),root=archive)
   raw=(state2/'report.csv').read_bytes();(state2/'report.csv').write_bytes(raw.replace(b'1.25',b'9.99'))
   with self.assertRaises(ValueError):w.publish_verified(state2,receipt,root=archive)
   self.assertEqual(read_active(archive,'ozon_final_realization',plan['cabinet'],'2026')['generation'],receipt['generation'])
 def test_quota_wait_does_not_consume_http_entry(self):
  state=self.root/'state';state.mkdir()
  cred=self.root/'creds';cred.mkdir();p=cred/'cabinets.json';p.write_text(json.dumps({'ozon_laser_master':{'client_id':'123','api_key':'fixture'}}));p.chmod(0o600)
  plan=self.plan('ozon_laser_master',3)
  with patch.object(w,'PLAN',plan),patch.dict(os.environ,{'CREDENTIALS_DIRECTORY':str(cred)}),patch.object(w.FinalQuota,'_approved_url',return_value='redis://fixture'),patch.object(w.FinalQuota,'reserve',side_effect=w.q.QuotaBusy(65)):
   with self.assertRaises(w.q.QuotaBusy):w.execute(state)
  self.assertFalse((state/'entry.json').exists());self.assertFalse((state/'dispatch.json').exists())
 def test_thirty_fixed_scopes_no_current_month(self):
  self.assertEqual(len(h.JOBS),30);self.assertEqual(len(set(h.JOBS)),30)
  self.assertTrue(all(1<=month<=10 for cab,month in h.JOBS))
 def test_job_rejects_wrong_scope_and_expiry(self):
  from types import SimpleNamespace
  path=self.root/'job.json'
  job={'cabinet':'ozon_dmitrieva','month':1,'year':2026,'nonce':'a'*32,'expires_epoch':w.time.time()+300}
  original=Path.lstat
  def st(p):
   if p==path:return SimpleNamespace(st_mode=0o100644,st_uid=0,st_nlink=1)
   return original(p)
  with patch.object(Path,'lstat',st):
   path.write_text(json.dumps(job));self.assertEqual(w.load_job(path)['month'],1)
   for key,value in [('month',11),('month',True),('cabinet','wb_dmitrieva'),('nonce','../x'),('expires_epoch',0)]:
    changed={**job,key:value};path.write_text(json.dumps(changed))
    with self.assertRaises(ValueError):w.load_job(path)
 def test_foreign_drop_never_stopped_or_removed(self):
  ledger=self.root/'ledger';ledger.mkdir();drop=self.root/'foreign.conf';drop.write_bytes(b'foreign')
  (ledger/'activation.json').write_text(json.dumps({'nonce':'a'*32,'drop_sha256':'0'*64,'credential_sha256':'0'*64}))
  with patch.object(h,'LEDGER',ledger),patch.object(h,'DROP',drop),patch.object(h.r,'trust'),patch.object(h.r,'run',side_effect=AssertionError('must not stop')):
   with self.assertRaises(ValueError):h.cleanup_owned()
  self.assertEqual(drop.read_bytes(),b'foreign')
 def test_cleanup_restores_only_owned_controls(self):
  ledger=self.root/'ledger';ledger.mkdir();root=self.root/'release';root.mkdir();drop=self.root/'owned.conf';drop.write_bytes(b'owned')
  credential=root/'cabinets.json';credential.write_bytes(b'private fixture')
  (ledger/'activation.json').write_text(json.dumps({'nonce':'a'*32,'drop_sha256':h.r.sha(b'owned'),'credential_sha256':h.r.sha(b'private fixture')}))
  calls=[]
  with patch.object(h,'LEDGER',ledger),patch.object(h,'DROP',drop),patch.object(h,'ROOT',root),patch.object(h.r,'trust'),patch.object(h.r,'run',lambda a:calls.append(a)),patch.object(h.r,'show',return_value={'ActiveState':'inactive','PrivateNetwork':'yes','DropInPaths':''}):h.cleanup_owned()
  self.assertFalse(drop.exists());self.assertFalse(credential.exists());self.assertTrue((ledger/('activation-'+'a'*32+'.json')).exists())
  self.assertEqual(calls,[['/usr/bin/systemctl','daemon-reload']])
 def test_background_start_does_not_wait_for_campaign_or_restart_existing(self):
  commands=[]
  def run(args,timeout=30):
   commands.append(args)
   if '--no-block' in args:return b''
   if 'LoadState' in args:return b'LoadState=not-found\n'
   return b'LoadState=loaded\nActiveState=activating\n'
  with patch.object(start_root.os,'geteuid',return_value=0),patch.object(start_root.r,'verify_payload'),patch.object(start_root.h,'preflight'),patch.object(start_root.r,'run',run):start_root.main()
  launch=[a for a in commands if '/usr/bin/systemd-run' in a][0]
  self.assertIn('--no-block',launch)
  self.assertIn('--property=Restart=no',launch)
  self.assertTrue(any(a.startswith('--property=ExecStopPost=') for a in launch))
 def test_campaign_all_jobs_and_failure_stop_without_budget_reset(self):
  from contextlib import ExitStack
  for fail_at in (None,3):
   folder=self.root/str(fail_at);folder.mkdir();archive=folder/'archive';archive.mkdir();lock=folder/'lock';lock.write_text('')
   results=[];sleeps=[]
   def mkdir(path,mode,uid=0,gid=0):path.mkdir(mode=mode)
   def activate(job,*args):
    results.append((job['cabinet'],job['month']))
    return {'status':'HOLD' if len(results)==fail_at else 'COMPLETE','cabinet':job['cabinet'],'period':f"2026-{job['month']:02d}",'rows':2}
   original=h.Path
   def paths(value):return lock if value=='/var/lib/msp-finance-control/controller.lock' else original(value)
   public=folder/'public.json'
   with ExitStack() as stack:
    for name,value in {'HISTORY':archive/'history','LEDGER':folder/'ledger','PUBLIC':public,'ARCHIVE':archive}.items():stack.enter_context(patch.object(h,name,value))
    stack.enter_context(patch.object(h,'Path',paths));stack.enter_context(patch.object(h.os,'geteuid',return_value=0))
    stack.enter_context(patch.object(h.os,'fchown'));stack.enter_context(patch.object(h.r,'trust'))
    stack.enter_context(patch.object(h,'preflight',return_value=({c:{} for c in h.CABINETS},[])))
    stack.enter_context(patch.object(h,'mkdir_owned',mkdir));stack.enter_context(patch.object(h,'activate',activate));stack.enter_context(patch.object(h.time,'sleep',lambda n:sleeps.append(n)))
    status=h.execute()
   doc=json.loads(public.read_bytes())
   if fail_at is None:
    self.assertEqual(status,0);self.assertEqual(results,h.JOBS);self.assertEqual(doc['completed_monthly_reports'],30)
    self.assertEqual(len(sleeps),29);self.assertTrue(doc['closed_month_realization_coverage_complete'])
   else:
    self.assertEqual(status,1);self.assertEqual(results,h.JOBS[:3]);self.assertEqual(doc['completed_monthly_reports'],2)
    self.assertEqual(doc['status'],'HOLD')
   self.assertTrue((folder/'ledger'/'plan.json').exists())
if __name__=='__main__':unittest.main()
