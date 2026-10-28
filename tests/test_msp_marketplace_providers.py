"""Offline contract tests using mock responses; no token or network."""
import unittest
from datetime import date

from apps.msp_marketplace_reports.providers import (
    ProviderError, wb_discover_main, wb_discover_all, wb_detail, ozon_final_month,
    ozon_current_postings, ozon_accrual_day,
    WB_LIST, WB_DETAIL, OZON_FBO, OZON_FBS, OZON_ACCRUAL, OZON_FINAL,
)


def scripted(pairs):
    requests = []
    answers = iter(pairs)

    def send(request):
        requests.append(request)
        return next(answers)

    return send, requests


class WBContractTests(unittest.TestCase):
    def test_discovery_two_fragments_same_week(self):
        send, calls = scripted([(200, [
            {"reportId": 833903021, "dateFrom": "2026-08-31", "dateTo": "2026-08-31", "reportType": 1},
            {"reportId": 836274098, "dateFrom": "2026-09-01", "dateTo": "2026-09-06", "reportType": 1},
            {"reportId": 123, "dateFrom": "2026-09-01", "dateTo": "2026-09-06", "reportType": 2},
        ])])
        rows = wb_discover_main(send, 2026, date(2026, 10, 28))
        self.assertEqual(len(rows), 2)
        self.assertEqual(calls[0].path, WB_LIST)
        self.assertEqual(calls[0].body["period"], "weekly")

    def test_discovery_all_types_preserves_buyouts(self):
        send, calls = scripted([(200, [
            {"reportId": 1001, "dateFrom": "2026-10-05", "dateTo": "2026-10-11", "reportType": 1},
            {"reportId": 1002, "dateFrom": "2026-10-05", "dateTo": "2026-10-11", "reportType": 2},
        ])])
        reports = wb_discover_all(send, 2026, date(2026, 10, 28))
        self.assertEqual([(x["reportId"], x["reportType"]) for x in reports], [(1001, 1), (1002, 2)])
        self.assertEqual(len(calls), 1)

    def test_discovery_rejects_unknown_type(self):
        send, _ = scripted([(200, [
            {"reportId": 1003, "dateFrom": "2026-10-05", "dateTo": "2026-10-11", "reportType": 3}
        ])])
        with self.assertRaisesRegex(ProviderError, "unsupported WB report type"):
            wb_discover_all(send, 2026, date(2026, 10, 28))

    def test_wb_buyout_detail_and_wrong_type(self):
        send, _ = scripted([
            (200, [{"reportId": 77, "rrdId": 33, "reportType": 2}]),
            (204, None),
        ])
        self.assertEqual(len(wb_detail(send, 77, report_type=2)), 1)
        send_bad, _ = scripted([
            (200, [{"reportId": 77, "rrdId": 33, "reportType": 1}]),
        ])
        with self.assertRaisesRegex(ProviderError, "mismatches list"):
            wb_detail(send_bad, 77, report_type=2)

    def test_wb_detail_until_204(self):
        send, calls = scripted([
            (200, [{"reportId": 42, "rrdId": 1, "reportType": 1}]),
            (200, [{"reportId": 42, "rrdId": 3, "reportType": 1}]),
            (204, None),
        ])
        self.assertEqual(len(wb_detail(send, 42)), 2)
        self.assertEqual([r.body["rrdId"] for r in calls], [0, 1, 3])
        self.assertTrue(calls[0].path.startswith(WB_DETAIL))

    def test_wb_429_does_not_commit_partial(self):
        send, _ = scripted([
            (200, [{"reportId": 42, "rrdId": 1}]),
            (429, {"secret": "must not surface"}),
        ])
        with self.assertRaisesRegex(ProviderError, "rate limit") as ctx:
            wb_detail(send, 42)
        self.assertNotIn("must not surface", str(ctx.exception))

    def test_wb_ambiguous_empty_200_fails(self):
        send, _ = scripted([(200, [])])
        with self.assertRaises(ProviderError):
            wb_detail(send, 42)

    def test_wb_stuck_rrd_id_fails(self):
        send, _ = scripted([
            (200, [{"rrdId": 10}]),
            (200, [{"rrdId": 10}]),
        ])
        with self.assertRaises(ProviderError):
            wb_detail(send, 42)


class OzonContractTests(unittest.TestCase):
    def test_final_closed_month(self):
        send, calls = scripted([(200, {"rows": [{"row_number": 2, "item": {"sku": 42}}]})])
        rows = ozon_final_month(send, 2026, 9)
        self.assertEqual(rows[0]["report_month"], "2026-09")
        self.assertEqual(calls[0].path, OZON_FINAL)
        self.assertEqual(calls[0].body, {"year": 2026, "month": 9})

    def test_final_missing_rows_is_not_empty_month(self):
        send, _ = scripted([(200, {"result": {}})])
        with self.assertRaises(ProviderError):
            ozon_final_month(send, 2026, 9)

    def test_fbs_cursor_without_result_wrapper(self):
        send, calls = scripted([
            (200, {"postings": [{"posting_number": "A"}], "cursor": "cursor-one", "has_next": True}),
            (200, {"postings": [{"posting_number": "B"}], "has_next": False}),
        ])
        rows = ozon_current_postings(send, "fbs", date(2026, 10, 1), date(2026, 10, 28))
        self.assertEqual(len(rows), 2)
        self.assertEqual([r.path for r in calls], [OZON_FBS, OZON_FBS])
        self.assertEqual(calls[1].body["cursor"], "cursor-one")
        self.assertEqual(calls[0].body["filter"]["since"], "2026-09-30T21:00:00Z")

    def test_fbo_duplication_fails(self):
        send, _ = scripted([
            (200, {"postings": [{"posting_number": "A"}], "cursor": "xx", "has_next": True}),
            (200, {"postings": [{"posting_number": "A"}], "has_next": False}),
        ])
        with self.assertRaises(ProviderError):
            ozon_current_postings(send, "fbo", date(2026, 10, 1), date(2026, 10, 28))

    def test_fbo_cursor_unchanged_fails(self):
        send, _ = scripted([
            (200, {"postings": [{"posting_number": "A"}], "cursor": "xx", "has_next": True}),
            (200, {"postings": [{"posting_number": "B"}], "cursor": "xx", "has_next": True}),
        ])
        with self.assertRaises(ProviderError):
            ozon_current_postings(send, "fbo", date(2026, 10, 1), date(2026, 10, 28))

    def test_accrual_last_id(self):
        send, calls = scripted([
            (200, {"accruals": [{"accrual_id": "1"}], "last_id": "first"}),
            (200, {"accruals": [{"accrual_id": "2"}], "last_id": ""}),
        ])
        rows = ozon_accrual_day(send, date(2026, 10, 28))
        self.assertEqual(len(rows), 2)
        self.assertEqual(calls[0].path, OZON_ACCRUAL)
        self.assertEqual(calls[1].body["last_id"], "first")

    def test_accrual_ambiguous_page_fails(self):
        send, _ = scripted([(200, {"accruals": [], "last_id": "nonempty"})])
        with self.assertRaises(ProviderError):
            ozon_accrual_day(send, date(2026, 10, 28))


if __name__ == "__main__":
    unittest.main()
