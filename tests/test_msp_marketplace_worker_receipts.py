"""Regression proofs for R99-1/R99-2. Synthetic only, no provider/Redis."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from apps.msp_marketplace_reports import archive as ar, generation_store as gs
from apps.msp_marketplace_reports import wb_worker_adapter as worker

class WorkerReceiptTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)

    def setup_report(self, name, kind):
        root = self.base / name / 'archive'
        root.parent.mkdir()
        invoke = lambda send: worker.run_one_step(root, 'wb_laser_master', 2026, 555, kind, send)
        invoke(lambda req: (200, [dict(reportId=555, reportType=kind, rrdId=10,
                                     dateTo='2026-10-25', amount='10')]))
        result = invoke(lambda req: (204, None))
        return root, invoke, result

    def test_coverage_pin_must_match_staged_values_not_just_count(self):
        for kind in (1, 2):
            for field in ('amount', '_raw_json'):
                with self.subTest(kind=kind, field=field):
                    root, invoke, receipt = self.setup_report(str(kind) + field, kind)
                    args = root, worker._dataset(kind), 'wb_laser_master', '2026'
                    active = gs.read_active(*args)
                    files = dict(active['files'])
                    fields, rows = ar._rows(files['data.csv'], ('reportId', 'rrdId'))
                    for row in rows.values():
                        row[field] = '99' if field == 'amount' else '{"amount":"99"}'
                    raw = ar._encode(fields, rows)
                    files['data.csv'] = raw
                    files['data.csv.meta.json'] = json.dumps(
                        ar._metadata(raw, len(rows), *args[1:])).encode()
                    changed = gs.publish_batch(*args, files, expected_generation=receipt['generation'])
                    path = worker._dir(root, 'wb_laser_master', 2026, 555, kind) / 'coverage.json'
                    doc = json.loads(path.read_bytes())
                    doc.update(generation=changed['generation'], manifest_sha256=changed['manifest_sha256'])
                    path.write_text(json.dumps(doc))
                    before = path.read_bytes()
                    with self.assertRaisesRegex(gs.GenerationError, 'staged rows'):
                        invoke(lambda req: self.fail('must not refetch'))
                    self.assertEqual(path.read_bytes(), before)

    def test_visible_coverage_retry_sync_errors_stay_uncertain(self):
        for target in ('file', 'directory'):
            with self.subTest(target=target):
                root, invoke, receipt = self.setup_report(target, 1)
                folder = worker._dir(root, 'wb_laser_master', 2026, 555, 1)
                path = folder / 'coverage.json'
                before = path.read_bytes()
                original = os.fsync
                hits = []
                def fail(fd):
                    name = os.readlink('/proc/self/fd/' + str(fd))
                    if name == str(path if target == 'file' else folder):
                        hits.append(name)
                        raise OSError(5, 'synthetic fsync error')
                    return original(fd)
                for attempt in range(2):
                    with patch.object(os, 'fsync', fail):
                        with self.assertRaises(worker.CoverageUncertainError):
                            invoke(lambda req: self.fail('no HTTP'))
                    self.assertEqual(path.read_bytes(), before)
                self.assertEqual(len(hits), 2)
                result = invoke(lambda req: self.fail('no HTTP'))
                self.assertEqual(result['generation'], receipt['generation'])
                self.assertEqual(path.read_bytes(), before)

    def test_successful_replay_fsyncs_without_rewriting_receipt(self):
        root, invoke, receipt = self.setup_report('repeat', 1)
        path = worker._dir(root, 'wb_laser_master', 2026, 555, 1) / 'coverage.json'
        before = path.read_bytes()
        original = os.fsync
        trace = []
        def track(fd):
            trace.append(os.readlink('/proc/self/fd/' + str(fd)))
            return original(fd)
        with patch.object(os, 'replace', side_effect=AssertionError('must not rewrite evidence')):
            with patch.object(os, 'fsync', track):
                result = invoke(lambda req: self.fail('no HTTP'))
        self.assertIn(str(path), trace)
        self.assertIn(str(path.parent), trace)
        self.assertFalse(result['changed'])
        self.assertEqual(path.read_bytes(), before)
