"""Exercise the exact old queue persistence interface using an offline fixture."""
import asyncio
import copy
import tempfile
import unittest
from pathlib import Path
from apps.msp_marketplace_reports.existing_worker_bridge import step_existing_job, MODE, SELECTION
from apps.msp_marketplace_reports.quota import QuotaBusy
from apps.msp_marketplace_reports.generation_store import GenerationError

class QueueFixture:
    def __init__(self):
        self.saved = []
        self.scheduled = []
        self.unscheduled = []
        self.fail_save = False
    async def _save(self, state):
        if self.fail_save:
            raise OSError('synthetic job-store failure')
        self.saved.append(copy.deepcopy(state))
    async def _schedule(self, job, delay=0):
        self.scheduled.append((job, delay))
    async def _unschedule(self, job):
        self.unscheduled.append(job)

def job(kind=1):
    return dict(job_id='synthetic-existing-job', archive_mode=MODE, selection_contract=SELECTION,
                phase='DOWNLOAD', status='QUEUED', cabinet='wb_laser_master', year=2026,
                fragments=[dict(report_id=555, report_type=kind)], report_index=0)

def row(kind=1):
    return dict(reportId=555, reportType=kind, rrdId=10, dateTo='2026-10-25', amount='10')

class ExistingWorkerBridgeTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name) / 'archive'
    def step(self, queue, state, send):
        return asyncio.run(step_existing_job(queue, state, root=self.root, send=send))
    def test_one_step_wait_preserves_cursor_and_persists_not_before(self):
        q = QueueFixture()
        state = job()
        self.step(q, state, lambda req: (200, [row()]))
        calls = []
        def busy(req):
            calls.append(req.body['rrdId'])
            raise QuotaBusy(180)
        result = self.step(q, state, busy)
        self.assertEqual(calls, [10])
        self.assertEqual(result['provider_calls'], 0)
        self.assertEqual(q.saved[-1]['status'], 'WAITING_RATE_LIMIT')
        self.assertGreaterEqual(q.scheduled[-1][1], 180)
        self.assertIn('not_before_utc', q.saved[-1])
        self.assertNotIn('current_rrd_id', state)
    def test_main_buyout_same_id_and_verified_unit_before_unschedule(self):
        q = QueueFixture()
        state = job()
        state['fragments'].append(dict(report_id=555, report_type=2))
        seen = []
        for kind in (1, 2):
            def send(req):
                seen.append(req.body['rrdId'])
                return (200, [row(kind)]) if req.body['rrdId'] == 0 else (204, None)
            self.step(q, state, send)
            self.step(q, state, send)
        self.assertEqual(seen, [0, 10, 0, 10])
        self.assertEqual(len(state['verified_report_units']), 2)
        self.assertEqual(state['report_index'], 2)
        self.assertEqual(state['status'], 'COMPLETE')
        self.assertEqual(q.unscheduled, [state['job_id']])
    def test_job_save_failure_after_archive_commit_retries_without_provider(self):
        q = QueueFixture()
        state = job()
        self.step(q, state, lambda req: (200, [row()]))
        durable = copy.deepcopy(q.saved[-1])
        q.fail_save = True
        with self.assertRaises(OSError):
            self.step(q, state, lambda req: (204, None))
        q.fail_save = False
        done = self.step(q, durable, lambda req: self.fail('must not refetch'))
        self.assertEqual(done['job_status'], 'COMPLETE')
        self.assertEqual(q.saved[-1]['report_index'], 1)
    def test_legacy_or_unapproved_job_refused_before_provider(self):
        for key, value in [('archive_mode', 'legacy'), ('selection_contract', 'old-main-only'),
                           ('current_rrd_id', 5), ('finalize', {'phase': 'COMMIT'})]:
            state = job()
            state[key] = value
            with self.subTest(key=key), self.assertRaises(GenerationError):
                self.step(QueueFixture(), state, lambda req: self.fail('no HTTP'))
