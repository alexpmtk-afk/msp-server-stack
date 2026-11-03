"""Network-free tests of bounded discovery, revision publication and refresh planning."""
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from apps.msp_marketplace_reports import standalone_wb as s, wb_discovery_resume as d
from apps.msp_marketplace_reports.finance_refresh_plan import build_refresh_plan,digest,discovery_windows
from apps.msp_marketplace_reports.wb_report_revision import publish_revision,revision_root
from apps.msp_marketplace_reports.wb_page_resume import step_wb_detail
from apps.msp_marketplace_reports.generation_store import GenerationError,read_active
from apps.msp_marketplace_reports.versioned_archive import read_csv_versioned
from apps.msp_marketplace_reports.archive import _rows,DATASETS
from apps.msp_marketplace_reports.quota import QuotaBusy

CAB='wb_laser_master'
def item(rid=883801632,kind=1):return {'reportId':rid,'reportType':kind,'dateFrom':'2026-10-19','dateTo':'2026-10-25'}
def row(rid=883801632,cursor=1,kind=1,value='100'):return {'reportId':rid,'reportType':kind,'rrdId':cursor,'amount':value,'dateTo':'2026-10-25'}
class Temp(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)/'archive';self.root.mkdir()

class Discovery(Temp):
    def setUp(self):
        super().setUp();self.plan={'schema':1,'kind':'wb-discovery','cabinet':CAB,'year':2026,'date_from':'2026-01-01','date_to':'2026-11-03','limit':2,'max_send_entries':3}
        self.auth={'schema':1,'plan_sha256':s._digest(self.plan),'code_sha256':s.code_digest(),'archive_root':str(self.root),'expires_epoch':9999999999,'owner_api_pilot_authorized':True,'shared_quota_verified':True,'conflicting_clients_excluded':True,'evidence_reference':'OFFLINE_SYNTHETIC'}
    def go(self,send,now=1000,fault=None):return d.step(self.root,self.plan,self.auth,lambda:send,now=now,fault=fault)
    def no(self,r):raise AssertionError('no extra HTTP')
    def test_durable_list_offset_both_types_and_no_refetch(self):
        requests=[]
        def send(r):requests.append(r);return 200,[item(),item(883801636,2)]
        self.assertEqual(self.go(send)['status'],'PAGE_STAGED_RECONCILE')
        self.assertEqual(self.go(self.no)['offset'],2)
        self.assertEqual(self.go(lambda r:(204,None))['status'],'PAGE_STAGED_RECONCILE')
        out=self.go(self.no);self.assertEqual(out['status'],'COMPLETE');self.assertEqual(out['entries'],2)
        self.assertEqual(len(out['items']),2);self.assertEqual(requests[0].body['offset'],0)
        self.assertEqual(self.go(self.no)['entries'],2)
    def test_page_written_before_crash_replays_no_new_budget(self):
        def crash(stage):
            if stage=='after_page_before_state':raise RuntimeError('synthetic crash')
        with self.assertRaises(RuntimeError):self.go(lambda r:(200,[item()]),fault=crash)
        out=self.go(self.no);self.assertEqual(out['status'],'COMPLETE');self.assertEqual(out['entries'],1)
    def test_429_preserves_offset_budget_and_delay(self):
        out=self.go(lambda r:(_ for _ in ()).throw(QuotaBusy(120)))
        self.assertEqual(out['entries'],1);self.assertEqual(out['offset'],0);self.assertEqual(out['not_before_epoch'],1120)
        self.assertEqual(self.go(self.no,1100)['entries'],1)
    def test_budget_never_resets_after_reentry(self):
        for now in [1000,1100,1200]:self.go(lambda r:(429,None),now)
        out=self.go(self.no,1400);self.assertEqual(out['status'],'PAUSED_BUDGET');self.assertEqual(out['entries'],3)
        self.assertEqual(self.go(self.no,1500)['entries'],3)
    def test_missing_cutover_blocks_before_factory(self):
        self.auth['conflicting_clients_excluded']=False
        with self.assertRaises(s.PilotBlocked):self.go(self.no)
        self.assertFalse((self.root/'.wb-executor').exists())
    def test_changed_journal_does_not_reseal(self):
        self.go(lambda r:(429,None));p=next((self.root/'.wb-executor').glob('discovery-*.json'));obj=json.loads(p.read_text());obj['entries']=0;p.write_text(json.dumps(obj))
        with self.assertRaisesRegex(GenerationError,'checksum'):self.go(self.no,2000)

    def test_read_inventory_joins_acknowledged_evidence_not_partial_window(self):
        self.go(lambda r:(200,[item()]))
        with self.assertRaises(GenerationError):d.read_inventory(self.root,[self.plan])
        self.go(self.no)
        inventory=d.read_inventory(self.root,[self.plan])
        self.assertEqual(inventory['status'],'DISCOVERED_NOT_DOWNLOADED')
        self.assertEqual(len(inventory['items']),1)
    def test_invalid_metadata_holds_without_repeated_http(self):
        out=self.go(lambda r:(200,[{'wrong':'synthetic'}]))
        self.assertEqual(out['status'],'HOLD_ERROR');self.assertEqual(out['entries'],1)
        self.assertEqual(self.go(self.no,1100)['status'],'HOLD_ERROR')

