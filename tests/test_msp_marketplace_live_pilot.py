"""No root/systemd/API effects: E payload safety and real accepted-loader integration."""
import base64
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
launcher=load('E_launcher','scripts/wb_live_pilot/launch.py')
runner=load('E_runner','scripts/wb_live_pilot/runner.py')

class Pure(unittest.TestCase):
    def token(self,expiry=10000,sid='synthetic_seller'):
        return 'synthetic.'+base64.urlsafe_b64encode(json.dumps({'sid':sid,'exp':expiry}).encode()).decode().rstrip('=')+'.no_signature'
    def test_pilot_alias_binding_allows_only_selected_token_no_claim_auth(self):
        token=self.token();pilot=json.dumps({'wb_laser_master':{'token':token}}).encode()
        master=json.dumps({'wb_laser_master':{'token':token,'private_metadata':'not copied'},'wb_dmitrieva':{'token':'never copied'}}).encode()
        out=launcher.verify_credentials(pilot,master,100)
        self.assertTrue(out['pilot_master_match']);self.assertFalse(out['signature_or_finance_permission_proven'])
        self.assertNotIn(token,json.dumps(out))
    def test_expired_changed_and_boolean_seller_refused(self):
        for one,two in [(self.token(1),self.token(1)),(self.token(),self.token(sid='other')),(self.token(sid=True),self.token(sid=True))]:
            with self.assertRaises(ValueError):launcher.verify_credentials(json.dumps({'wb_laser_master':{'token':one}}).encode(),json.dumps({'wb_laser_master':{'token':two}}).encode(),100)
    def test_redis_env_exact_local_no_injected_gates_or_python(self):
        good=b'MARKETPLACE_MCP_REDIS_URL=redis://quota_runtime:synthetic@127.0.0.1:16379/0\nMARKETPLACE_REQUIRE_REDIS=1\n'
        launcher.redis_config(good)
        for bad in [good+b'PYTHONPATH=/untrusted\n',good.replace(b'127.0.0.1',b'external'),good.replace(b'/0',b'/1'),good+b'MARKETPLACE_REQUIRE_REDIS=1\n']:
            with self.assertRaises(ValueError):launcher.redis_config(bad)
    def test_response_requires_exact_typed_report_identity(self):
        runner.validate_response(200,[{'reportId':883801632,'reportType':1,'rrdId':1}])
        for row in [{'rrdId':1},{'reportId':1,'reportType':1,'rrdId':1},{'reportId':883801632,'reportType':2,'rrdId':1},{'reportId':883801632,'reportType':1,'rrdId':True}]:
            with self.assertRaises(ValueError):runner.validate_response(200,[row])
    def test_scope_denies_before_any_opener_or_journal(self):
        class No:
            def open(self,*a,**k):raise AssertionError('no HTTP')
        opener=runner.AuditedOpener(No(),Path('/not-used'))
        req=urllib.request.Request('https://finance-api.wildberries.ru/api/v1/account/balance',data=b'{}',method='POST')
        with self.assertRaises(ValueError):opener.open(req,60)
        req=urllib.request.Request(runner.URL,data=b'{"limit":1000,"rrdId":true}',method='POST')
        with self.assertRaises(ValueError):opener.open(req,60)
    def test_nonroot_refusal_before_privileged_reads(self):
        with patch.object(os,'geteuid',return_value=1001),patch.object(launcher,'preflight',side_effect=AssertionError('no read')),patch('builtins.print'):
            self.assertEqual(launcher.main(),2)
    def test_dropin_is_ephemeral_existing_service_single_sender_no_timer(self):
        text=launcher.dropin_text(Path('/var/lib/controlled/runner.py'),['127.0.0.1/32','203.0.113.5/32']).decode()
        self.assertIn('IPAddressDeny=any',text);self.assertIn('IPAddressAllow=127.0.0.1/32 203.0.113.5/32',text)
        self.assertIn('redis-runtime.env',text);self.assertIn('-I -B /var/lib/controlled/runner.py',text)
        self.assertNotIn('Restart=always',text);self.assertNotIn('[Install]',text);self.assertNotIn('LoadCredential',text)

