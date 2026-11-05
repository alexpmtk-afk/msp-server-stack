"""Only new batch behavior; no accepted production tests repeated locally."""
import importlib.util,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from apps.msp_marketplace_reports import standalone_wb as s
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('next_worker',ROOT/'scripts/finance_campaign/next_worker.py');w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)
class NextBatch(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR',str(ROOT)));self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name);self.now=1000.;self.calls=[]
 def auth(self,plan):return {'schema':1,'plan_sha256':s._digest(plan),'code_sha256':s.code_digest(),'archive_root':str(self.root),'expires_epoch':9999999999,'owner_api_pilot_authorized':True,'shared_quota_verified':True,'conflicting_clients_excluded':True,'evidence_reference':'OFFLINE_TEST'}
 def sleep(self,t):self.now+=t
 def completed(self,rid,kind,count):
  plan={'schema':1,'cabinet':'wb_laser_master','year':2026,'report_id':rid,'report_type':kind,'max_send_entries':3}
  replies=iter([(200,[{'reportId':rid,'reportType':kind,'rrdId':n} for n in range(1,count+1)]),(204,None)])
  return s.run_bounded(self.root,plan,self.auth(plan),lambda:lambda req:next(replies),clock=lambda:self.now,sleep=self.sleep)
 def test_real_loader_next_main_keeps_both_completed_budgets_and_skips_on_repeat(self):
  self.completed(883801632,1,841);self.completed(883801636,2,46)
  actual=json.loads((ROOT/'docs/marketplace-reports/next-20261105/WB_EXECUTION_RECEIPT.json').read_text())['outcome']['discovery']['items']
  from apps.msp_marketplace_reports import wb_discovery_resume as discovery
  discovery.step(self.root,w.DISCOVERY,self.auth(w.DISCOVERY),lambda:lambda req:(200,actual),now=self.now)
  discovery.step(self.root,w.DISCOVERY,self.auth(w.DISCOVERY),lambda:(_ for _ in ()).throw(AssertionError('replay only')),now=self.now)
  before={p:p.read_bytes() for p in (self.root/'.wb-executor').glob('*.json')}
  replies=iter([(200,[{'reportId':865431404,'reportType':1,'rrdId':1}]),(204,None)])
  def factory():
   def send(req):
    self.assertFalse(req.path.endswith(('/883801632','/883801636')));self.calls.append(req.path);return next(replies)
   return send
  out=w.execute(self.root,self.auth(w.BATCH),factory,clock=lambda:self.now,sleep=self.sleep)
  self.assertTrue(out['report_detail_complete']);self.assertEqual(out['report_type'],1);self.assertEqual(out['receipt']['rows'],1);self.assertNotIn('/api/finance/v1/sales-reports/list',self.calls)
  for p,raw in before.items():self.assertEqual(raw,p.read_bytes())
  self.calls=[];again=w.execute(self.root,self.auth(w.BATCH),factory,clock=lambda:self.now,sleep=self.sleep);self.assertTrue(again['report_detail_complete']);self.assertEqual(self.calls,[])
 def test_missing_completed_buyout_stops_before_discovery(self):
  self.completed(883801632,1,841)
  with self.assertRaisesRegex(ValueError,'buyout'):w.execute(self.root,self.auth(w.BATCH),lambda:(_ for _ in ()).throw(AssertionError('no sender')),clock=lambda:self.now,sleep=self.sleep)
 def test_completed_routes_denied_before_opener(self):
  import urllib.request,types
  op=w.AuditedOpener(types.SimpleNamespace(open=lambda *a,**k:(_ for _ in ()).throw(AssertionError('no opener'))),self.root/'events')
  for rid in [883801632,883801636]:
   with self.assertRaises(ValueError):op.open(urllib.request.Request('https://finance-api.wildberries.ru/api/finance/v1/sales-reports/detailed/'+str(rid),data=b'{}',method='POST'),60)
