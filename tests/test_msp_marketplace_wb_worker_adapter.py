"""Synthetic WB wiring, no network, Redis, credentials or installed worker."""
import asyncio
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apps.msp_marketplace_reports.quota import QuotaBusy
from apps.msp_marketplace_reports.generation_store import read_active
from apps.msp_marketplace_reports.versioned_archive import read_csv_versioned
from apps.msp_marketplace_reports import wb_worker_adapter as worker


class WBWorkerWiringTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "reports"
        self.cabinet = "wb_laser_master"
        self.year = 2026
        self.report_id = 555

    def invoke(self, kind, sender, fault=None):
        return worker.run_one_step(self.root, self.cabinet, self.year,
                                   self.report_id, kind, sender, fault=fault)

    @staticmethod
    def page(kind, cursor, extra=False):
        row = {"reportId": 555, "rrdId": cursor, "reportType": kind,
               "dateFrom": "2026-10-19", "dateTo": "2026-10-25",
               "amount": str(cursor)}
        if extra:
            row["extra_finance_field"] = "second_page_preserved"
        return row

    def populate(self, kind):
        calls = []
        state = {"blocked": False}
        def sender(req):
            cursor = req.body["rrdId"]
            calls.append(cursor)
            if cursor == 0:
                return 200, [self.page(kind, 10)]
            if cursor == 10 and not state["blocked"]:
                state["blocked"] = True
                raise QuotaBusy(180, "shared quota busy")
            if cursor == 10:
                return 200, [self.page(kind, 20, extra=True)]
            if cursor == 20:
                return 204, None
            raise AssertionError("unexpected request cursor")

        first = self.invoke(kind, sender)
        self.assertEqual(first["cursor"], 10)
        paused = self.invoke(kind, sender)
        self.assertEqual(paused["status"], "WAITING_RATE_LIMIT")
        self.assertEqual(paused["retry_after_seconds"], 180.0)
        self.assertTrue(paused["not_before_utc"].endswith("+00:00"))
        self.assertEqual(paused["provider_calls"], 0)
        self.assertEqual(self.invoke(kind, sender)["cursor"], 20)
        result = self.invoke(kind, sender)
        self.assertEqual(result["status"], "LOCAL_VERIFIED_NOT_PROVIDER_COMPLETE")
        self.assertEqual(result["rows"], 2)
        self.assertFalse(result["provider_coverage_proven"])
        self.assertEqual(calls, [0, 10, 10, 20])
        return result, calls

    def test_main_and_buyout_two_pages_publish_and_no_refetch(self):
        for kind in (1, 2):
            with self.subTest(kind=kind):
                result, calls = self.populate(kind)
                dataset = worker._dataset(kind)
                raw, pin = read_csv_versioned(
                    self.root, dataset, self.cabinet, "2026",
                    pinned_generation=result["generation"],
                    expected_digest=result["manifest_sha256"])
                rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig")),
                                           delimiter=";"))
                self.assertEqual(len(rows), 2)
                self.assertEqual(set(rows[1]), set(rows[0]))
                self.assertEqual(rows[1]["extra_finance_field"], "second_page_preserved")
                self.assertEqual(json.loads(rows[1]["_raw_json"])["rrdId"], 20)
                self.assertEqual(pin["generation"], result["generation"])
                reused = self.invoke(kind, lambda _: (_ for _ in ()).throw(
                    AssertionError("coverage already committed; no HTTP")))
                self.assertEqual(reused["generation"], result["generation"])
                self.assertFalse(reused["changed"])
                self.assertEqual(calls, [0, 10, 10, 20])

    def test_lost_response_after_publication_retries_without_new_generation(self):
        kind = 1
        sender = iter([
            (200, [self.page(kind, 10)]),
            (204, None),
        ])
        self.invoke(kind, lambda _: next(sender))
        real = worker.import_csv_versioned
        def lost_response(*args, **kwargs):
            real(*args, **kwargs)
            raise OSError("synthetic response lost after CURRENT commit")
        with patch.object(worker, "import_csv_versioned", lost_response):
            with self.assertRaisesRegex(OSError, "response lost"):
                self.invoke(kind, lambda _: next(sender))
        dataset = worker._dataset(kind)
        first = read_active(self.root, dataset, self.cabinet, "2026")["generation"]
        done = self.invoke(kind, lambda _: (_ for _ in ()).throw(
            AssertionError("must never refetch complete staged pages")))
        self.assertEqual(done["generation"], first)
        self.assertEqual(read_active(self.root, dataset, self.cabinet,
                                     "2026")["generation"], first)

    def test_after_publication_before_coverage_retry_is_idempotent(self):
        kind = 2
        self.invoke(kind, lambda _: (200, [self.page(kind, 10)]))
        def stop(label):
            if label == "after_publication_before_coverage":
                raise OSError("synthetic crash before coverage")
        with self.assertRaisesRegex(OSError, "before coverage"):
            self.invoke(kind, lambda _: (204, None), fault=stop)
        dataset = worker._dataset(kind)
        first = read_active(self.root, dataset, self.cabinet, "2026")["generation"]
        done = self.invoke(kind, lambda _: (_ for _ in ()).throw(
            AssertionError("no HTTP when staged complete")))
        self.assertEqual(first, done["generation"])
        self.assertFalse(done["changed"])

    def test_async_worker_thread_calls_only_one_sender_per_step(self):
        kind = 1
        calls = []
        def send(req):
            calls.append(req.body["rrdId"])
            return (200, [self.page(kind, 10)]) if len(calls) == 1 else (204, None)
        async def drive():
            first = await asyncio.to_thread(self.invoke, kind, send)
            second = await asyncio.to_thread(self.invoke, kind, send)
            return first, second
        first, second = asyncio.run(drive())
        self.assertEqual(first["cursor"], 10)
        self.assertEqual(second["rows"], 1)
        self.assertEqual(calls, [0, 10])


if __name__ == "__main__":
    unittest.main()
