"""Real identifier sequences, synthetic business payloads; no provider I/O."""
import json
import tempfile
import unittest
from pathlib import Path
from apps.msp_marketplace_reports import wb_page_resume as p
from apps.msp_marketplace_reports.wb_worker_adapter import run_one_step
from apps.msp_marketplace_reports.generation_store import GenerationError

ROOT = Path(__file__).resolve().parents[1]
CAB = 'wb_laser_master'
RID = 601780521

def row(i):
    return {'reportId': RID, 'reportType': 1, 'rrdId': i, 'amount': 'SYNTHETIC'}

class ChunkPolicy(unittest.TestCase):
    def test_actual_third_page_with_lower_new_ids_continues_to_explicit_terminal(self):
        second = json.loads((ROOT/'tests/fixtures/wb_601780521_rrd_ids.json').read_text())
        third = json.loads((ROOT/'tests/fixtures/wb_601780521_third_rrd_ids.json').read_text())
        answers = iter([(200, [row(second['cursor'])]),
                        (200, [row(i) for i in second['ids']]),
                        (200, [row(i) for i in third['ids']]), (204, None)])
        calls = []
        def send(req):
            calls.append(req.body)
            return next(answers)
        with tempfile.TemporaryDirectory() as tmp:
            for _ in range(3):
                staged = run_one_step(Path(tmp), CAB, 2026, RID, 1, send)
                self.assertEqual(staged['status'], 'PAGE_STAGED')
            self.assertLess(third['ids'][-1], third['cursor'])
            done = run_one_step(Path(tmp), CAB, 2026, RID, 1, send)
            self.assertEqual(done['rows'], len({second['cursor'], *second['ids'], *third['ids']}))
            self.assertEqual([c['rrdId'] for c in calls], [0, second['cursor'], third['cursor'], third['ids'][-1]])
            self.assertTrue(all(c['limit'] == 1000 for c in calls))

    def test_cursor_cycle_is_retained_but_never_acknowledged_or_refetched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for rows in ([row(30)], [row(20)]):
                p.step_wb_detail(root, CAB, 2026, RID, 1, lambda req: (200, rows))
            folder=p._dir(root,CAB,2026,RID,1)
            saved=(folder/'state.json').read_bytes()
            with self.assertRaisesRegex(GenerationError, 'cycle'):
                p.step_wb_detail(root,CAB,2026,RID,1,lambda req:(200,[row(31),row(30)]))
            self.assertEqual((folder/'state.json').read_bytes(),saved)
            self.assertTrue((folder/'response-20.json').exists())
            with self.assertRaisesRegex(GenerationError, 'cycle'):
                p.step_wb_detail(root,CAB,2026,RID,1,lambda req:self.fail('no refetch'))

    def test_lower_identifier_conflict_is_not_hidden_by_relaxed_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            p.step_wb_detail(root,CAB,2026,RID,1,lambda req:(200,[row(10),row(30)]))
            folder=p._dir(root,CAB,2026,RID,1);saved=(folder/'state.json').read_bytes()
            with self.assertRaisesRegex(GenerationError,'conflicting'):
                p.step_wb_detail(root,CAB,2026,RID,1,lambda req:(200,[{**row(10),'amount':'CHANGED'},row(20)]))
            self.assertEqual((folder/'state.json').read_bytes(),saved)

    def test_lower_page_replays_after_crash_without_transport(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            p.step_wb_detail(root,CAB,2026,RID,1,lambda req:(200,[row(30)]))
            def crash(stage):
                raise OSError('simulated interruption')
            with self.assertRaises(OSError):
                p.step_wb_detail(root,CAB,2026,RID,1,lambda req:(200,[row(20)]),fault=crash)
            result=p.step_wb_detail(root,CAB,2026,RID,1,lambda req:self.fail('replay only'))
            self.assertEqual(result['cursor'],20);self.assertEqual(result['provider_calls'],0)
            self.assertEqual(p.step_wb_detail(root,CAB,2026,RID,1,lambda req:(204,None))['status'],'STAGED_COMPLETE')

    def test_worker_persists_seventy_second_page_pause_without_resetting_counter(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('apps.msp_marketplace_reports.chunk_overlay',ROOT/'scripts/finance_control/overlays/standalone_wb.py')
        s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
        plan={'schema':1,'cabinet':CAB,'year':2026,'report_id':RID,'report_type':1,'max_send_entries':3}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);calls=[]
            auth={'schema':1,'plan_sha256':s._digest(plan),'code_sha256':s.code_digest(),'archive_root':str(root),'expires_epoch':9999999999,'owner_api_pilot_authorized':True,'shared_quota_verified':True,'conflicting_clients_excluded':True,'evidence_reference':'OFFLINE_CHUNK_POLICY'}
            def sender(req):
                calls.append(req.body['rrdId'])
                return (200,[row(30)]) if len(calls)==1 else (204,None)
            first=s.run_step(root,plan,auth,lambda:sender,now=1000.)
            self.assertGreaterEqual(first['not_before_epoch'],1070.)
            waiting=s.run_step(root,plan,auth,lambda:sender,now=1069.)
            self.assertEqual(waiting['send_entries'],1);self.assertEqual(calls,[0])
            done=s.run_step(root,plan,auth,lambda:sender,now=1070.)
            self.assertEqual(done['status'],'DONE');self.assertEqual(done['send_entries'],2)
            self.assertEqual(calls,[0,30])

    def test_existing_four_entry_hold_replays_locally_before_next_admission(self):
        import importlib.util
        from unittest.mock import patch
        spec=importlib.util.spec_from_file_location('apps.msp_marketplace_reports.cursor_recovery_overlay',ROOT/'scripts/finance_control/overlays/standalone_wb.py')
        s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
        plan={'schema':1,'cabinet':CAB,'year':2026,'report_id':RID,'report_type':1,'max_send_entries':3}
        fixture=json.loads((ROOT/'tests/fixtures/wb_601780521_cursor_hold.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for rows in ([row(10)],[row(30)]):p.step_wb_detail(root,CAB,2026,RID,1,lambda req:(200,rows))
            folder=p._dir(root,CAB,2026,RID,1)
            pending={'schema':1,'report_id':RID,'report_type':1,'cursor':30,'next_rrd_id':20,'rows':[row(20)]}
            pending['payload_sha256']=p._sha(p._canonical(pending));raw=p._canonical(pending)
            (folder/'response-30.json').write_bytes(raw)
            ledger=root/'.wb-executor';ledger.mkdir()
            # Business payloads remain synthetic. Pin the exact fixture state shape.
            fixture.pop('local_response_replay');fixture.pop('processing_recovery')
            state_hash=s._digest(fixture)
            budget=ledger/(s._digest(plan)+'.json');budget.write_bytes(s._encode({**fixture,'state_sha256':state_hash}))
            (ledger/('control-'+32*'b'+'-events.jsonl')).write_text(''.join(json.dumps({'event':event,'plan':plan,**values})+'\n' for _ in range(4) for event,values in [('HTTP_DISPATCH_ATTEMPT',{}),('HTTP_RESPONSE',{'status':200})]))
            auth={'schema':1,'plan_sha256':s._digest(plan),'code_sha256':s.code_digest(),'archive_root':str(root),'expires_epoch':9999999999,'owner_api_pilot_authorized':True,'shared_quota_verified':True,'conflicting_clients_excluded':True,'evidence_reference':'OFFLINE_CURSOR_MIGRATION'}
            with patch.object(s,'CURSOR_HOLD_SHA256',state_hash), patch.object(s,'CURSOR_ROWS_PROFILE_SHA256',s._digest([{'rrdId':20,'row_sha256':s._digest(row(20))}])):
                # Recomputed envelope checksum must not authenticate changed financial data.
                changed={**pending,'rows':[{**row(20),'amount':'TAMPERED'}]};changed.pop('payload_sha256')
                changed['payload_sha256']=p._sha(p._canonical(changed));(folder/'response-30.json').write_bytes(p._canonical(changed))
                before=budget.read_bytes()
                with self.assertRaisesRegex(GenerationError,'protected diagnostic'):
                    s.run_step(root,plan,auth,lambda:self.fail('no HTTP on tamper'),now=1000,admission_ceiling=1000,policy_sha256='c'*64)
                self.assertEqual(budget.read_bytes(),before);(folder/'response-30.json').write_bytes(raw)
                out=s.run_step(root,plan,auth,lambda:self.fail('no sender during local replay'),now=1000,admission_ceiling=1000,policy_sha256='c'*64)
                self.assertEqual(out['status'],'PAGE_STAGED');self.assertEqual(out['send_entries'],4)
                self.assertEqual(p._read_json(folder/'state.json')['current_rrd_id'],20)
                self.assertEqual((folder/'response-30.json').read_bytes(),raw)
                # An interrupted replay must never turn a lost saved response into HTTP.
                (folder/'response-30.json').unlink()
                with self.assertRaises(GenerationError):
                    s.run_step(root,plan,auth,lambda:self.fail('no sender on lost evidence'),now=1070,admission_ceiling=1000,policy_sha256='c'*64)

    def test_diagnostic_separates_new_lower_ids_from_conflicting_overlaps(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('chunk_profile',ROOT/'scripts/finance_control/rrd_profile.py')
        profile=importlib.util.module_from_spec(spec);spec.loader.exec_module(profile)
        out=profile.analyze({'rows':[row(20),row(10),{**row(30),'amount':'CHANGED'}]},[[row(10),row(30)]],40)
        self.assertEqual(out['new_ids_below_cursor'],[20])
        self.assertEqual(out['conflicting_previous_ids'],[30])
        self.assertEqual(out['identical_previous_ids'],[10])

    def test_large_report_twelve_full_chunks_and_short_tail_require_terminal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);calls=[]
            def send(req):
                calls.append(req.body['rrdId'])
                start=req.body['rrdId'];end=min(start+req.body['limit'],12345)
                return (200,[row(i) for i in range(start+1,end+1)]) if start<12345 else (204,None)
            for number in range(13):
                out=p.step_wb_detail(root,CAB,2026,RID,1,send)
                self.assertEqual(out['status'],'PAGE_STAGED')
                self.assertLessEqual(out['rows_this_page'],1000)
                folder=p._dir(root,CAB,2026,RID,1);state=p._read_json(folder/'state.json')
                self.assertEqual(len(state['pages']),number+1)
                self.assertEqual(state['current_rrd_id'],min((number+1)*1000,12345))
            self.assertEqual(p._read_json(folder/'state.json')['status'],'RUNNING')
            self.assertEqual(p.step_wb_detail(root,CAB,2026,RID,1,send)['status'],'STAGED_COMPLETE')
            self.assertEqual(sum(len(page) for page in p.read_completed_wb_pages(root,CAB,2026,RID,1)),12345)
            self.assertEqual(calls[-1],12345)
