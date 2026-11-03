"""Recovery refuses ambiguity and never rewrites old budget/evidence."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from apps.msp_marketplace_reports import standalone_wb as s
from apps.msp_marketplace_reports.wb_page_resume import _dir
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('recovery_guard',ROOT/'scripts/wb_live_pilot/recovery_guard.py')
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
PLAN={'schema':1,'cabinet':'wb_laser_master','year':2026,'report_id':883801632,'report_type':1,'max_send_entries':3}

class Recovery(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR',str(ROOT)));self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.old=self.root/'old';self.old.mkdir();self.archive=self.root/'archive';self.archive.mkdir()
        self.program=self.root/'msp-wb-E-program-fixture';self.program.mkdir();self.runner=self.program/'runner.py';self.runner.write_bytes(b'old-fixture')
        self.public=self.root/'public.json'
        self.failure={'status':'FAIL','worker_exit':1,'api_enabled_after_run':False,'outcome':{'error_type':'PermissionError','wrapper_status':'STOP_OR_UNCERTAIN'}}
        for p,v in [(self.old/'result.json',self.failure),(self.public,self.failure),(self.old/'worker-output.json',self.failure['outcome']),(self.old/'controls.json',{'runner_path':str(self.runner)})]:p.write_text(json.dumps(v))
        (self.old/'worker-stderr.txt').write_text('never disclose private details')
        self.budget=self.archive/'.wb-executor'/(s._digest(PLAN)+'.json');self.budget.parent.mkdir()
    def inspect(self):
        return g.inspect_failure(old_state=self.old,old_public=self.public,archive=self.archive,evidence_uid=os.geteuid(),archive_uid=os.geteuid(),old_runner_sha=hashlib.sha256(self.runner.read_bytes()).hexdigest(),program_parent=self.root)
    def save_budget(self,n=2):
        v={'schema':1,'plan_sha256':s._digest(PLAN),'send_entries':n,'status':'PAGE_STAGED'}
        self.budget.write_text(json.dumps({**v,'state_sha256':s._digest(v)}))
    def test_no_budget_or_http_evidence_does_not_create_any_state(self):
        result=self.inspect();self.assertEqual(result['budget_entries_before_resume'],0)
        self.assertEqual(result['http_dispatch_attempts_observed_before_resume'],0);self.assertFalse(self.budget.exists())
        self.assertNotIn('private details',json.dumps(result));self.assertFalse(result['historical_exception_path_recorded'])
    def test_existing_budget_events_are_read_only_and_cumulative(self):
        self.save_budget(2);event=self.budget.parent/'E-883801632-events.jsonl';event.write_text('{"event":"HTTP_DISPATCH_ATTEMPT"}\n')
        before=self.budget.read_bytes();out=self.inspect()
        self.assertEqual(out['budget_entries_before_resume'],2);self.assertEqual(out['http_dispatch_attempts_observed_before_resume'],1)
        g.assert_preserved(out['snapshots'],archive_uid=os.geteuid());self.assertEqual(before,self.budget.read_bytes())
        event.write_text(event.read_text()+'{}\n')
        with self.assertRaisesRegex(ValueError,'changed'):g.assert_preserved(out['snapshots'],archive_uid=os.geteuid())
    def test_bad_budget_seal_stops_without_repair(self):
        self.save_budget();self.budget.write_text(self.budget.read_text().replace('"send_entries": 2','"send_entries": 0'));before=self.budget.read_bytes()
        with self.assertRaisesRegex(ValueError,'budget'):self.inspect()
        self.assertEqual(before,self.budget.read_bytes())
    def test_http_evidence_without_budget_is_not_zero(self):
        (self.budget.parent/'E-883801632-events.jsonl').write_text('{"event":"HTTP_DISPATCH_ATTEMPT"}\n')
        with self.assertRaisesRegex(ValueError,'without budget'):self.inspect()
    def test_orphan_page_refuses_fresh_cursor(self):
        folder=_dir(self.archive,'wb_laser_master',2026,883801632,1);folder.mkdir(parents=True);(folder/'page-0.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'orphan'):self.inspect()
    def test_different_private_failure_refuses_replay(self):
        doc=dict(self.failure,worker_exit=2);(self.old/'result.json').write_text(json.dumps(doc))
        with self.assertRaisesRegex(ValueError,'different failure'):self.inspect()
    def test_original_runner_changed_stops(self):
        self.runner.write_text('changed')
        with self.assertRaisesRegex(ValueError,'source differs'):
            g.inspect_failure(old_state=self.old,old_public=self.public,archive=self.archive,evidence_uid=os.geteuid(),archive_uid=os.geteuid(),old_runner_sha=hashlib.sha256(b'old-fixture').hexdigest(),program_parent=self.root)
    def test_symlink_budget_refused(self):
        other=self.root/'elsewhere';other.write_text('{}');self.budget.symlink_to(other)
        with self.assertRaises(Exception):self.inspect()
