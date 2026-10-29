"""B7 opt-in adapter and evidence recovery: all fixtures offline/synthetic."""
import json
import os
import shutil
import signal
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from apps.msp_marketplace_reports.archive import _rows, import_csv as import_legacy_csv, verify as verify_legacy
from apps.msp_marketplace_reports.generation_store import (
    CommitUncertainError, GenerationError, publish_batch, read_active, reconcile,
)
from apps.msp_marketplace_reports.generation_recovery import (
    RecoveryUncertainError, quarantine_uncommitted,
)
from apps.msp_marketplace_reports.versioned_archive import (
    import_csv_versioned, read_csv_versioned, verify_versioned_scope,
)
from test_msp_marketplace_generations import wb_files


def source(path, fields, rows):
    import csv
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter=";")
        w.writeheader()
        w.writerows(rows)


class VersionedImportTests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name) / "archive"
        self.source = Path(d.name) / "incoming.csv"

    def _wb(self, report="11", amount="10", report_type="1"):
        source(self.source, ["reportId", "rrdId", "reportType", "amount", "dateTo"],
               [{"reportId": report, "rrdId": report, "reportType": report_type,
                 "amount": amount, "dateTo": "2026-10-11"}])
        return self.source

    def test_wb_versioned_merges_without_legacy_writes(self):
        args = (self.root, "wb_weekly_finance_main", "wb_laser_master", "2026")
        r1 = import_csv_versioned(*args, self._wb())
        self.assertTrue(r1["changed"])
        one, pin = read_csv_versioned(*args)
        self.assertEqual(pin["generation"], r1["generation"])
        self.assertEqual(pin["manifest_sha256"], r1["manifest_sha256"])
        self.assertEqual(len(_rows(one, ("reportId", "rrdId"))[1]), 1)
        same = import_csv_versioned(*args, self._wb())
        self.assertFalse(same["changed"])
        self.assertEqual(same["generation"], r1["generation"])
        r2 = import_csv_versioned(*args, self._wb("12", "25"))
        self.assertTrue(r2["changed"])
        self.assertEqual(r2["new_rows"], 1)
        updated, _ = read_csv_versioned(*args)
        self.assertEqual(len(_rows(updated, ("reportId", "rrdId"))[1]), 2)
        old, old_pin = read_csv_versioned(*args, pinned_generation=pin["generation"],
                                          expected_digest=pin["manifest_sha256"])
        self.assertEqual(old, one)
        self.assertEqual(old_pin["sha256"], pin["sha256"])
        self.assertTrue(verify_versioned_scope(*args)["ok"])
        self.assertFalse((self.root / "База данных").exists())

    def test_wb_conflict_and_wrong_type_no_publish(self):
        args = (self.root, "wb_weekly_finance_main", "wb_laser_master", "2026")
        first = import_csv_versioned(*args, self._wb())
        with self.assertRaisesRegex(ValueError, "conflicting WB"):
            import_csv_versioned(*args, self._wb("11", "99"))
        with self.assertRaisesRegex(ValueError, "reportType mismatch"):
            import_csv_versioned(*args, self._wb("12", "20", "2"))
        self.assertEqual(read_csv_versioned(*args)[1]["generation"], first["generation"])

    def test_two_wb_types_are_isolated(self):
        main = (self.root, "wb_weekly_finance_main", "wb_laser_master", "2026")
        buyout = (self.root, "wb_weekly_finance_buyout", "wb_laser_master", "2026")
        a = import_csv_versioned(*main, self._wb())
        b = import_csv_versioned(*buyout, self._wb("13", "20", "2"))
        self.assertNotEqual(a["generation"], b["generation"])
        self.assertEqual(read_csv_versioned(*main)[1]["generation"], a["generation"])
        self.assertEqual(read_csv_versioned(*buyout)[1]["generation"], b["generation"])

    def test_ozon_monthly_annual_one_snapshot_preserves_old_month(self):
        args_jan = (self.root, "ozon_final_realization", "ozon_laser_master", "2026-01")
        source(self.source, ["report_year", "report_month", "row_number", "qty"], [
            {"report_year": "2026", "report_month": "2026-01", "row_number": "1", "qty": "5"}])
        one = import_csv_versioned(*args_jan, self.source)
        january, pin = read_csv_versioned(*args_jan)
        args_feb = (self.root, "ozon_final_realization", "ozon_laser_master", "2026-02")
        source(self.source, ["report_year", "report_month", "row_number", "qty"], [
            {"report_year": "2026", "report_month": "2026-02", "row_number": "2", "qty": "7"}])
        feb = import_csv_versioned(*args_feb, self.source)
        self.assertNotEqual(one["generation"], feb["generation"])
        self.assertEqual(read_csv_versioned(*args_jan)[0], january)
        self.assertEqual(len(read_active(self.root, "ozon_final_realization",
                                         "ozon_laser_master", "2026")["files"]), 6)
        older = read_csv_versioned(*args_jan, pinned_generation=pin["generation"],
                                   expected_digest=pin["manifest_sha256"])
        self.assertEqual(older[0], january)
        self.assertFalse(verify_versioned_scope(*args_feb)["provider_coverage_proven"])
        self.assertTrue(verify_versioned_scope(*args_feb)["ok"])
        self.assertFalse((self.root / "База данных").exists())

    def test_ozon_bad_month_rejected_before_any_publishing(self):
        args = (self.root, "ozon_final_realization", "ozon_laser_master", "2026-02")
        source(self.source, ["report_year", "report_month", "row_number"], [
            {"report_year": "2026", "report_month": "2026-01", "row_number": "2"}])
        with self.assertRaisesRegex(ValueError, "must match selected month"):
            import_csv_versioned(*args, self.source)
        self.assertFalse(self.root.exists())

    def test_legacy_files_block_opt_in_first_import_without_migration(self):
        args = (self.root, "wb_weekly_finance_main", "wb_laser_master", "2026")
        target = (self.root / "База данных" / "WB" / "wb_laser_master" / "2026"
                  / "finance" / "weekly" / "main" /
                  "wb_laser_master__weekly_main__2026.csv")
        target.parent.mkdir(parents=True)
        target.write_bytes(b"old")
        with self.assertRaisesRegex(GenerationError, "legacy CSV scope"):
            import_csv_versioned(*args, self._wb())
        self.assertEqual(target.read_bytes(), b"old")
        self.assertFalse((self.root / ".b7-generations").exists())

    def test_versioned_optimistic_cas_rejects_concurrent_change(self):
        import apps.msp_marketplace_reports.versioned_archive as va
        args = (self.root, "wb_weekly_finance_main", "wb_laser_master", "2026")
        first = import_csv_versioned(*args, self._wb())
        original = va.publish_batch
        def concurrent_commit(root, dataset, cabinet, period, files,
                              *, expected_generation):
            active = read_active(root, dataset, cabinet, period)
            assert active["generation"] == first["generation"]
            # Publish a distinct full valid candidate before the stale
            # adapter attempts its optimistic commit.
            newer = wb_files("888")
            original(root, dataset, cabinet, period, newer,
                     expected_generation=first["generation"])
            return original(root, dataset, cabinet, period, files,
                            expected_generation=expected_generation)
        with mock.patch.object(va, "publish_batch", side_effect=concurrent_commit):
            with self.assertRaisesRegex(GenerationError, "stale expected generation"):
                import_csv_versioned(*args, self._wb("12", "20"))
        self.assertEqual(read_active(*args)["files"], wb_files("888"))

    def test_adapter_commit_uncertain_does_not_claim_rollback(self):
        import apps.msp_marketplace_reports.versioned_archive as va
        from apps.msp_marketplace_reports.generation_store import publish_batch as core_publish
        args = (self.root, "wb_weekly_finance_main", "wb_laser_master", "2026")
        first = import_csv_versioned(*args, self._wb())
        def ambiguous(root, dataset, cabinet, period, files,
                      *, expected_generation):
            def lose_reply(stage):
                if stage == "after_commit":
                    raise OSError("synthetic response loss after CURRENT")
            return core_publish(root, dataset, cabinet, period, files,
                                expected_generation=expected_generation, fault=lose_reply)
        with mock.patch.object(va, "publish_batch", side_effect=ambiguous):
            with self.assertRaisesRegex(CommitUncertainError, "commit result uncertain"):
                import_csv_versioned(*args, self._wb("12", "30"))
        after, receipt = read_csv_versioned(*args)
        self.assertNotEqual(first["generation"], receipt["generation"])
        self.assertEqual(len(_rows(after, ("reportId", "rrdId"))[1]), 2)
        retry = import_csv_versioned(*args, self._wb("12", "30"))
        self.assertFalse(retry["changed"])
        self.assertEqual(retry["generation"], receipt["generation"])

    def test_cli_opt_in_no_legacy_data_exposure(self):
        import contextlib
        import io
        from apps.msp_marketplace_reports.cli import main
        args = (self.root, "wb_weekly_finance_main", "wb_laser_master", "2026")
        self._wb(amount="SENSITIVE_AMOUNT_990077")
        out = io.StringIO()
        params = ["--root", str(self.root)]
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(params + [
                "import-csv-versioned", "--dataset", args[1],
                "--cabinet", args[2], "--period", args[3],
                "--source", str(self.source)]), 0)
        result = json.loads(out.getvalue())
        self.assertTrue(result["changed"])
        self.assertNotIn("SENSITIVE_AMOUNT_990077", out.getvalue())  # no financial-row payload printed
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(params + [
                "verify-versioned", "--dataset", args[1],
                "--cabinet", args[2], "--period", args[3]]), 0)
        self.assertTrue(json.loads(out.getvalue())["ok"])

    def test_r96_2_versioned_first_blocks_legacy_and_legacy_verify_mixed(self):
        args = (self.root, "wb_weekly_finance_main", "wb_laser_master", "2026")
        receipt = import_csv_versioned(*args, self._wb())
        with self.assertRaisesRegex(ValueError, "versioned scope exists"):
            import_legacy_csv(*args, self.source)
        self.assertEqual(read_active(*args)["generation"], receipt["generation"])
        # Deliberately introduce an inconsistent legacy copy OUTSIDE either
        # cooperating writer; both verifiers must fail, never report two PASS.
        legacy = (self.root / "База данных" / "WB" / "wb_laser_master" / "2026"
                  / "finance" / "weekly" / "main" /
                  "wb_laser_master__weekly_main__2026.csv")
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes(self.source.read_bytes())
        from apps.msp_marketplace_reports.archive import _metadata, _rows
        raw = legacy.read_bytes()
        rows = len(_rows(raw, ("reportId", "rrdId"))[1])
        legacy.with_name(legacy.name + ".meta.json").write_text(
            json.dumps(_metadata(raw, rows, args[1], args[2], args[3])))
        self.assertFalse(verify_legacy(self.root)["ok"])
        self.assertFalse(verify_versioned_scope(*args)["ok"])
        with self.assertRaisesRegex(GenerationError, "legacy CSV scope"):
            read_csv_versioned(*args)

    def test_r96_2_legacy_first_blocks_versioned(self):
        args = (self.root, "wb_weekly_finance_main", "wb_laser_master", "2026")
        legacy = import_legacy_csv(*args, self._wb())
        before = Path(legacy["path"]).read_bytes()
        with self.assertRaisesRegex(GenerationError, "legacy CSV scope"):
            import_csv_versioned(*args, self.source)
        self.assertEqual(Path(legacy["path"]).read_bytes(), before)
        self.assertFalse((self.root / ".b7-generations").exists())

    def test_r96_2_dangling_manifest_symlink_blocks_versioned(self):
        args = (self.root, "wb_weekly_finance_main", "wb_laser_master", "2026")
        legacy = (self.root / "База данных" / "WB" / "wb_laser_master" / "2026"
                  / "finance" / "weekly" / "main" /
                  "wb_laser_master__weekly_main__2026.csv.meta.json")
        legacy.parent.mkdir(parents=True)
        legacy.symlink_to(legacy.parent / "does-not-exist.json")
        self.assertFalse(legacy.exists())
        self.assertTrue(legacy.is_symlink())
        with self.assertRaisesRegex(GenerationError, "symbolic link forbidden"):
            import_csv_versioned(*args, self._wb())
        self.assertFalse((self.root / ".b7-generations").exists())

    def test_r96_2_shared_admission_lock_closes_preflight_window(self):
        import apps.msp_marketplace_reports.versioned_archive as va
        args = (self.root, "wb_weekly_finance_main", "wb_laser_master", "2026")
        path = self._wb()
        entered = threading.Event()
        release = threading.Event()
        old_check = va._assert_no_legacy
        result = {}
        def block(root, dataset, cabinet, period):
            entered.set()
            if not release.wait(10):
                raise RuntimeError("timed out waiting for race release")
            return old_check(root, dataset, cabinet, period)
        def newer():
            try:
                result["new"] = import_csv_versioned(*args, path)
            except Exception as exc:
                result["new_error"] = exc
        def legacy():
            try:
                result["legacy"] = import_legacy_csv(*args, path)
            except Exception as exc:
                result["legacy_error"] = exc
        with mock.patch.object(va, "_assert_no_legacy", side_effect=block):
            a = threading.Thread(target=newer)
            b = threading.Thread(target=legacy)
            a.start()
            try:
                self.assertTrue(entered.wait(10))
                b.start()
            finally:
                release.set()
                a.join(10)
                if b.ident is not None:
                    b.join(10)
        self.assertFalse(a.is_alive())
        self.assertFalse(b.is_alive())
        self.assertIn("new", result, result)
        self.assertIn("legacy_error", result, result)
        self.assertIn("versioned scope exists", str(result["legacy_error"]))
        self.assertFalse((self.root / "База данных").exists())

    def test_r96_4_symlinked_root_locks_and_lockfile_never_escape_root(self):
        """Both import entrypoints reject all three Hermes R96-4 probes."""
        imports = (("versioned", import_csv_versioned),
                   ("legacy", import_legacy_csv))
        for importer_name, importer in imports:
            for case in ("root", "locks", "lockfile", "dangling_lockfile",
                         "dangling_locks", "ancestor"):
                with self.subTest(importer=importer_name, case=case):
                    base = Path(self.source.parent) / ("r96-4-" + importer_name
                                                       + "-" + case)
                    base.mkdir()
                    outside = base / "outside"
                    outside.mkdir()
                    root = base / "archive"
                    lockname = "wb_laser_master__wb_weekly_finance_main.lock"
                    if case == "root":
                        root.symlink_to(outside, target_is_directory=True)
                    elif case == "ancestor":
                        alias = base / "alias"
                        alias.symlink_to(outside, target_is_directory=True)
                        root = alias / "archive"
                    else:
                        root.mkdir()
                        if case in ("locks", "dangling_locks"):
                            target = (outside if case == "locks"
                                      else base / "not-existing-lock-folder")
                            (root / ".locks").symlink_to(
                                target, target_is_directory=True)
                        else:
                            folder = root / ".locks"
                            folder.mkdir()
                            (folder / lockname).symlink_to(outside / "injected.lock")
                    src = self._wb()
                    before = [(p.relative_to(outside).as_posix(), p.is_symlink())
                              for p in outside.rglob("*")]
                    with self.assertRaisesRegex(ValueError, "unsafe archive admission"):
                        importer(root, "wb_weekly_finance_main",
                                 "wb_laser_master", "2026", src)
                    after = [(p.relative_to(outside).as_posix(), p.is_symlink())
                             for p in outside.rglob("*")]
                    self.assertEqual(before, after)
                    self.assertFalse((outside / "injected.lock").exists())
                    self.assertFalse((outside / ".locks").exists())

    def test_r96_4_existing_lock_regular_file_allowed_but_hardlink_refused(self):
        root = Path(self.source.parent) / "r96-4-regular"
        root.mkdir()
        folder = root / ".locks"
        folder.mkdir()
        name = "wb_laser_master__wb_weekly_finance_main.lock"
        (folder / name).write_bytes(b"")
        receipt = import_csv_versioned(root, "wb_weekly_finance_main",
                                       "wb_laser_master", "2026", self._wb())
        self.assertEqual(receipt["status"], "COMMITTED")
        other = Path(self.source.parent) / "outside-hardlink"
        os.link(folder / name, other)
        with self.assertRaisesRegex(ValueError, "unsafe archive admission lock inode"):
            import_csv_versioned(root, "wb_weekly_finance_main",
                                 "wb_laser_master", "2026", self._wb("12"))
        self.assertEqual(other.read_bytes(), b"")
        self.assertEqual(read_active(root, "wb_weekly_finance_main",
                                     "wb_laser_master", "2026")["generation"],
                         receipt["generation"])

    def test_r96_2_shared_admission_lock_legacy_wins_race(self):
        import apps.msp_marketplace_reports.archive as legacy_module
        args = (self.root, "wb_weekly_finance_main", "wb_laser_master", "2026")
        path = self._wb()
        entered, release = threading.Event(), threading.Event()
        original = legacy_module._reject_versioned_scope
        results = {}
        def pause(root, dataset, cabinet, period):
            entered.set()
            if not release.wait(10):
                raise RuntimeError("legacy admission test timed out")
            return original(root, dataset, cabinet, period)
        def legacy():
            try:
                results["legacy"] = import_legacy_csv(*args, path)
            except Exception as error:
                results["legacy_error"] = error
        def new():
            try:
                results["new"] = import_csv_versioned(*args, path)
            except Exception as error:
                results["new_error"] = error
        with mock.patch.object(legacy_module, "_reject_versioned_scope",
                               side_effect=pause):
            a = threading.Thread(target=legacy)
            b = threading.Thread(target=new)
            a.start()
            try:
                self.assertTrue(entered.wait(10))
                b.start()
            finally:
                release.set()
                a.join(10)
                if b.ident is not None:
                    b.join(10)
        self.assertFalse(a.is_alive())
        self.assertFalse(b.is_alive())
        self.assertIn("legacy", results, results)
        self.assertIn("new_error", results, results)
        self.assertIn("legacy CSV scope", str(results["new_error"]))
        self.assertFalse((self.root / ".b7-generations").exists())

    def test_readonly_verify_does_not_create_empty_root(self):
        args = (self.root, "ozon_current_orders_fbo", "ozon_dmitrieva", "2026-10")
        self.assertFalse(verify_versioned_scope(*args)["ok"])
        self.assertFalse(self.root.exists())


