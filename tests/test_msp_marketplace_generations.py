"""B7 opt-in generation experiments: synthetic fixtures, no network or VPS."""
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path

from apps.msp_marketplace_reports.archive import _encode, _metadata
from apps.msp_marketplace_reports.generation_store import (
    CommitUncertainError, GenerationError, publish_batch, read_active,
    read_generation, reconcile,
)


def _fixture_meta(raw, count, dataset, cabinet, period):
    result = _metadata(raw, count, dataset, cabinet, period)
    # Deterministic synthetic inputs across clock boundaries: metadata time
    # must not affect comparison of otherwise identical file snapshots.
    result["updated_at_utc"] = "2026-10-29T00:00:00+00:00"
    return result


def wb_files(amount="10", *, dataset="wb_weekly_finance_main"):
    row = {"reportId": "11", "rrdId": "1", "reportType": "1"
           if dataset.endswith("_main") else "2", "amount": amount}
    raw = _encode(list(row), {("11", "1"): row})
    return {"data.csv": raw, "data.csv.meta.json": json.dumps(
        _fixture_meta(raw, 1, dataset, "wb_laser_master", "2026")).encode()}


def ozon_final_files(january="5", february=None):
    year = "2026"
    cabinet = "ozon_laser_master"
    source = {}
    all_rows = {}
    for month, qty in [("2026-01", january), ("2026-02", february)]:
        if qty is None:
            continue
        row = {"report_year": year, "report_month": month, "row_number": month[-2:],
               "qty": qty}
        all_rows[(year, month, month[-2:])] = row
        raw = _encode(list(row), {(year, month, month[-2:]): row})
        name = "monthly/" + month + ".csv"
        source[name] = raw
        source[name + ".meta.json"] = json.dumps(
            _fixture_meta(raw, 1, "ozon_final_realization", cabinet, month)).encode()
    annual_raw = _encode(["report_year", "report_month", "row_number", "qty"], all_rows)
    source["annual.csv"] = annual_raw
    source["annual.csv.meta.json"] = json.dumps(
        _fixture_meta(annual_raw, len(all_rows), "ozon_final_realization", cabinet, year)
    ).encode()
    return source


class GenerationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "archive"
        self.args = (self.root, "wb_weekly_finance_main", "wb_laser_master", "2026")

    def test_empty_reconcile_has_no_filesystem_side_effect(self):
        self.assertEqual(reconcile(*self.args),
                         {"status": "EMPTY", "uncommitted_generations": []})
        self.assertFalse(self.root.exists())

    def test_first_publish_and_pinned_reader(self):
        first = publish_batch(*self.args, wb_files())
        self.assertEqual(first["status"], "COMMITTED")
        old = read_active(*self.args)
        self.assertEqual(old["generation"], first["generation"])
        self.assertEqual(old["files"], wb_files())
        second = publish_batch(*self.args, wb_files("20"),
                               expected_generation=first["generation"])
        self.assertNotEqual(first["generation"], second["generation"])
        self.assertEqual(read_generation(*self.args, first["generation"], expected_digest=first["manifest_sha256"])["files"],
                         wb_files())
        self.assertEqual(read_active(*self.args)["files"], wb_files("20"))

    def test_commit_pointer_is_noop_for_identical_payload(self):
        first = publish_batch(*self.args, wb_files())
        second = publish_batch(*self.args, wb_files(), expected_generation=None)
        self.assertFalse(second["changed"])
        self.assertEqual(first["generation"], second["generation"])

    def test_precommit_crash_preserves_previous_committed_snapshot(self):
        prior = publish_batch(*self.args, wb_files())
        def fail(stage):
            if stage == "after_file:data.csv":
                raise OSError("SYNTHETIC_FAIL")
        with self.assertRaisesRegex(OSError, "SYNTHETIC_FAIL"):
            publish_batch(*self.args, wb_files("40"),
                          expected_generation=prior["generation"], fault=fail)
        self.assertEqual(read_active(*self.args)["files"], wb_files())
        result = reconcile(*self.args)
        self.assertEqual(result["status"], "RECOVERY_REQUIRED")
        self.assertEqual(result["generation"], prior["generation"])
        self.assertEqual(len(result["uncommitted_generations"]), 1)
        with self.assertRaisesRegex(GenerationError, "pending generation"):
            publish_batch(*self.args, wb_files("50"),
                          expected_generation=prior["generation"])

    def test_before_commit_crash_on_first_import_is_pending(self):
        def fail(stage):
            if stage == "before_commit":
                raise OSError("NO_COMMIT")
        with self.assertRaises(OSError):
            publish_batch(*self.args, wb_files(), fault=fail)
        with self.assertRaisesRegex(GenerationError, "UNKNOWN_COMMIT_STATE"):
            read_active(*self.args)
        self.assertEqual(reconcile(*self.args)["status"], "UNKNOWN_COMMIT_STATE")

    def test_after_commit_lost_response_can_be_reconciled(self):
        first = publish_batch(*self.args, wb_files())
        def fail(stage):
            if stage == "after_commit":
                raise OSError("LOST_RECEIPT")
        with self.assertRaisesRegex(CommitUncertainError, "commit result uncertain"):
            publish_batch(*self.args, wb_files("99"),
                          expected_generation=first["generation"], fault=fail)
        active = read_active(*self.args)
        self.assertEqual(active["files"], wb_files("99"))
        self.assertEqual(reconcile(*self.args)["status"], "ACTIVE_VERIFIED")
        same = publish_batch(*self.args, wb_files("99"),
                             expected_generation=first["generation"])
        self.assertFalse(same["changed"])
        self.assertEqual(same["generation"], active["generation"])

    def test_stale_writer_rejected_without_switch(self):
        first = publish_batch(*self.args, wb_files())
        second = publish_batch(*self.args, wb_files("20"),
                               expected_generation=first["generation"])
        with self.assertRaisesRegex(GenerationError, "stale expected generation"):
            publish_batch(*self.args, wb_files("30"),
                          expected_generation=first["generation"])
        self.assertEqual(read_active(*self.args)["generation"], second["generation"])

    def test_ozon_monthly_and_annual_are_one_generation(self):
        args = (self.root, "ozon_final_realization", "ozon_laser_master", "2026")
        first = publish_batch(*args, ozon_final_files())
        second = publish_batch(*args, ozon_final_files(january="9", february="7"),
                               expected_generation=first["generation"])
        self.assertEqual(len(read_active(*args)["files"]), 6)
        self.assertEqual(read_generation(*args, first["generation"], expected_digest=first["manifest_sha256"])["files"],
                         ozon_final_files())
        self.assertEqual(read_active(*args)["generation"], second["generation"])

    def test_ozon_parity_and_corrupt_month_manifest_rejected_before_stage(self):
        args = (self.root, "ozon_final_realization", "ozon_laser_master", "2026")
        ok = publish_batch(*args, ozon_final_files())
        files = ozon_final_files(january="8")
        files["annual.csv"] = ozon_final_files(january="5")["annual.csv"]
        with self.assertRaisesRegex(GenerationError, "manifest identity/hash mismatch"):
            publish_batch(*args, files, expected_generation=ok["generation"])
        files = ozon_final_files(january="8")
        meta = json.loads(files["monthly/2026-01.csv.meta.json"])
        meta["schema"] = True
        files["monthly/2026-01.csv.meta.json"] = json.dumps(meta).encode()
        with self.assertRaisesRegex(GenerationError, "integer field"):
            publish_batch(*args, files, expected_generation=ok["generation"])
        self.assertEqual(read_active(*args)["generation"], ok["generation"])

    def test_pointer_corruption_not_auto_repaired(self):
        first = publish_batch(*self.args, wb_files())
        ptr = (self.root / ".b7-generations" /
               "wb_weekly_finance_main" / "wb_laser_master" / "2026" /
               "CURRENT.json")
        ptr.write_bytes(b'{"schema":true,"generation":"bad"}')
        with self.assertRaises(GenerationError):
            read_active(*self.args)
        self.assertEqual(reconcile(*self.args)["status"], "RECOVERY_REQUIRED")
        with self.assertRaises(GenerationError):
            publish_batch(*self.args, wb_files("30"),
                          expected_generation=first["generation"])

    def test_snapshot_corruption_not_recertified(self):
        first = publish_batch(*self.args, wb_files())
        f = (self.root / ".b7-generations" / "wb_weekly_finance_main" /
             "wb_laser_master" / "2026" / "generations" /
             first["generation"] / "data.csv")
        f.write_bytes(f.read_bytes() + b"CORRUPT")
        with self.assertRaises(GenerationError):
            read_active(*self.args)
        self.assertEqual(reconcile(*self.args)["status"], "RECOVERY_REQUIRED")

    def test_duplicate_json_keys_rejected(self):
        files = wb_files()
        raw = files["data.csv.meta.json"].decode()
        self.assertIn('"schema": 1', raw)
        files["data.csv.meta.json"] = raw.replace('"schema": 1',
                                                    '"schema": true, "schema": 1').encode()
        with self.assertRaisesRegex(GenerationError, "invalid JSON control document"):
            publish_batch(*self.args, files)

    def test_untrusted_paths_and_mismatched_wb_type_rejected(self):
        files = wb_files()
        files["../escape.csv"] = b"bad"
        with self.assertRaisesRegex(GenerationError, "out-of-scope"):
            publish_batch(*self.args, files)
        files = wb_files(dataset="wb_weekly_finance_buyout")
        with self.assertRaises(GenerationError):
            publish_batch(*self.args, files)

    def test_completed_previous_generations_are_not_false_orphans(self):
        one = publish_batch(*self.args, wb_files())
        two = publish_batch(*self.args, wb_files("20"),
                            expected_generation=one["generation"])
        three = publish_batch(*self.args, wb_files("30"),
                              expected_generation=two["generation"])
        self.assertEqual(reconcile(*self.args),
                         {"status": "ACTIVE_VERIFIED", "generation": three["generation"]})
        self.assertEqual(read_generation(*self.args, one["generation"], expected_digest=one["manifest_sha256"])["files"],
                         wb_files())

    def test_uncommitted_first_generation_blocks_new_publish(self):
        def fail(stage):
            if stage == "before_commit":
                raise OSError("test interruption")
        with self.assertRaises(OSError):
            publish_batch(*self.args, wb_files(), fault=fail)
        self.assertEqual(reconcile(*self.args)["status"], "UNKNOWN_COMMIT_STATE")
        with self.assertRaisesRegex(GenerationError, "UNKNOWN_COMMIT_STATE"):
            publish_batch(*self.args, wb_files("99"))

    def test_g1_uncommitted_complete_generation_not_readable_publicly(self):
        a = publish_batch(*self.args, wb_files())
        pending = None
        def stop(where):
            nonlocal pending
            if where == "before_commit":
                store = (self.root / ".b7-generations" /
                         "wb_weekly_finance_main" / "wb_laser_master" / "2026" /
                         "generations")
                pending = next(x.name for x in store.iterdir()
                               if x.name != a["generation"])
                raise OSError("before_commit")
        with self.assertRaises(OSError):
            publish_batch(*self.args, wb_files("21"),
                          expected_generation=a["generation"], fault=stop)
        self.assertIsNotNone(pending)
        scope = (self.root / ".b7-generations" /
                 "wb_weekly_finance_main" / "wb_laser_master" / "2026")
        stage = scope / "generations" / pending / "generation.json"
        from apps.msp_marketplace_reports.generation_store import _sha
        with self.assertRaisesRegex(GenerationError, "not in committed"):
            read_generation(*self.args, pending, expected_digest=_sha(stage.read_bytes()))
        self.assertEqual(read_active(*self.args)["generation"], a["generation"])
        self.assertEqual(reconcile(*self.args)["status"], "RECOVERY_REQUIRED")

    def test_g2_missing_current_after_commits_is_unknown_not_pending(self):
        a = publish_batch(*self.args, wb_files())
        b = publish_batch(*self.args, wb_files("21"),
                          expected_generation=a["generation"])
        current = (self.root / ".b7-generations" /
                   "wb_weekly_finance_main" / "wb_laser_master" / "2026" /
                   "CURRENT.json")
        current.unlink()
        with self.assertRaisesRegex(GenerationError, "UNKNOWN_COMMIT_STATE"):
            read_active(*self.args)
        with self.assertRaisesRegex(GenerationError, "UNKNOWN_COMMIT_STATE"):
            read_generation(*self.args, b["generation"],
                            expected_digest=b["manifest_sha256"])
        self.assertEqual(reconcile(*self.args)["status"], "UNKNOWN_COMMIT_STATE")
        with self.assertRaisesRegex(GenerationError, "UNKNOWN_COMMIT_STATE"):
            publish_batch(*self.args, wb_files("30"),
                          expected_generation=b["generation"])

    def test_g3_old_generation_repack_blocked_by_trusted_parent_hash(self):
        a = publish_batch(*self.args, wb_files())
        b = publish_batch(*self.args, wb_files("21"),
                          expected_generation=a["generation"])
        scope = (self.root / ".b7-generations" / "wb_weekly_finance_main"
                 / "wb_laser_master" / "2026")
        old = scope / "generations" / a["generation"]
        modified = wb_files("999")
        for name, raw in modified.items():
            (old / name).write_bytes(raw)
        descriptor = json.loads((old / "generation.json").read_text("utf-8"))
        from apps.msp_marketplace_reports.generation_store import _sha
        for item in descriptor["files"]:
            raw = (old / item["path"]).read_bytes()
            item["sha256"] = _sha(raw)
            item["bytes"] = len(raw)
        (old / "generation.json").write_text(json.dumps(descriptor), encoding="utf-8")
        with self.assertRaisesRegex(GenerationError, "descriptor hash mismatch"):
            read_active(*self.args)
        with self.assertRaisesRegex(GenerationError, "descriptor hash mismatch"):
            read_generation(*self.args, a["generation"],
                            expected_digest=a["manifest_sha256"])
        self.assertEqual(reconcile(*self.args)["status"], "RECOVERY_REQUIRED")

    def test_g3_wrong_or_missing_pin_refused(self):
        a = publish_batch(*self.args, wb_files())
        with self.assertRaisesRegex(GenerationError, "requires expected descriptor"):
            read_generation(*self.args, a["generation"], expected_digest=None)
        with self.assertRaisesRegex(GenerationError, "pinned generation digest mismatch"):
            read_generation(*self.args, a["generation"], expected_digest="0" * 64)
        self.assertEqual(read_generation(*self.args, a["generation"],
                         expected_digest=a["manifest_sha256"])["files"], wb_files())

    def test_g4_first_scope_creation_fsyncs_each_new_parent(self):
        import unittest.mock
        import apps.msp_marketplace_reports.generation_store as gs
        calls = []
        original = gs._sync_dir
        def record(path):
            calls.append(Path(path))
            return original(path)
        with unittest.mock.patch.object(gs, "_sync_dir", side_effect=record):
            publish_batch(*self.args, wb_files())
        scope = (self.root / ".b7-generations" / "wb_weekly_finance_main" /
                 "wb_laser_master" / "2026")
        chain = [self.root, self.root / ".b7-generations",
                 self.root / ".b7-generations" / "wb_weekly_finance_main",
                 scope.parent, scope]
        for directory in chain:
            self.assertIn(directory.parent, calls,
                          "parent directory not fsynced after mkdir")
            self.assertIn(directory, calls,
                          "new directory itself not fsynced")
        generations = scope / "generations"
        self.assertIn(scope, calls, "scope not fsynced after generations mkdir")
        self.assertIn(generations, calls, "generations directory not fsynced")
        self.assertEqual(reconcile(*self.args)["status"], "ACTIVE_VERIFIED")

    def test_g4_generation_parent_fsync_failure_prevents_commit(self):
        import unittest.mock
        import apps.msp_marketplace_reports.generation_store as gs
        original = gs._sync_dir
        generation_dir = (self.root / ".b7-generations" /
                          "wb_weekly_finance_main" / "wb_laser_master" /
                          "2026" / "generations")
        def fail(path):
            if Path(path) == generation_dir:
                raise OSError("generation hierarchy fsync failed")
            return original(path)
        with unittest.mock.patch.object(gs, "_sync_dir", side_effect=fail):
            with self.assertRaisesRegex(OSError, "generation hierarchy fsync failed"):
                publish_batch(*self.args, wb_files())
        ptr = generation_dir.parent / "CURRENT.json"
        self.assertFalse(ptr.exists())
        self.assertIn(reconcile(*self.args)["status"], ("EMPTY", "RECOVERY_REQUIRED"))

    def test_g4_failure_during_new_parent_fsync_has_no_commit(self):
        import unittest.mock
        import apps.msp_marketplace_reports.generation_store as gs
        original = gs._sync_dir
        target = self.root / ".b7-generations"
        def fail(path):
            if Path(path) == target:
                raise OSError("fsync parent failed")
            return original(path)
        with unittest.mock.patch.object(gs, "_sync_dir", side_effect=fail):
            with self.assertRaisesRegex(OSError, "fsync parent failed"):
                publish_batch(*self.args, wb_files())
        scope = (self.root / ".b7-generations" / "wb_weekly_finance_main" /
                 "wb_laser_master" / "2026")
        self.assertFalse((scope / "CURRENT.json").exists())
        # The failure may leave directories but cannot certify a generation.
        self.assertIsNone(read_active(*self.args))

    def test_symlink_scope_is_rejected_before_directory_creation(self):
        outside = Path(self.root.parent) / "outside"
        outside.mkdir()
        self.root.mkdir()
        (self.root / ".b7-generations").symlink_to(outside,
                                                    target_is_directory=True)
        with self.assertRaisesRegex(GenerationError, "symbolic link forbidden"):
            publish_batch(*self.args, wb_files())
        self.assertEqual(list(outside.rglob("*")), [])

    def test_two_writers_same_generation_cannot_lose_update(self):
        first = publish_batch(*self.args, wb_files())
        stage_reached = threading.Event()
        proceed = threading.Event()
        second_started = threading.Event()
        outcomes = []

        def slow_writer():
            def barrier(where):
                if where == "before_commit":
                    stage_reached.set()
                    if not proceed.wait(10):
                        raise RuntimeError("test barrier expired")
            try:
                outcomes.append(("first", publish_batch(
                    *self.args, wb_files("20"),
                    expected_generation=first["generation"], fault=barrier)))
            except Exception as exc:
                outcomes.append(("first_error", str(exc)))

        def stale_writer():
            second_started.set()
            try:
                outcomes.append(("second", publish_batch(
                    *self.args, wb_files("30"),
                    expected_generation=first["generation"])))
            except GenerationError as exc:
                outcomes.append(("second_error", str(exc)))

        a = threading.Thread(target=slow_writer)
        b = threading.Thread(target=stale_writer)
        a.start()
        try:
            self.assertTrue(stage_reached.wait(10))
            b.start()
            self.assertTrue(second_started.wait(10))
        finally:
            proceed.set()
            a.join(10)
            if b.ident is not None:
                b.join(10)
        self.assertFalse(a.is_alive())
        self.assertFalse(b.is_alive())
        self.assertEqual({x[0] for x in outcomes}, {"first", "second_error"})
        self.assertIn("stale expected generation", outcomes[1][1]
                      if outcomes[1][0] == "second_error" else outcomes[0][1])
        self.assertEqual(read_active(*self.args)["files"], wb_files("20"))

    def test_failing_precommit_does_not_mutate_legacy_canonical_paths(self):
        before = list((self.root / "База данных").rglob("*.csv"))
        def fail(stage):
            if stage == "after_descriptor":
                raise OSError("crash")
        with self.assertRaises(OSError):
            publish_batch(*self.args, wb_files(), fault=fail)
        self.assertEqual(list((self.root / "База данных").rglob("*.csv")), before)
        with self.assertRaisesRegex(GenerationError, "UNKNOWN_COMMIT_STATE"):
            read_active(*self.args)


if __name__ == "__main__":
    unittest.main()