class TempFixture(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR",str(ROOT)));self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)

class Files(TempFixture):
    def trusted(self,p,uid=0,mode=None):return self.original_trust(p,uid=os.geteuid(),mode=mode)
    def test_cleanup_refuses_changed_or_linked_control(self):
        p=self.root/'control';p.write_bytes(b'new-state');self.original_trust=launcher.trusted
        with patch.object(launcher,'trusted',side_effect=self.trusted):
            with self.assertRaises(ValueError):launcher.safe_remove(p,launcher.sha(b'old-state'))
            self.assertEqual(p.read_bytes(),b'new-state')
            launcher.safe_remove(p,launcher.sha(b'new-state'));self.assertFalse(p.exists())
        p.symlink_to(self.root/'missing')
        with self.assertRaises(ValueError):launcher.safe_remove(p,launcher.sha(b''))
    def test_root_write_is_exclusive_and_explicit_mode_under077(self):
        p=self.root/'program';previous=os.umask(0o077)
        try:
            with patch.object(os,'fchown',return_value=None):launcher.write_new(p,b'code',0o644)
        finally:os.umask(previous)
        self.assertEqual(p.stat().st_mode&0o777,0o644)
        with self.assertRaises(FileExistsError):launcher.write_new(p,b'replacement')
    def test_dispatch_evidence_precedes_response_without_leaking_header(self):
        log=self.root/'events'
        class Response:status=200
        class Inner:
            def open(self,req,timeout):
                self_result=json.loads(log.read_text().splitlines()[0]);assert self_result['event']=='HTTP_DISPATCH_ATTEMPT'
                return Response()
        req=urllib.request.Request(runner.URL,data=b'{"limit":1000,"rrdId":0}',headers={'Authorization':'synthetic-never-log'},method='POST')
        runner.AuditedOpener(Inner(),log).open(req,60)
        self.assertNotIn('synthetic-never-log',log.read_text());self.assertEqual(len(log.read_text().splitlines()),2)
    def test_event_journal_symlink_fails_before_http(self):
        log=self.root/'events';log.symlink_to(self.root/'external')
        class Inner:
            def open(self,*a,**k):raise AssertionError('no HTTP')
        req=urllib.request.Request(runner.URL,data=b'{"limit":1000,"rrdId":0}',method='POST')
        with self.assertRaises(ValueError):runner.AuditedOpener(Inner(),log).open(req,60)
        self.assertFalse((self.root/'external').exists())

class LoaderIntegration(TempFixture):
    def simulate(self,answers):
        from apps.msp_marketplace_reports import standalone_wb as s,runtime
        archive=self.root/'archive';archive.mkdir();release=self.root/'release';release.mkdir()
        (release/'pilot-plan.json').write_text(json.dumps(launcher.PLAN))
        auth={'schema':1,'plan_sha256':s._digest(launcher.PLAN),'code_sha256':s.code_digest(),'archive_root':str(archive),'expires_epoch':9999999999,'owner_api_pilot_authorized':True,'shared_quota_verified':True,'conflicting_clients_excluded':True,'evidence_reference':'OFFLINE_SYNTHETIC'}
        now=[1000];actual_run=s.run_bounded;calls=[];pending=iter(answers)
        class Response:
            def __init__(self,status,rows):self.status=status;self.rows=rows
            def read(self,n):return json.dumps(self.rows).encode()
            def __enter__(self):return self
            def __exit__(self,*args):return False
        class Inner:
            def open(self,req,timeout):
                journal=json.loads(next((archive/'.wb-executor').glob('[0-9a-f]*.json')).read_text())
                assert 1<=journal['send_entries']<=3
                calls.append(json.loads(req.data)['rrdId']);status,rows=next(pending);return Response(status,rows)
        def bounded(*args):return actual_run(*args,clock=lambda:now[0],sleep=lambda dt:now.__setitem__(0,now[0]+dt))
        out=io.StringIO()
        with patch.object(runner,'RELEASE',release),patch.object(runner,'ARCHIVE',archive),patch.object(s,'read_authorization',return_value=auth),patch.object(s,'run_bounded',side_effect=bounded),patch.object(runtime,'load_credentials',return_value={'wb_laser_master':{'token':'synthetic-never-log'}}),patch.object(runtime,'_rate_gate',return_value=contextlib.nullcontext()),patch.object(runtime.urllib.request,'build_opener',return_value=Inner()),patch.object(runtime.SharedQuota,'reserve',return_value=[]),patch.dict(os.environ,{'CREDENTIALS_DIRECTORY':str(self.root),'MSP_REPORTS_SHARED_QUEUE_VERIFIED':'YES','MARKETPLACE_MCP_REDIS_URL':'redis://synthetic-local-only'}),contextlib.redirect_stdout(out):
            rc=runner.main(expected_uid=os.geteuid())
        self.assertNotIn('synthetic-never-log',out.getvalue())
        return rc,json.loads(out.getvalue()),calls
    def row(self,n):return {'reportId':883801632,'reportType':1,'rrdId':n}
    def test_real_pr104_runner_two_pages_then204(self):
        rc,summary,calls=self.simulate([(200,[self.row(n) for n in range(1,101)]),(200,[self.row(101)]),(204,None)])
        self.assertEqual(rc,0);self.assertEqual(calls,[0,100,101]);self.assertEqual(summary['rows'],101)
        self.assertTrue(summary['report_detail_complete']);self.assertEqual(summary['http_dispatch_attempts_this_run'],3)
        self.assertEqual(summary['http_response_statuses'],[200,200,204]);self.assertEqual(summary['executor']['send_entries'],3)
    def test_three_pages_pause_no_fourth_attempt(self):
        rc,summary,calls=self.simulate([(200,[self.row(1)]),(200,[self.row(2)]),(200,[self.row(3)])])
        self.assertEqual(rc,2);self.assertEqual(len(calls),3);self.assertFalse(summary['report_detail_complete'])
        self.assertEqual(summary['executor']['status'],'PAUSED_BUDGET');self.assertEqual(summary['rows_staged'],3)
    def test_wrong_report_fails_after_one_budgeted_attempt(self):
        rc,summary,calls=self.simulate([(200,[{'reportId':1,'reportType':1,'rrdId':1}])])
        self.assertEqual(rc,2);self.assertEqual(len(calls),1);self.assertEqual(summary['executor']['status'],'HOLD_ERROR')
        self.assertFalse(summary['report_detail_complete']);self.assertEqual(summary['pages'],0)


class Coordinator(TempFixture):
    def setup_scope(self):
        control=self.root/'control';control.mkdir();run=self.root/'run';run.mkdir();private=self.root/'state';public=self.root/'public'
        return {'CONTROL':control,'APPROVAL':control/'approval.json','STATE':private,'PUBLIC':public,'DROP_DIR':run/'pilot.service.d','DROP':run/'pilot.service.d/test.conf'}
    def test_single_start_cleanup_and_completed_repeat_no_http(self):
        values=self.setup_scope();commands=[];calls=[];program=b'synthetic not executed'
        assets={'runner_base64':base64.b64encode(program).decode(),'runner_sha256':launcher.sha(program),'app_code_sha256':'a'*64}
        orig_trust=launcher.trusted
        def trust(p,uid=0,mode=None):return orig_trust(p,uid=0 if p.lstat().st_uid==0 else os.getuid(),mode=mode)
        def show():return {'ActiveState':'inactive','PrivateNetwork':'no' if values['DROP'].exists() else 'yes','User':'msp-reports','Group':'msp-reports','DropInPaths':str(values['DROP']) if values['DROP'].exists() else '', 'EnvironmentFiles':str(launcher.REDIS_ENV),'Restart':'no'}
        def command(args,**kwargs):commands.append(args);return b''
        def start(args,**kwargs):
            calls.append(args)
            (values['STATE']/'worker-output.json').write_text(json.dumps({'report_detail_complete':True,'executor':{'status':'DONE','send_entries':2},'rows':1,'pages':1,'http_dispatch_attempts_this_run':2,'http_response_statuses':[200,204]}))
            return type('Done',(),{'returncode':0})()
        real_mkdtemp=tempfile.mkdtemp
        def mktemp(**kwargs):return real_mkdtemp(prefix='program-',dir=self.root)
        with contextlib.ExitStack() as stack:
            for k,v in values.items():stack.enter_context(patch.object(launcher,k,v))
            for name,value in [('ASSETS',assets),('preflight',lambda:([],{})),('resolve_allowlist',lambda:['127.0.0.1/32']),('trusted',trust),('show',show),('run',command)]:stack.enter_context(patch.object(launcher,name,value))
            stack.enter_context(patch.object(os,'geteuid',return_value=0));stack.enter_context(patch.object(os,'fchown',return_value=None));stack.enter_context(patch.object(sys,'argv',['launch']))
            stack.enter_context(patch.object(tempfile,'mkdtemp',side_effect=mktemp));stack.enter_context(patch.object(launcher.subprocess,'run',side_effect=start))
            captured=io.StringIO()
            with contextlib.redirect_stdout(captured):rc=launcher.main()
            self.assertEqual(rc,0,captured.getvalue())
            self.assertEqual(len(calls),1);self.assertEqual(calls[0],['/usr/bin/systemctl','start','msp-wb-pilot.service'])
            self.assertFalse(values['APPROVAL'].exists());self.assertFalse(values['DROP_DIR'].exists())
            self.assertTrue((values['STATE']/'result.json').exists())
            with contextlib.redirect_stdout(io.StringIO()):self.assertEqual(launcher.main(),0)
            self.assertEqual(len(calls),1)
            self.assertFalse(any('enable' in cmd or 'restart' in cmd for cmd in commands))
    def test_active_foreign_controls_never_stopped(self):
        values=self.setup_scope();values['DROP_DIR'].mkdir();values['DROP'].write_bytes(b'changed');values['APPROVAL'].write_bytes(b'foreign')
        orig_trust=launcher.trusted
        with contextlib.ExitStack() as stack:
            for k,v in values.items():stack.enter_context(patch.object(launcher,k,v))
            stack.enter_context(patch.object(launcher,'trusted',side_effect=lambda p,uid=0,mode=None:orig_trust(p,uid=os.geteuid(),mode=mode)))
            stack.enter_context(patch.object(launcher,'show',return_value={'ActiveState':'active'}))
            command=stack.enter_context(patch.object(launcher,'run',side_effect=AssertionError('no stop allowed')))
            with self.assertRaises(ValueError):launcher.cleanup({'approval_sha256':'unrelated','dropin_sha256':'unrelated'},stop=True)
            self.assertEqual(command.call_count,0)

if __name__=='__main__':unittest.main()
