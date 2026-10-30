"""Synthetic WB resume tests; never import credentials or use HTTP/Redis."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.msp_marketplace_reports.generation_store import GenerationError
from apps.msp_marketplace_reports.providers import ProviderError
from apps.msp_marketplace_reports.wb_page_resume import (
    step_wb_detail, read_completed_wb_pages,
)


class WBPageResumeTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name) / "reports"
        self.cabinet = "wb_laser_master"
        self.report_id = 555
        self.year = 2026
        self.kind = 1

    def step(self, send, fault=None):
        return step_wb_detail(self.root, self.cabinet, self.year,
                              self.report_id, self.kind, send, fault=fault)

    def folder(self):
        return (self.root / ".wb-report-stage" / self.cabinet /
                str(self.year) / (str(self.report_id) + "-type-" + str(self.kind)))

    def test_two_pages_busy_and_resume_from_last_saved_cursor(self):
        calls = []
        responses = iter([
            (200, [{"reportId": 555, "rrdId": 10, "reportType": 1,
                    "amount": "SENSITIVE_1900"}]),
            (429, None),
            (200, [{"reportId": 555, "rrdId": 20, "reportType": 1,
                    "amount": "SENSITIVE_2900"}]),
            (204, None),
        ])
        def send(request):
            calls.append(request.body["rrdId"])
            return next(responses)
        self.assertEqual(self.step(send)["cursor"], 10)
        waiting = self.step(send)
        self.assertEqual(waiting["status"], "WAITING_RATE_LIMIT")
        self.assertEqual(waiting["current_rrd_id"], 10)
        new = self.step(send)
        self.assertEqual(new["cursor"], 20)
        done = self.step(send)
        self.assertEqual(done["status"], "STAGED_COMPLETE")
        self.assertFalse(done["provider_coverage_proven"])
        self.assertEqual(calls, [0, 10, 10, 20])
        payloads = list(read_completed_wb_pages(self.root, self.cabinet,
                                                self.year, self.report_id, self.kind))
        self.assertEqual(len(payloads), 2)
        self.assertEqual([p[0]["rrdId"] for p in payloads], [10, 20])
        self.assertFalse(self.step(lambda _: (_ for _ in ()).throw(
            AssertionError("must not call provider on completed stage")))["provider_coverage_proven"])

    def test_crash_after_page_fsync_before_state_does_not_refetch(self):
        sent = []
        def send(req):
            sent.append(req.body["rrdId"])
            return 200, [{"reportId": 555, "rrdId": 7, "reportType": 1}]
        def crash(stage):
            if stage == "after_page_fsync_before_state":
                raise OSError("SIGKILL-like lost process after durable page")
        with self.assertRaisesRegex(OSError, "SIGKILL-like"):
            self.step(send, fault=crash)
        state = json.loads((self.folder() / "state.json").read_text())
        self.assertEqual(state["current_rrd_id"], 0)
        replay = self.step(lambda req: (_ for _ in ()).throw(
            AssertionError("must replay page without API")))
        self.assertEqual(replay["cursor"], 7)
        self.assertTrue(replay["replayed_after_interruption"])
        self.assertEqual(replay["provider_calls"], 0)
        self.assertEqual(sent, [0])
        self.assertEqual(self.step(lambda req: (204, None))["status"], "STAGED_COMPLETE")

    def test_pending_page_tamper_rejected_before_cursor_ack(self):
        def crash(_):
            raise OSError("interrupted before state commit")
        with self.assertRaises(OSError):
            self.step(lambda _: (200, [{"reportId": 555, "rrdId": 10,
                                        "reportType": 1, "amount": "10"}]), fault=crash)
        staged = self.folder() / "page-0.json"
        value = json.loads(staged.read_bytes())
        self.assertEqual(value["rows"][0]["amount"], "10")
        self.assertEqual(len(value["payload_sha256"]), 64)
        value["rows"][0]["amount"] = "99"
        staged.write_text(json.dumps(value), encoding="utf-8")
        state = self.folder() / "state.json"
        saved = state.read_bytes()
        with self.assertRaisesRegex(GenerationError, "payload checksum mismatch"):
            self.step(lambda _: (_ for _ in ()).throw(AssertionError("no HTTP on corrupt page")))
        self.assertEqual(state.read_bytes(), saved)
        self.assertEqual(json.loads(state.read_bytes())["current_rrd_id"], 0)

    def test_pending_page_whitespace_replay_uses_raw_file_hash(self):
        def crash(_):
            raise OSError("interrupted before state commit")
        with self.assertRaises(OSError):
            self.step(lambda _: (200, [{"reportId": 555, "rrdId": 10,
                                        "reportType": 1}]), fault=crash)
        staged = self.folder() / "page-0.json"
        staged.write_bytes(b"  " + staged.read_bytes())
        resumed = self.step(lambda _: (_ for _ in ()).throw(
            AssertionError("pending page must replay without HTTP")))
        self.assertTrue(resumed["replayed_after_interruption"])
        self.assertEqual(self.step(lambda _: (204, None))["status"], "STAGED_COMPLETE")
        pages = list(read_completed_wb_pages(self.root, self.cabinet,
                                             self.year, self.report_id, self.kind))
        self.assertEqual(pages[0][0]["rrdId"], 10)

    def test_oversize_serialized_page_rejected_before_stage_write(self):
        with patch("apps.msp_marketplace_reports.wb_page_resume.MAX_STAGE_BYTES", 4096):
            with self.assertRaisesRegex(ProviderError, "staging size limit"):
                self.step(lambda request: (200, [{
                    "reportId": 555, "rrdId": 10, "reportType": 1,
                    "amount": "x" * 5000,
                }]))
            self.assertFalse((self.folder() / "page-0.json").exists())
            state = json.loads((self.folder() / "state.json").read_bytes())
            self.assertEqual(state["current_rrd_id"], 0)
            result = self.step(lambda request: (200, [{
                "reportId": 555, "rrdId": 10, "reportType": 1,
            }]))
            self.assertEqual(result["cursor"], 10)
            self.assertFalse(result["replayed_after_interruption"])

    def test_page_request_uses_bounded_provider_batch(self):
        requests = []
        def send(request):
            requests.append(request.body)
            return 200, [{"reportId": 555, "rrdId": 1, "reportType": 1}]
        self.step(send)
        self.assertEqual(requests, [{"limit": 1000, "rrdId": 0}])

    def test_busy_error_leaves_cursor_unchanged_and_persisted(self):
        self.step(lambda _: (200, [{"reportId": 555, "rrdId": 10, "reportType": 1}]))
        def busy(_):
            raise ProviderError("API DOWNLOAD PAUSED: shared quota busy; retry later")
        result = self.step(busy)
        self.assertEqual(result["status"], "WAITING_RATE_LIMIT")
        self.assertEqual(result["current_rrd_id"], 10)
        self.assertEqual(json.loads((self.folder() / "state.json").read_text())
                         ["current_rrd_id"], 10)

    def test_corrupt_state_schema_and_page_bytes_rejected(self):
        self.step(lambda _: (200, [{"reportId": 555, "rrdId": 10, "reportType": 1}]))
        state = self.folder() / "state.json"
        original = state.read_bytes()
        data = json.loads(original)
        data["schema"] = True
        broken = json.dumps(data).encode()
        state.write_bytes(broken)
        with self.assertRaisesRegex(GenerationError, "state"):
            self.step(lambda _: (_ for _ in ()).throw(AssertionError("no API")))
        self.assertEqual(state.read_bytes(), broken)
        state.write_bytes(original)
        page = self.folder() / "page-0.json"
        page.write_bytes(b'{"schema":true}')
        with self.assertRaises(GenerationError):
            self.step(lambda _: (_ for _ in ()).throw(AssertionError("no API")))

    def test_invalid_provider_page_never_advances_cursor(self):
        with self.assertRaisesRegex(GenerationError, "report type mismatch"):
            self.step(lambda _: (200, [{"reportId": 555, "rrdId": 1,
                                        "reportType": 2}]))
        self.assertFalse((self.folder() / "page-0.json").exists())
        state = json.loads((self.folder() / "state.json").read_text())
        self.assertEqual(state["current_rrd_id"], 0)

    def test_204_empty_does_not_mark_staged_complete(self):
        with self.assertRaisesRegex(ProviderError, "empty WB report"):
            self.step(lambda _: (204, None))
        self.assertEqual(json.loads((self.folder() / "state.json").read_text())
                         ["status"], "QUEUED")

    def test_symlink_staging_directory_rejected_without_outside_writes(self):
        parent = self.folder().parent
        parent.mkdir(parents=True)
        outside = Path(self.root.parent) / "external-finance"
        outside.mkdir()
        self.folder().symlink_to(outside, target_is_directory=True)
        with self.assertRaises(GenerationError):
            self.step(lambda _: (_ for _ in ()).throw(AssertionError("no API")))
        self.assertEqual(list(outside.iterdir()), [])

    def test_financial_stage_private_permissions(self):
        self.step(lambda _: (200, [{"reportId": 555, "rrdId": 1, "reportType": 1}]))
        for directory in (self.root / ".wb-report-stage",
                          self.root / ".wb-report-stage" / self.cabinet,
                          self.folder().parent, self.folder()):
            self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
        for file in self.folder().glob("*.json"):
            self.assertEqual(file.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
