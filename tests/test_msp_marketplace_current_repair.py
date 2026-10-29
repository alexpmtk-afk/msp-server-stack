"""B7 phase 3: explicit witnessed pointer repair, synthetic inputs only."""
import base64
import json
import os
import signal
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from apps.msp_marketplace_reports.archive import _sha
from apps.msp_marketplace_reports.generation_store import (
    GenerationError, publish_batch, read_active, reconcile,
)
from apps.msp_marketplace_reports.current_repair import (
    RestoreUncertainError, repair_current_with_witness,
)
from test_msp_marketplace_generations import wb_files, ozon_final_files


class WitnessedCurrentRepairTests(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name) / "archive"
        self.args = (self.root, "wb_weekly_finance_main", "wb_laser_master", "2026")
        self.a = publish_batch(*self.args, wb_files("10"))
        self.b = publish_batch(*self.args, wb_files("20"),
                               expected_generation=self.a["generation"])
        self.scope = (self.root / ".b7-generations" /
                      "wb_weekly_finance_main" / "wb_laser_master" / "2026")
        self.current = self.scope / "CURRENT.json"

    def _repair(self, *, expected_current_sha256=None, generation=None,
                expected_digest=None, acknowledged=True, reference="external-test-receipt",
                fault=None):
        return repair_current_with_witness(
            *self.args, generation=generation or self.b["generation"],
            expected_digest=expected_digest or self.b["manifest_sha256"],
            expected_current_sha256=expected_current_sha256,
            witness_reference=reference, acknowledged=acknowledged,
            fault=fault)

    def _journal(self):
        docs = list((self.scope / "restore-journal").glob("*.json"))
        self.assertEqual(len(docs), 1)
        return json.loads(docs[0].read_text("utf-8"))

    def test_missing_current_two_commits_requires_witness_and_restores_b(self):
        self.current.unlink()
        self.assertEqual(reconcile(*self.args)["status"], "UNKNOWN_COMMIT_STATE")
        outcome = self._repair()
        self.assertEqual(outcome["status"], "CURRENT_VERIFIED")
        self.assertFalse(outcome["external_witness_authenticated_by_code"])
        self.assertEqual(read_active(*self.args)["generation"], self.b["generation"])
        self.assertEqual(reconcile(*self.args)["status"], "ACTIVE_VERIFIED")
        record = self._journal()
        self.assertEqual(record["state"], "VERIFIED")
        self.assertIsNone(record["previous_b64"])
        again = self._repair()
        self.assertFalse(again["changed_in_attempt"])

    def test_corrupt_current_preimage_is_preserved_unchanged(self):
        original = b'{broken CURRENT, not JSON}\n'
        self.current.write_bytes(original)
        receipt = self._repair(expected_current_sha256=_sha(original))
        self.assertEqual(receipt["status"], "CURRENT_VERIFIED")
        doc = self._journal()
        self.assertEqual(base64.b64decode(doc["previous_b64"]), original)
        self.assertEqual(doc["expected_previous_sha256"], _sha(original))
        self.assertEqual(read_active(*self.args)["files"], wb_files("20"))

    def test_no_ack_missing_witness_and_bad_pin_refused_before_journal(self):
        self.current.unlink()
        with self.assertRaisesRegex(GenerationError, "acknowledgment"):
            self._repair(acknowledged=False)
        with self.assertRaisesRegex(GenerationError, "independent witness reference"):
            self._repair(reference="")
        with self.assertRaisesRegex(GenerationError, "descriptor hash mismatch"):
            self._repair(expected_digest="0" * 64)
        self.assertFalse((self.scope / "restore-journal").exists())

    def test_stale_current_cas_does_not_publish_or_save_recovery_evidence(self):
        original = b'{"state":"broken"}'
        self.current.write_bytes(original)
        with self.assertRaisesRegex(GenerationError, "stale CURRENT byte CAS"):
            self._repair(expected_current_sha256="0" * 64)
        self.assertEqual(self.current.read_bytes(), original)
        self.assertFalse((self.scope / "restore-journal").exists())

    def test_healthy_divergent_head_cannot_be_rolled_back(self):
        before = self.current.read_bytes()
        with self.assertRaisesRegex(GenerationError, "healthy divergent"):
            self._repair(generation=self.a["generation"],
                         expected_digest=self.a["manifest_sha256"],
                         expected_current_sha256=_sha(before))
        self.assertEqual(self.current.read_bytes(), before)
        self.assertFalse((self.scope / "restore-journal").exists())

    def test_extra_staged_generation_blocks_unknown_last_commit(self):
        def interrupt(where):
            if where == "before_commit":
                raise OSError("uncommitted C")
        with self.assertRaises(OSError):
            publish_batch(*self.args, wb_files("30"),
                          expected_generation=self.b["generation"], fault=interrupt)
        self.current.unlink()
        with self.assertRaisesRegex(GenerationError, "UNRESOLVED_HEAD"):
            self._repair()
        self.assertFalse((self.scope / "restore-journal").exists())
        self.assertEqual(reconcile(*self.args)["status"], "UNKNOWN_COMMIT_STATE")

    def test_repacked_old_ancestor_blocked_by_parent_hash(self):
        old = self.scope / "generations" / self.a["generation"]
        corrupted = old / "data.csv"
        corrupted.write_bytes(corrupted.read_bytes() + b"repacked")
        self.current.unlink()
        with self.assertRaises(GenerationError):
            self._repair()
        self.assertFalse((self.scope / "restore-journal").exists())

    def test_interrupted_before_switch_retries_with_original_witness(self):
        old = b'{"invalid":"before"}'
        self.current.write_bytes(old)
        def fault(where):
            if where == "after_prepare":
                raise OSError("lost response after evidence fsync")
        with self.assertRaisesRegex(RestoreUncertainError, "evidence preparation"):
            self._repair(expected_current_sha256=_sha(old), fault=fault)
        self.assertEqual(self._journal()["state"], "PREPARED")
        self.assertEqual(self.current.read_bytes(), old)
        result = self._repair(expected_current_sha256=_sha(old))
        self.assertTrue(result["changed_in_attempt"])
        self.assertEqual(self._journal()["state"], "VERIFIED")

    def test_interrupted_after_switch_retries_and_preserves_old_pointer(self):
        old = b'{"schema":true,"generation":"bad"}'
        self.current.write_bytes(old)
        def fault(where):
            if where == "after_switch":
                raise OSError("lost reply after atomic CURRENT replace")
        with self.assertRaisesRegex(RestoreUncertainError, "CURRENT switch uncertain"):
            self._repair(expected_current_sha256=_sha(old), fault=fault)
        self.assertEqual(read_active(*self.args)["generation"], self.b["generation"])
        self.assertEqual(self._journal()["state"], "PREPARED")
        outcome = self._repair(expected_current_sha256=_sha(old))
        self.assertFalse(outcome["changed_in_attempt"])
        journal = self._journal()
        self.assertEqual(journal["state"], "VERIFIED")
        self.assertEqual(base64.b64decode(journal["previous_b64"]), old)

    def test_interrupted_after_verify_does_not_lose_journal(self):
        self.current.unlink()
        def fault(where):
            if where == "after_journal_verified":
                raise OSError("lost completion reply")
        with self.assertRaises(RestoreUncertainError):
            self._repair(fault=fault)
        self.assertEqual(self._journal()["state"], "VERIFIED")
        self.assertFalse(self._repair()["changed_in_attempt"])

    def test_after_journal_prepare_fsync_uncertain_does_not_switch_until_retry(self):
        import apps.msp_marketplace_reports.current_repair as cr
        self.current.unlink()
        original = cr._safe_write
        injected = []
        def fail_after_persist(path, data):
            original(path, data)
            if Path(path).parent.name == "restore-journal" and not injected:
                injected.append(True)
                raise OSError("journal fsync return lost")
        with mock.patch.object(cr, "_safe_write", side_effect=fail_after_persist):
            with self.assertRaisesRegex(RestoreUncertainError, "preparation uncertain"):
                self._repair()
        self.assertTrue(injected)
        self.assertFalse(self.current.exists())
        self.assertEqual(self._journal()["state"], "PREPARED")
        self.assertEqual(self._repair()["status"], "CURRENT_VERIFIED")
        self.assertEqual(self._journal()["state"], "VERIFIED")

    def test_current_replace_completed_but_fsync_error_is_uncertain_and_retryable(self):
        import apps.msp_marketplace_reports.current_repair as cr
        previous = b'{"bad":true}'
        self.current.write_bytes(previous)
        original = cr._safe_write
        injected = []
        def fail_after_replace(path, data):
            original(path, data)
            if Path(path).name == "CURRENT.json" and not injected:
                injected.append(True)
                raise OSError("CURRENT fsync response lost")
        with mock.patch.object(cr, "_safe_write", side_effect=fail_after_replace):
            with self.assertRaisesRegex(RestoreUncertainError, "switch uncertain"):
                self._repair(expected_current_sha256=_sha(previous))
        self.assertEqual(read_active(*self.args)["generation"], self.b["generation"])
        self.assertEqual(self._journal()["state"], "PREPARED")
        self.assertFalse(self._repair(
            expected_current_sha256=_sha(previous))["changed_in_attempt"])
        self.assertEqual(base64.b64decode(self._journal()["previous_b64"]), previous)

    def test_tampered_prepared_journal_and_unrelated_pending_journal_rejected(self):
        previous = b'{broken-pointer}'
        self.current.write_bytes(previous)
        def stop(where):
            if where == "after_prepare":
                raise OSError("interrupted")
        with self.assertRaises(RestoreUncertainError):
            self._repair(expected_current_sha256=_sha(previous), fault=stop)
        folder = self.scope / "restore-journal"
        document = next(folder.glob("*.json"))
        original = document.read_bytes()
        altered = json.loads(original)
        altered["previous_b64"] = base64.b64encode(b"fabricated").decode()
        document.write_text(json.dumps(altered))
        with self.assertRaisesRegex(GenerationError, "preimage"):
            self._repair(expected_current_sha256=_sha(previous))
        document.write_bytes(original)
        foreign = folder / ("f" * 32 + ".json")
        foreign.write_text('{"state":"PREPARED"}')
        with self.assertRaisesRegex(GenerationError, "unfinished restore journal"):
            self._repair(expected_current_sha256=_sha(previous))
        self.assertEqual(self.current.read_bytes(), previous)

    def test_untrusted_current_symlink_never_writes_outside(self):
        outside = Path(self.root.parent) / "outside-current"
        outside.write_bytes(b"SENTINEL")
        self.current.unlink()
        self.current.symlink_to(outside)
        with self.assertRaisesRegex(GenerationError, "symbolic link forbidden"):
            self._repair()
        self.assertEqual(outside.read_bytes(), b"SENTINEL")
        self.assertFalse((self.scope / "restore-journal").exists())

    def test_r97_2_strict_schema_prepared_and_verified_without_mutation(self):
        """Reject wrong JSON schema tokens in BOTH states before any rewrite."""
        previous = b'{"broken":"initial CURRENT"}'
        self.current.write_bytes(previous)
        previous_sha = _sha(previous)
        def fail(where):
            if where == "after_prepare":
                raise OSError("planned stop")
        with self.assertRaises(RestoreUncertainError):
            self._repair(expected_current_sha256=previous_sha, fault=fail)
        path = next((self.scope / "restore-journal").glob("*.json"))
        prepared = json.loads(path.read_bytes())
        variants = (True, 1.0, False, 0.0, "1", None, [], {})
        for variant in variants:
            with self.subTest(state="PREPARED", schema=repr(variant)):
                corrupt = dict(prepared, schema=variant)
                exact = json.dumps(corrupt).encode()
                path.write_bytes(exact)
                with self.assertRaisesRegex(GenerationError, "journal schema"):
                    self._repair(expected_current_sha256=previous_sha)
                self.assertEqual(path.read_bytes(), exact)
                self.assertEqual(self.current.read_bytes(), previous)
        path.write_bytes(json.dumps(prepared).encode())
        completed = self._repair(expected_current_sha256=previous_sha)
        self.assertEqual(completed["status"], "CURRENT_VERIFIED")
        verified = json.loads(path.read_bytes())
        self.assertEqual(verified["state"], "VERIFIED")
        new_pointer = self.current.read_bytes()
        for variant in variants:
            with self.subTest(state="VERIFIED", schema=repr(variant)):
                corrupt = dict(verified, schema=variant)
                exact = json.dumps(corrupt).encode()
                path.write_bytes(exact)
                with self.assertRaisesRegex(GenerationError, "journal schema"):
                    self._repair(expected_current_sha256=previous_sha)
                self.assertEqual(path.read_bytes(), exact)
                self.assertEqual(self.current.read_bytes(), new_pointer)

    @unittest.skipUnless(Path("/proc/self/fd").is_dir(), "Linux fd inspection required")
    def test_r97_1_verified_rename_dir_fsync_failure_retries_even_when_visible(self):
        """Simulate fsync(directory) fail after VERIFIED os.replace, then retry."""
        import apps.msp_marketplace_reports.current_repair as cr
        self.current.unlink()
        journal_dir = self.scope / "restore-journal"
        real_fsync = os.fsync
        injected = []
        def fail_fsync(fd):
            try:
                name = Path(os.readlink("/proc/self/fd/" + str(fd)))
            except OSError:
                name = None
            journal = next(journal_dir.glob("*.json"), None) if journal_dir.exists() else None
            if (name == journal_dir and journal is not None and
                    json.loads(journal.read_bytes()).get("state") == "VERIFIED"
                    and not injected):
                injected.append(True)
                raise OSError("R97-1 synthetic final journal directory fsync")
            return real_fsync(fd)
        with mock.patch.object(os, "fsync", side_effect=fail_fsync):
            with self.assertRaisesRegex(RestoreUncertainError, "post-switch"):
                self._repair()
        self.assertTrue(injected)
        self.assertEqual(self._journal()["state"], "VERIFIED")
        self.assertEqual(read_active(*self.args)["generation"], self.b["generation"])
        journal = next(journal_dir.glob("*.json"))
        exact_before = journal.read_bytes()
        real_sync = cr._sync_dir
        observed = []
        def reject_once(path):
            observed.append(Path(path))
            if Path(path) == journal_dir:
                raise OSError("R97-1 repeated fsync failed")
            return real_sync(path)
        with mock.patch.object(cr, "_sync_dir", side_effect=reject_once):
            with self.assertRaisesRegex(RestoreUncertainError, "VERIFIED journal sync uncertain"):
                self._repair()
        self.assertIn(journal_dir, observed)
        self.assertEqual(journal.read_bytes(), exact_before)
        observed.clear()
        def pass_sync(path):
            observed.append(Path(path))
            return real_sync(path)
        with mock.patch.object(cr, "_sync_dir", side_effect=pass_sync):
            answer = self._repair()
        self.assertEqual(answer["status"], "CURRENT_VERIFIED")
        self.assertFalse(answer["changed_in_attempt"])
        self.assertIn(journal_dir, observed)
        self.assertEqual(journal.read_bytes(), exact_before)

    @unittest.skipUnless(hasattr(os, "fork") and Path("/proc/self/fd").is_dir(),
                         "Linux fork and fd inspection required")
    def test_r97_1_sigkill_after_verified_rename_retries_file_and_dir_fsync(self):
        import apps.msp_marketplace_reports.current_repair as cr
        self.current.unlink()
        journal_dir = self.scope / "restore-journal"
        pid = os.fork()
        if pid == 0:
            try:
                real_fsync = os.fsync
                def die_before_dir_fsync(fd):
                    name = Path(os.readlink("/proc/self/fd/" + str(fd)))
                    journal = next(journal_dir.glob("*.json"), None) if journal_dir.exists() else None
                    if (name == journal_dir and journal is not None and
                            json.loads(journal.read_bytes()).get("state") == "VERIFIED"):
                        os.kill(os.getpid(), signal.SIGKILL)
                    return real_fsync(fd)
                with mock.patch.object(os, "fsync", side_effect=die_before_dir_fsync):
                    self._repair()
            finally:
                os._exit(96)
        _, code = os.waitpid(pid, 0)
        self.assertTrue(os.WIFSIGNALED(code))
        self.assertEqual(os.WTERMSIG(code), signal.SIGKILL)
        self.assertEqual(self._journal()["state"], "VERIFIED")
        trace = []
        actual_sync = cr._sync_dir
        def trace_sync(path):
            trace.append(Path(path))
            return actual_sync(path)
        with mock.patch.object(cr, "_sync_dir", side_effect=trace_sync):
            receipt = self._repair()
        self.assertFalse(receipt["changed_in_attempt"])
        self.assertEqual(receipt["status"], "CURRENT_VERIFIED")
        self.assertIn(journal_dir, trace)
        self.assertEqual(self._journal()["state"], "VERIFIED")

    @unittest.skipUnless(hasattr(os, "fork"), "requires Linux fork")
    def test_real_sigkill_after_current_switch_replays_same_transaction(self):
        original = b"{corrupted before repair}"
        self.current.write_bytes(original)
        pid = os.fork()
        if pid == 0:
            try:
                def kill(where):
                    if where == "after_switch":
                        os.kill(os.getpid(), signal.SIGKILL)
                self._repair(expected_current_sha256=_sha(original), fault=kill)
            finally:
                os._exit(95)
        _, status = os.waitpid(pid, 0)
        self.assertTrue(os.WIFSIGNALED(status))
        self.assertEqual(os.WTERMSIG(status), signal.SIGKILL)
        result = self._repair(expected_current_sha256=_sha(original))
        self.assertFalse(result["changed_in_attempt"])
        self.assertEqual(self._journal()["state"], "VERIFIED")
        self.assertEqual(read_active(*self.args)["generation"], self.b["generation"])

    def test_same_scope_legacy_is_refused_without_new_pointer(self):
        self.current.unlink()
        legacy = (self.root / "База данных" / "WB" / "wb_laser_master" /
                  "2026" / "finance" / "weekly" / "main" /
                  "wb_laser_master__weekly_main__2026.csv")
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes(b"old")
        with self.assertRaisesRegex(GenerationError, "legacy CSV scope exists"):
            self._repair()
        self.assertFalse((self.scope / "restore-journal").exists())

    def test_missing_and_corrupt_current_ozon_final_year(self):
        scope_args = (self.root, "ozon_final_realization", "ozon_laser_master", "2026")
        first = publish_batch(*scope_args, ozon_final_files())
        second = publish_batch(*scope_args, ozon_final_files(january="6", february="7"),
                               expected_generation=first["generation"])
        current = (self.root / ".b7-generations" / "ozon_final_realization" /
                   "ozon_laser_master" / "2026" / "CURRENT.json")
        corrupt = b'{"schema":false}\n'
        current.write_bytes(corrupt)
        outcome = repair_current_with_witness(
            *scope_args, generation=second["generation"],
            expected_digest=second["manifest_sha256"],
            expected_current_sha256=_sha(corrupt),
            witness_reference="synthetic-independent-yearly-receipt",
            acknowledged=True)
        self.assertEqual(outcome["status"], "CURRENT_VERIFIED")
        self.assertEqual(len(read_active(*scope_args)["files"]), 6)


if __name__ == "__main__":
    unittest.main()