class EvidenceQuarantineTests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name) / "archive"
        self.args = (self.root, "wb_weekly_finance_main", "wb_laser_master", "2026")
        self.committed = publish_batch(*self.args, wb_files())
        self.scope = (self.root / ".b7-generations" /
                      "wb_weekly_finance_main" / "wb_laser_master" / "2026")

    def _orphan(self, value="40"):
        current = self.committed
        def fail(where):
            if where == "before_commit":
                raise OSError("synthetic precommit")
        with self.assertRaisesRegex(OSError, "synthetic precommit"):
            publish_batch(*self.args, wb_files(value),
                          expected_generation=current["generation"], fault=fail)
        folder = self.scope / "generations"
        return next(x.name for x in folder.iterdir()
                    if x.name != self.committed["generation"])

    def _quarantine(self, ids, *, fault=None, expected=None, digest=None, ack=True):
        return quarantine_uncommitted(
            *self.args, expected_generation=expected or self.committed["generation"],
            expected_digest=digest or self.committed["manifest_sha256"],
            candidates=ids, acknowledged=ack, fault=fault)

    def test_retains_uncommitted_bytes_and_clears_pending_without_changing_current(self):
        candidate = self._orphan()
        source = self.scope / "generations" / candidate
        before = {x.relative_to(source).as_posix(): x.read_bytes()
                  for x in source.rglob("*") if x.is_file()}
        self.assertEqual(reconcile(*self.args)["status"], "RECOVERY_REQUIRED")
        report = self._quarantine([candidate])
        self.assertEqual(report["status"], "EVIDENCE_RETAINED")
        self.assertTrue(report["current_unchanged"])
        evidence = self.scope / "evidence" / candidate
        self.assertFalse(source.exists())
        self.assertEqual({x.relative_to(evidence).as_posix(): x.read_bytes()
                          for x in evidence.rglob("*") if x.is_file()}, before)
        self.assertEqual(reconcile(*self.args)["status"], "ACTIVE_VERIFIED")
        self.assertEqual(read_active(*self.args)["generation"],
                         self.committed["generation"])
        repeat = self._quarantine([candidate])
        self.assertEqual(repeat["moved_in_this_attempt"], [])
        fresh = publish_batch(*self.args, wb_files("60"),
                              expected_generation=self.committed["generation"])
        self.assertEqual(fresh["status"], "COMMITTED")

    def test_requires_ack_and_exact_commit_pin(self):
        candidate = self._orphan()
        with self.assertRaisesRegex(GenerationError, "acknowledgment"):
            self._quarantine([candidate], ack=False)
        with self.assertRaisesRegex(GenerationError, "stale recovery pin"):
            self._quarantine([candidate], digest="0" * 64)
        self.assertTrue((self.scope / "generations" / candidate).exists())

    def test_uncertain_evidence_rename_is_retryable(self):
        candidate = self._orphan()
        def fault(where):
            if where.startswith("after_evidence_fsync"):
                raise OSError("response lost after evidence")
        with self.assertRaisesRegex(RecoveryUncertainError, "uncertain"):
            self._quarantine([candidate], fault=fault)
        self.assertTrue((self.scope / "evidence" / candidate).exists())
        result = self._quarantine([candidate])
        self.assertEqual(result["status"], "EVIDENCE_RETAINED")
        self.assertEqual(result["moved_in_this_attempt"], [])
        self.assertEqual(reconcile(*self.args)["status"], "ACTIVE_VERIFIED")

    def test_missing_current_is_unknown_and_never_quarantined(self):
        candidate = self._orphan()
        (self.scope / "CURRENT.json").unlink()
        with self.assertRaisesRegex(GenerationError, "UNKNOWN_COMMIT_STATE"):
            self._quarantine([candidate])
        self.assertTrue((self.scope / "generations" / candidate).exists())

    def test_committed_generation_and_unlisted_candidates_refused(self):
        candidate = self._orphan()
        with self.assertRaisesRegex(GenerationError, "cannot quarantine committed"):
            self._quarantine([self.committed["generation"]])
        with self.assertRaisesRegex(GenerationError, "unlisted uncommitted"):
            self._quarantine(["0" * 32])
        self.assertTrue((self.scope / "generations" / candidate).exists())

    def test_r96_1_retry_resyncs_source_parent_after_failed_first_fsync(self):
        import apps.msp_marketplace_reports.generation_recovery as gr
        candidate = self._orphan()
        original = gr._sync_dir
        source_parent = self.scope / "generations"
        evidence = self.scope / "evidence"
        injected = []
        def fail(path):
            if Path(path) == source_parent and not injected:
                injected.append(True)
                raise OSError("first source-parent fsync failed")
            return original(path)
        with mock.patch.object(gr, "_sync_dir", side_effect=fail):
            with self.assertRaises(RecoveryUncertainError) as error:
                self._quarantine([candidate])
        self.assertEqual(error.exception.moved_in_attempt, (candidate,))
        self.assertTrue((evidence / candidate).is_dir())
        self.assertFalse((source_parent / candidate).exists())
        trace = []
        def audit(path):
            trace.append(Path(path))
            return original(path)
        with mock.patch.object(gr, "_sync_dir", side_effect=audit):
            report = self._quarantine([candidate])
        self.assertIn(source_parent, trace, "retry skipped original failed sync")
        self.assertIn(evidence, trace)
        self.assertEqual(report["status"], "EVIDENCE_RETAINED")
        self.assertEqual(report["moved_in_this_attempt"], [])
        self.assertIn(candidate, report["resynced_candidates"])

    def test_r96_1_evidence_dir_fsync_failure_resynced_on_retry(self):
        import apps.msp_marketplace_reports.generation_recovery as gr
        candidate = self._orphan()
        source_parent = self.scope / "generations"
        evidence = self.scope / "evidence"
        original = gr._sync_dir
        injected = []
        def fail(path):
            if Path(path) == evidence and not injected:
                injected.append(True)
                raise OSError("evidence fsync interrupted")
            return original(path)
        with mock.patch.object(gr, "_sync_dir", side_effect=fail):
            with self.assertRaises(RecoveryUncertainError):
                self._quarantine([candidate])
        self.assertTrue((evidence / candidate).exists())
        trace = []
        def audit(path):
            trace.append(Path(path))
            return original(path)
        with mock.patch.object(gr, "_sync_dir", side_effect=audit):
            result = self._quarantine([candidate])
        self.assertEqual(result["status"], "EVIDENCE_RETAINED")
        self.assertIn(source_parent, trace)
        self.assertIn(evidence, trace)

    @unittest.skipUnless(hasattr(os, "fork"), "Linux fork required")
    def test_r96_1_sigkill_after_evidence_rename_requires_retry_sync(self):
        import apps.msp_marketplace_reports.generation_recovery as gr
        candidate = self._orphan()
        original = gr._sync_dir
        evidence = self.scope / "evidence"
        source_parent = self.scope / "generations"
        pid = os.fork()
        if pid == 0:
            try:
                def terminate(path):
                    if Path(path) == source_parent and (evidence / candidate).exists():
                        os.kill(os.getpid(), signal.SIGKILL)
                    return original(path)
                with mock.patch.object(gr, "_sync_dir", side_effect=terminate):
                    self._quarantine([candidate])
            finally:
                os._exit(82)
        _, status = os.waitpid(pid, 0)
        self.assertTrue(os.WIFSIGNALED(status))
        self.assertEqual(os.WTERMSIG(status), signal.SIGKILL)
        trace = []
        def audit(path):
            trace.append(Path(path))
            return original(path)
        with mock.patch.object(gr, "_sync_dir", side_effect=audit):
            result = self._quarantine([candidate])
        self.assertIn(source_parent, trace)
        self.assertIn(evidence, trace)
        self.assertEqual(result["status"], "EVIDENCE_RETAINED")

    def test_r96_3_invalid_second_candidate_rejected_before_first_rename(self):
        candidate = self._orphan()
        second = "f" * 32
        if second == candidate:
            second = "e" * 32
        clone = self.scope / "generations" / second
        shutil.copytree(self.scope / "generations" / candidate, clone)
        evidence = self.scope / "evidence"
        evidence.mkdir()
        (evidence / second).write_bytes(b"conflicting evidence entry")
        before = {p.relative_to(self.scope).as_posix(): p.read_bytes()
                  for p in self.scope.rglob("*") if p.is_file()}
        with self.assertRaisesRegex(GenerationError, "invalid evidence"):
            self._quarantine([candidate, second])
        self.assertTrue((self.scope / "generations" / candidate).is_dir())
        self.assertFalse((evidence / candidate).exists())
        self.assertEqual(before, {
            p.relative_to(self.scope).as_posix(): p.read_bytes()
            for p in self.scope.rglob("*") if p.is_file()})

    def test_r96_3_partial_progress_exposed_on_second_rename_error(self):
        import apps.msp_marketplace_reports.generation_recovery as gr
        candidate = self._orphan()
        second = "f" * 32
        if second == candidate:
            second = "e" * 32
        shutil.copytree(self.scope / "generations" / candidate,
                        self.scope / "generations" / second)
        ordered = sorted((candidate, second))
        original = gr.os.replace
        def fail_second(src, dest):
            if Path(src).name == ordered[1]:
                raise OSError("synthetic second rename failure")
            return original(src, dest)
        with mock.patch.object(gr.os, "replace", side_effect=fail_second):
            with self.assertRaises(RecoveryUncertainError) as error:
                self._quarantine(ordered)
        self.assertEqual(error.exception.candidate, ordered[1])
        self.assertEqual(error.exception.moved_in_attempt, (ordered[0],))
        self.assertIn("partial progress=", str(error.exception))
        self.assertTrue((self.scope / "evidence" / ordered[0]).exists())
        result = self._quarantine(ordered)
        self.assertEqual(result["status"], "EVIDENCE_RETAINED")
        self.assertEqual(result["moved_in_this_attempt"], [ordered[1]])
        self.assertEqual(reconcile(*self.args)["status"], "ACTIVE_VERIFIED")

    def test_quarantine_isolation_from_other_cabinet(self):
        candidate = self._orphan()
        other_args = (self.root, "wb_weekly_finance_main", "wb_novokshenov", "2026")
        # Fixture must identify the second cabinet correctly.
        from apps.msp_marketplace_reports.archive import _metadata
        files = wb_files()
        meta = json.loads(files["data.csv.meta.json"])
        meta["cabinet"] = "wb_novokshenov"
        files["data.csv.meta.json"] = json.dumps(meta).encode()
        other = publish_batch(*other_args, files)
        self._quarantine([candidate])
        self.assertEqual(read_active(*other_args)["generation"], other["generation"])


if __name__ == "__main__":
    unittest.main()