class Revisions(Temp):
    def stage(self,revision,rows,rid=883801632,kind=1):
        root=revision_root(self.root,revision);root.mkdir(parents=True)
        step_wb_detail(root,CAB,2026,rid,kind,lambda r:(200,rows))
        step_wb_detail(root,CAB,2026,rid,kind,lambda r:(204,None))
    def pub(self,revision,parent=None,rid=883801632,kind=1):return publish_revision(self.root,cabinet=CAB,year=2026,report_id=rid,report_type=kind,revision=revision,expected_generation=parent,checked_at='2026-11-03T10:00:00+00:00')
    def test_late_correction_replaces_changed_and_removed_rows_keeps_other_report(self):
        self.stage('first',[row(cursor=1),row(cursor=2)]);a=self.pub('first')
        self.stage('another',[row(99,1)],rid=99);b=self.pub('another',a['generation'],rid=99)
        self.stage('correction',[row(cursor=1,value='75')]);c=self.pub('correction',b['generation'])
        raw,_=read_csv_versioned(self.root,'wb_weekly_finance_main',CAB,'2026');_,rows=_rows(raw,DATASETS['wb_weekly_finance_main'][1])
        self.assertEqual(len(rows),2);self.assertEqual(rows[('883801632','1')]['amount'],'75');self.assertIn(('99','1'),rows)
        old,_=read_csv_versioned(self.root,'wb_weekly_finance_main',CAB,'2026',pinned_generation=a['generation'],expected_digest=a['manifest_sha256'])
        self.assertEqual(len(_rows(old,DATASETS['wb_weekly_finance_main'][1])[1]),2)
        self.assertTrue(c['report_content_changed'])
    def test_stale_revision_rejected_without_overwrite(self):
        self.stage('one',[row()]);a=self.pub('one');self.stage('two',[row(value='55')])
        with self.assertRaisesRegex(GenerationError,'stale'):self.pub('two')
        self.assertEqual(read_active(self.root,'wb_weekly_finance_main',CAB,'2026')['generation'],a['generation'])
    def test_partial_report_not_publishable(self):
        root=revision_root(self.root,'partial');root.mkdir(parents=True);step_wb_detail(root,CAB,2026,883801632,1,lambda r:(200,[row()]))
        with self.assertRaisesRegex(GenerationError,'not terminal'):self.pub('partial')
    def test_main_buyout_isolation(self):
        self.stage('main',[row()]);self.pub('main')
        self.stage('buyout',[row(883801636,kind=2)],rid=883801636,kind=2);self.pub('buyout',rid=883801636,kind=2)
        self.assertIsNotNone(read_active(self.root,'wb_weekly_finance_buyout',CAB,'2026'))
    def test_repeated_same_verified_revision_is_noop(self):
        self.stage('same',[row()]);a=self.pub('same');b=self.pub('same',a['generation']);self.assertFalse(b['changed']);self.assertFalse(b['report_content_changed'])

