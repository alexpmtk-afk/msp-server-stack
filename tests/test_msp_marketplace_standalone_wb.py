"""No real API/Redis. Exercise bounded standalone wiring against B7 storage."""
import json
import multiprocessing
import os
import signal
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from apps.msp_marketplace_reports import standalone_wb as s
from apps.msp_marketplace_reports import wb_worker_adapter as w
from apps.msp_marketplace_reports import archive as ar
from apps.msp_marketplace_reports.quota import QuotaBusy
from apps.msp_marketplace_reports.runtime import TransportUnavailable


def kill_before_send(root, plan, auth):
    def fault(label):
        os.kill(os.getpid(), signal.SIGKILL)
    s.run_step(Path(root),plan,auth,lambda: (_ for _ in ()).throw(AssertionError('not sent')),
               now=1000,fault=fault)

def kill_after_page(root, plan, auth):
    def fault(label):
        if label == 'after_page_fsync_before_state':
            os.kill(os.getpid(),signal.SIGKILL)
    original=s.run_one_step
    def wrapped(*args,**kwargs):return original(*args,**kwargs,fault=fault)
    s.run_one_step=wrapped
    row=dict(reportId=555,reportType=1,rrdId=10,dateFrom='2026-10-19',dateTo='2026-10-25',amount='10')
    s.run_step(Path(root),plan,auth,lambda:lambda req:(200,[row]),now=1000)

def concurrent_step(root,plan,auth,entered,start):
    start.wait(5)
    def send(req):
        with entered.get_lock():entered.value+=1
        time.sleep(.15)
        return 200,[dict(reportId=555,reportType=1,rrdId=10,dateTo='2026-10-25',amount='10')]
    s.run_step(Path(root),plan,auth,lambda:send,now=1000)

class StandaloneTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'archive';self.root.mkdir()
        self.plan=dict(schema=1,cabinet='wb_laser_master',year=2026,report_id=555,
                       report_type=1,max_send_entries=3)
        self.auth=dict(schema=1,plan_sha256=s._digest(self.plan),code_sha256=s.code_digest(),
                       archive_root=str(self.root),expires_epoch=9999999999,
                       owner_api_pilot_authorized=True,shared_quota_verified=True,
                       conflicting_clients_excluded=True,evidence_reference='synthetic-only')
    def step(self,send,now=1000):
        return s.run_step(self.root,self.plan,self.auth,lambda:send,now=now)
    def row(self,rrd=10):
        return dict(reportId=555,reportType=self.plan['report_type'],rrdId=rrd,
                    dateFrom='2026-10-19',dateTo='2026-10-25',amount='10')
    def no_call(self,*args):self.fail('must not contact provider')
    def test_vertical_slice_terminal_receipt_and_no_refetch(self):
        seen=[]
        def send(req):
            seen.append(req.body['rrdId'])
            return (200,[self.row()]) if not req.body['rrdId'] else (204,None)
        self.assertEqual(self.step(send)['status'],'PAGE_STAGED')
        self.assertEqual(self.step(self.no_call,1001)['status'],'PAGE_STAGED')
        done=self.step(send,1067)
        self.assertEqual(done['status'],'DONE');self.assertEqual(done['rows'],1)
        replay=self.step(self.no_call,1200)
        self.assertEqual(replay['generation'],done['generation']);self.assertEqual(seen,[0,10])
    def test_three_entry_budget_survives_relaunch_and_never_resets(self):
        for n in range(3):
            result=self.step(lambda req:(200,[self.row((n+1)*10)]),1000+67*n)
        self.assertEqual(result['send_entries'],3)
        for now in (1300,1400):
            result=self.step(self.no_call,now)
            self.assertEqual(result['status'],'PAUSED_BUDGET');self.assertEqual(result['send_entries'],3)
    def test_busy_wait_preserves_page_cursor_and_late_deadline(self):
        self.step(lambda req:(200,[self.row()]))
        def busy(req):
            self.assertEqual(req.body['rrdId'],10);raise QuotaBusy(3600)
        result=self.step(busy,1067)
        self.assertEqual(result['status'],'WAITING_RATE_LIMIT')
        self.assertEqual(self.step(self.no_call,1200),result)
        self.assertGreaterEqual(result['not_before_epoch'],4667)
    def test_typed_transport_failure_retries_saved_cursor(self):
        self.step(lambda req:(200,[self.row()]))
        def error(req):raise TransportUnavailable('synthetic transport failure')
        result=self.step(error,1067);self.assertEqual(result['status'],'WAITING_RETRY')
        self.step(self.no_call,1068)
        def terminal(req):
            self.assertEqual(req.body['rrdId'],10);return 204,None
        self.assertEqual(self.step(terminal,1134)['status'],'DONE')
    def test_owner_quota_conflict_code_plan_expiry_fail_before_writes(self):
        original=dict(self.auth)
        for field,value in [('shared_quota_verified',False),('conflicting_clients_excluded',False),
                            ('owner_api_pilot_authorized',False),('expires_epoch',999),
                            ('code_sha256','bad'),('plan_sha256','bad')]:
            with self.subTest(field=field):
                self.auth={**original,field:value}
                with self.assertRaises(s.PilotBlocked):self.step(self.no_call)
                self.assertFalse((self.root/'.locks').exists())
        self.auth=original
    def test_corrupted_journal_does_not_reset_budget(self):
        self.step(lambda req:(200,[self.row()]))
        path=next((self.root/'.wb-executor').glob('*.json'));d=json.loads(path.read_bytes())
        d['send_entries']=0;path.write_text(json.dumps(d));before=path.read_bytes()
        with self.assertRaisesRegex(s.PilotBlocked,'checksum'):self.step(self.no_call,1100)
        self.assertEqual(path.read_bytes(),before)
    def test_budget_write_failure_means_no_factory_or_http(self):
        real=s._safe_write
        def fail(path,data):
            if b'DISPATCH_UNCERTAIN' in data:raise OSError('synthetic disk failure')
            return real(path,data)
        with patch.object(s,'_safe_write',fail):
            result=self.step(self.no_call)
        self.assertEqual(result['status'],'HOLD_ERROR')
        self.assertEqual(self.step(self.no_call,1200)['status'],'HOLD_ERROR')
    def test_actual_sigkill_after_durable_budget_reconciles_conservatively(self):
        proc=multiprocessing.get_context('fork').Process(target=kill_before_send,
            args=(str(self.root),self.plan,self.auth));proc.start();proc.join(10)
        self.assertEqual(proc.exitcode,-signal.SIGKILL)
        result=self.step(lambda req:(200,[self.row()]),1100)
        self.assertEqual(result['send_entries'],2)
    def test_buyout_separate_registry_and_strict_plan(self):
        self.plan['report_type']=2;self.auth['plan_sha256']=s._digest(self.plan)
        self.step(lambda req:(200,[self.row()]))
        self.assertEqual(self.step(lambda req:(204,None),1067)['status'],'DONE')
        self.plan['max_send_entries']=True
        with self.assertRaises(s.PilotBlocked):self.step(self.no_call,1200)
    def test_non_root_authorization_and_duplicate_json_refused(self):
        path=Path(self.tmp.name)/'approval.json';path.write_text('{"schema":1,"schema":1}')
        with self.assertRaises(s.PilotBlocked):s.read_control(path)
        path.write_text('{}')
        if os.geteuid()!=0:
            with self.assertRaises(s.PilotBlocked):s.read_authorization(path)

    def test_two_processes_one_local_owner_one_provider_entry(self):
        ctx=multiprocessing.get_context('fork');entered=ctx.Value('i',0);start=ctx.Event()
        procs=[ctx.Process(target=concurrent_step,args=(str(self.root),self.plan,self.auth,entered,start)) for _ in range(2)]
        for p in procs:p.start()
        start.set()
        for p in procs:p.join(10);self.assertEqual(p.exitcode,0)
        self.assertEqual(entered.value,1)
    def test_sigkill_after_page_replays_without_spending_another_entry(self):
        ctx=multiprocessing.get_context('fork');p=ctx.Process(target=kill_after_page,args=(str(self.root),self.plan,self.auth))
        p.start();p.join(10);self.assertEqual(p.exitcode,-signal.SIGKILL)
        result=self.step(self.no_call,1100)
        self.assertEqual(result['status'],'PAGE_STAGED');self.assertEqual(result['send_entries'],1)
        done=self.step(lambda req:(204,None),1167)
        self.assertEqual(done['status'],'DONE');self.assertEqual(done['send_entries'],2)
