"""Test the privileged receiver in an isolated sandbox, not against real credentials."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from scripts.remote.msp_reports_credentials_receiver import (
    CredentialTransferError, DESTINATION, check_ready, receive_bundle, validate_bundle, interactive_bundle,
)


def fake_bundle():
    return {
        "wb_laser_master": {"token": "eyJhbGciOiJub25lIn0.eyJjYWIiOiJBIn0.c2lnQQ"},
        "wb_novokshenov": {"token": "eyJhbGciOiJub25lIn0.eyJjYWIiOiJCIn0.c2lnQg"},
        "wb_dmitrieva": {"token": "eyJhbGciOiJub25lIn0.eyJjYWIiOiJDIn0.c2lnQw"},
        "ozon_laser_master": {"client_id": "1001", "api_key": "TEST_KEY_A"},
        "ozon_novokshenov": {"client_id": "1002", "api_key": "TEST_KEY_B"},
        "ozon_dmitrieva": {"client_id": "1003", "api_key": "TEST_KEY_C"},
    }


def to_bytes(data):
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


class ReceiverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dir = self.root / "secrets"
        self.dest = self.dir / "cabinets.json"
        self.raw = to_bytes(fake_bundle())

    def test_initial_create_and_no_duplicate_write(self):
        self.assertEqual(receive_bundle(self.raw, destination=self.dest), "CREATED")
        self.assertEqual(self.dest.read_bytes(), self.raw)
        self.assertEqual(self.dest.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.dir.stat().st_mode & 0o777, 0o700)
        self.assertEqual(receive_bundle(self.raw, destination=self.dest), "UNCHANGED")
        self.assertEqual(list(self.dir.glob("*.backup-*")), [])

    def test_change_requires_flag_and_keeps_secure_backup(self):
        receive_bundle(self.raw, destination=self.dest)
        second = fake_bundle()
        second["wb_laser_master"]["token"] = "eyJhbGciOiJub25lIn0.eyJjYWIiOiJSLU5FVyJ9.c2lnUg"
        new = to_bytes(second)
        with self.assertRaisesRegex(CredentialTransferError, "replacement required"):
            receive_bundle(new, destination=self.dest)
        self.assertEqual(self.dest.read_bytes(), self.raw)
        self.assertEqual(receive_bundle(new, destination=self.dest, replace=True), "UPDATED")
        backups = list(self.dir.glob("*.backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), self.raw)
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)

    def test_masked_interactive_validates_nine_fields(self):
        provided = iter([
            "eyJhbGciOiJub25lIn0.eyJjYWIiOiJBIn0.c2lnQQ", "eyJhbGciOiJub25lIn0.eyJjYWIiOiJCIn0.c2lnQg", "eyJhbGciOiJub25lIn0.eyJjYWIiOiJDIn0.c2lnQw",
            "1001", "OZON_LASER_KEY", "1002", "OZON_NOV_KEY", "1003", "OZON_DMITR_KEY"
        ])
        prompts = []
        def fake_hidden_prompt(label):
            prompts.append(label)
            return next(provided)
        with patch("sys.stdin.isatty", return_value=True):
            raw = interactive_bundle(prompt=fake_hidden_prompt)
        values = validate_bundle(raw)
        self.assertEqual(len(prompts), 9)
        self.assertEqual(len(values), 6)
        self.assertEqual(values["wb_laser_master"]["token"], "eyJhbGciOiJub25lIn0.eyJjYWIiOiJBIn0.c2lnQQ")

    def test_masked_interactive_rejects_non_tty_before_prompts(self):
        with patch("sys.stdin.isatty", return_value=False):
            with self.assertRaisesRegex(CredentialTransferError, "real SSH terminal"):
                interactive_bundle(prompt=lambda _: self.fail("should not prompt"))

    def test_canonical_destination_is_isolated_from_hermes(self):
        self.assertEqual(DESTINATION, Path("/etc/msp-marketplace-reports/cabinets.json"))

    def test_readiness_check_with_secure_parent(self):
        self.assertIsNone(check_ready(self.dest))
        self.root.chmod(0o777)
        with self.assertRaisesRegex(CredentialTransferError, "unsafe"):
            check_ready(self.dest)

    def test_rejects_missing_cabinet(self):
        bad = fake_bundle()
        del bad["wb_dmitrieva"]
        with self.assertRaises(CredentialTransferError):
            validate_bundle(to_bytes(bad))

    def test_rejects_extra_field(self):
        bad = fake_bundle()
        bad["ozon_dmitrieva"]["unexpected"] = "secret"
        with self.assertRaises(CredentialTransferError):
            validate_bundle(to_bytes(bad))

    def test_rejects_whitespace_and_oversized_data(self):
        bad = fake_bundle()
        bad["wb_dmitrieva"]["token"] = " TEST "
        with self.assertRaises(CredentialTransferError):
            validate_bundle(to_bytes(bad))
        with self.assertRaises(CredentialTransferError):
            validate_bundle(b"x" * 65537)

    def test_rejects_ctrl_v_character_for_every_field(self):
        bad = fake_bundle()
        for cabinet, credentials in bad.items():
            for field in credentials:
                credentials[field] = "\u0016"
        # JSON escapes a single ASCII control character instead of rejecting it.
        with self.assertRaisesRegex(CredentialTransferError, "control character"):
            receive_bundle(to_bytes(bad), destination=self.dest, replace=True)
        self.assertFalse(self.dest.exists())

    def test_rejects_non_jwt_wb_token(self):
        bad = fake_bundle()
        bad["wb_laser_master"]["token"] = "SHORT_WRONG_VALUE"
        with self.assertRaisesRegex(CredentialTransferError, "JWT-shaped"):
            validate_bundle(to_bytes(bad))

    def test_rejects_nonnumeric_ozon_client_id(self):
        bad = fake_bundle()
        bad["ozon_laser_master"]["client_id"] = "not-a-client-id"
        with self.assertRaisesRegex(CredentialTransferError, "digits"):
            validate_bundle(to_bytes(bad))

    def test_rejects_symlinked_target(self):
        self.dir.mkdir(mode=0o700)
        other = self.root / "other.json"
        other.write_bytes(b"original")
        self.dest.symlink_to(other)
        with self.assertRaises(CredentialTransferError):
            receive_bundle(self.raw, destination=self.dest)
        self.assertEqual(other.read_bytes(), b"original")

    def test_rejects_insecure_parent(self):
        self.root.chmod(0o777)
        with self.assertRaises(CredentialTransferError):
            receive_bundle(self.raw, destination=self.dest)


if __name__ == "__main__":
    unittest.main()