class Plans(unittest.TestCase):
    def inv(self):return {CAB:{'cabinet':CAB,'year':2026,'status':'DISCOVERED_NOT_DOWNLOADED','items':[item(),item(883801636,2)]}}
    def test_bounded_three_cabinet_discovery_no_guess_empty(self):
        p=build_refresh_plan(as_of=date(2026,11,3),max_actions=4)
        self.assertEqual(len(p['actions']),4);self.assertEqual(p['remaining_actions'],29);self.assertEqual(len(p['gaps']),3)
        self.assertEqual(p['network_calls'],0);self.assertFalse(p['executable_without_admission'])
    def test_type1_type2_separate_deterministic_units(self):
        a=build_refresh_plan(as_of=date(2026,11,3),discoveries=self.inv(),max_actions=100)
        wb=[x for x in a['actions'] if x['cabinet']==CAB];self.assertEqual(len(wb),2);self.assertNotEqual(wb[0]['unit_id'],wb[1]['unit_id'])
        self.assertEqual(a,build_refresh_plan(as_of=date(2026,11,3),discoveries=self.inv(),max_actions=100))
    def test_daily_revalidates_same_id_even_without_metadata_change(self):
        meta=digest(item());ev={f'{CAB}:883801632:1':{'verified':True,'terminal_http_status':204,'page_hashes_verified':True,'publication_verified':True,'metadata_sha256':meta,'last_checked_at':'2026-11-01T00:00:00+00:00'}}
        p=build_refresh_plan(as_of=date(2026,11,3),discoveries=self.inv(),evidence=ev,mode='daily',max_actions=100)
        self.assertTrue(any(x['action']=='REFETCH_REVISION' and x['report_id']==883801632 for x in p['actions']))
    def test_final_closed_current_separate(self):
        p=build_refresh_plan(as_of=date(2026,11,3));tasks=p['ozon_separate_plan']
        self.assertEqual(len([x for x in tasks if x['dataset']=='ozon_final_realization']),30)
        self.assertFalse(any(x['period']=='2026-11' and x['dataset']=='ozon_final_realization' for x in tasks))
        self.assertEqual(len([x for x in tasks if x['period']=='2026-11']),9)
    def test_january_future_and_bounded_inputs(self):
        self.assertEqual(len(discovery_windows(2026,date(2026,1,2))),1)
        for n in [True,0,101]:
            with self.assertRaises(ValueError):build_refresh_plan(as_of=date(2026,11,3),max_actions=n)


class OzonPreparation(unittest.TestCase):
    def test_separate_final_current_and_method_gate(self):
        from apps.msp_marketplace_reports.ozon_connection_plan import connection_plan
        from apps.msp_marketplace_reports.providers import OZON_FINAL,OZON_ACCRUAL
        from apps.msp_marketplace_reports.archive import CABINETS
        p=connection_plan(CABINETS['ozon'][0],date(2026,11,3))
        self.assertEqual(len(p['final']),10);self.assertTrue(all(r.path==OZON_FINAL for r in p['final']))
        self.assertEqual(len([r for r in p['current'] if r.path==OZON_ACCRUAL]),3)
        self.assertFalse(p['orders_are_final']);self.assertFalse(p['api_enabled'])
    def test_existing_quota_blocks_unaccepted_ozon_methods(self):
        from apps.msp_marketplace_reports.quota import request_rules,OZON_REQUIRED_METHOD_APPROVAL
        from apps.msp_marketplace_reports.providers import Request,OZON_FINAL,ProviderError
        with patch.dict('os.environ',{OZON_REQUIRED_METHOD_APPROVAL:''}):
            with self.assertRaises(ProviderError):request_rules('ozon',{'client_id':'123'},Request('ozon',OZON_FINAL,{'year':2026,'month':1}))
    def test_wrong_cabinet_rejected(self):
        from apps.msp_marketplace_reports.ozon_connection_plan import connection_plan
        with self.assertRaises(ValueError):connection_plan('wb_laser_master',date(2026,11,3))

class WindowReceipts(unittest.TestCase):
    def test_completed_window_not_resubmitted_while_inventory_incomplete(self):
        ev={f'list:{CAB}:2026-01-01:2026-01-31':{'checked_on':'2026-11-03'}}
        result=build_refresh_plan(as_of=date(2026,11,3),evidence=ev,max_actions=100)
        self.assertFalse(any(x['cabinet']==CAB and x.get('body',{}).get('dateFrom')=='2026-01-01' for x in result['actions']))

class PreparationArtifacts(unittest.TestCase):
    def test_synthetic_launcher_payload_hash_and_nonroot_refusal(self):
        import importlib.util,hashlib,base64,os,sys
        repo=Path(__file__).resolve().parents[1]
        spec=importlib.util.spec_from_file_location('prepared_root_launcher',repo/'docs/marketplace-reports/execution-20261103/run-synthetic.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        raw=base64.b64decode(module.PAYLOAD)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),module.DIGEST)
        self.assertEqual(raw,(repo/'docs/marketplace-reports/pilot-next-20261103/synthetic_quota.py').read_bytes())
        with patch.object(os,'geteuid',return_value=1001),patch.object(sys,'argv',['run','--synthetic-write-approved']),patch('builtins.print'):
            self.assertEqual(module.main(),2)
    def test_pilot_packet_keeps_budget3_and_no_api_approval(self):
        repo=Path(__file__).resolve().parents[1]/'docs/marketplace-reports/execution-20261103'
        plan=json.loads((repo/'pilot-plan.json').read_text());auth=json.loads((repo/'authorization.BLOCKED.json').read_text())
        self.assertEqual(plan['report_id'],883801632);self.assertEqual(plan['max_send_entries'],3)
        self.assertFalse(auth['owner_api_pilot_authorized']);self.assertFalse(auth['conflicting_clients_excluded']);self.assertEqual(auth['expires_epoch'],0)
    def test_daily_template_inert_no_finance_sender(self):
        repo=Path(__file__).resolve().parents[1]/'docs/marketplace-reports/execution-20261103'
        unit=(repo/'msp-finance-daily-plan.service.in').read_text();timer=(repo/'msp-finance-daily-plan.timer.in').read_text()
        self.assertIn('finance_refresh_plan',unit);self.assertNotIn('ReadOnlyHTTP',unit)
        self.assertFalse(any(line.strip().startswith('OnCalendar=') for line in timer.splitlines()));self.assertNotIn('[Install]',[line.strip() for line in timer.splitlines()])

class HistoricalPilot(Temp):
    def setUp(self):
        super().setUp();self.plan={'schema':1,'cabinet':CAB,'year':2026,'report_id':883801632,'report_type':1,'max_send_entries':3}
        self.auth={'schema':1,'plan_sha256':s._digest(self.plan),'code_sha256':s.code_digest(),'archive_root':str(self.root),'expires_epoch':9999999999,'owner_api_pilot_authorized':True,'shared_quota_verified':True,'conflicting_clients_excluded':True,'evidence_reference':'SYNTHETIC_ONLY'}
    def go(self,send,now):return s.run_step(self.root,self.plan,self.auth,lambda:send,now=now)
    def test_100_rows_not_complete_then_next_cursor_and204_full_download(self):
        seen=[]
        def send(req):
            seen.append(req.body['rrdId'])
            return (200,[row(cursor=i) for i in range(1,101)]) if len(seen)==1 else ((200,[row(cursor=101)]) if len(seen)==2 else (204,None))
        a=self.go(send,1000);self.assertEqual(a['status'],'PAGE_STAGED');self.assertEqual(a['send_entries'],1)
        b=self.go(send,1100);self.assertEqual(b['status'],'PAGE_STAGED')
        c=self.go(send,1200);self.assertEqual(c['status'],'DONE');self.assertEqual(c['rows'],101);self.assertEqual(c['send_entries'],3)
        self.assertEqual(seen,[0,100,101])
        def no(req):raise AssertionError('completed report refetched')
        self.assertEqual(self.go(no,1300)['send_entries'],3)
    def test_three_nonterminal_pages_pause_without_budget_reset(self):
        for i in range(3):out=self.go(lambda req:(200,[row(cursor=req.body['rrdId']+1)]),1000+i*100)
        def no(req):raise AssertionError('over budget')
        out=self.go(no,1400);self.assertEqual(out['status'],'PAUSED_BUDGET');self.assertEqual(out['send_entries'],3)
        self.assertEqual(self.go(no,1500)['send_entries'],3)

class ActualReceipts(Temp):
    def test_missing_root_read_does_not_initialize(self):
        from apps.msp_marketplace_reports.finance_receipts import report_receipt
        missing=self.root/'not-created'
        self.assertEqual(report_receipt(missing,CAB,2026,883801632,1)['status'],'MISSING')
        self.assertFalse(missing.exists())
    def test_partial_cursor_and_budget_are_read_without_writes(self):
        from apps.msp_marketplace_reports.finance_receipts import report_receipt
        plan={'schema':1,'cabinet':CAB,'year':2026,'report_id':883801632,'report_type':1,'max_send_entries':3}
        auth={'schema':1,'plan_sha256':s._digest(plan),'code_sha256':s.code_digest(),'archive_root':str(self.root),'expires_epoch':9999999999,'owner_api_pilot_authorized':True,'shared_quota_verified':True,'conflicting_clients_excluded':True,'evidence_reference':'SYNTHETIC'}
        s.run_step(self.root,plan,auth,lambda:lambda req:(200,[row()]),now=1000)
        before={str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        out=report_receipt(self.root,CAB,2026,883801632,1)
        self.assertEqual(out['cursor'],1);self.assertEqual(out['budget_entries'],1);self.assertFalse(out['verified'])
        self.assertEqual(before,{str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        ev={f'{CAB}:883801632:1':out}
        plan=build_refresh_plan(as_of=date(2026,11,3),discoveries={CAB:{'cabinet':CAB,'year':2026,'status':'DISCOVERED_NOT_DOWNLOADED','items':[item()]}},evidence=ev,max_actions=100)
        self.assertTrue(any(x['action']=='RESUME_OR_DOWNLOAD' for x in plan['actions']))
    def test_modified_page_blocks_download_instead_of_recertifying(self):
        from apps.msp_marketplace_reports.finance_receipts import report_receipt
        step_wb_detail(self.root,CAB,2026,883801632,1,lambda req:(200,[row()]))
        page=next(self.root.rglob('page-0.json'));page.write_text('invalid')
        out=report_receipt(self.root,CAB,2026,883801632,1)
        self.assertEqual(out['status'],'HOLD_INVALID_LOCAL_EVIDENCE')
        inv={CAB:{'cabinet':CAB,'year':2026,'status':'DISCOVERED_NOT_DOWNLOADED','items':[item()]}}
        tasks=build_refresh_plan(as_of=date(2026,11,3),discoveries=inv,evidence={f'{CAB}:883801632:1':out},max_actions=100)['actions']
        self.assertTrue(any(x['action']=='REVIEW_LOCAL_EVIDENCE' for x in tasks))
        self.assertFalse(any(x['cabinet']==CAB and x['action']=='RESUME_OR_DOWNLOAD' for x in tasks))
    def test_latest_revision_reads_real_checks_and_pinned_business_values(self):
        from apps.msp_marketplace_reports.finance_receipts import report_receipt
        root=revision_root(self.root,'latest');root.mkdir(parents=True)
        step_wb_detail(root,CAB,2026,883801632,1,lambda req:(200,[row()]))
        step_wb_detail(root,CAB,2026,883801632,1,lambda req:(204,None))
        publish_revision(self.root,cabinet=CAB,year=2026,report_id=883801632,report_type=1,revision='latest',expected_generation=None,checked_at='2026-11-03T10:00:00+00:00',report_metadata=item())
        out=report_receipt(self.root,CAB,2026,883801632,1)
        self.assertTrue(out['verified']);self.assertEqual(out['rows'],1);self.assertEqual(out['metadata_sha256'],digest(item()))

if __name__=='__main__':unittest.main()
