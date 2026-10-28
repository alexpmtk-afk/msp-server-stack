#!/usr/bin/env python3
"""Receive WB/Ozon credentials through authenticated SSH stdin, never argv.

This file is inert until deployed and explicitly executed by an authorized
operator. Root-only destination; no provider calls and no service restarts.
"""
from __future__ import annotations

import argparse
import hmac
import json
import os
import re
import secrets
import stat
import sys
from pathlib import Path

DESTINATION = Path("/etc/msp-marketplace-reports/cabinets.json")
CABINETS = {
    "wb_laser_master": ("token",),
    "wb_novokshenov": ("token",),
    "wb_dmitrieva": ("token",),
    "ozon_laser_master": ("client_id", "api_key"),
    "ozon_novokshenov": ("client_id", "api_key"),
    "ozon_dmitrieva": ("client_id", "api_key"),
}
MAX_BYTES = 65536


class CredentialTransferError(Exception):
    pass


def validate_bundle(raw: bytes) -> dict:
    if not raw or len(raw) > MAX_BYTES:
        raise CredentialTransferError("invalid bundle size")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise CredentialTransferError("invalid JSON structure") from None
    if not isinstance(data, dict) or set(data) != set(CABINETS):
        raise CredentialTransferError("expected exactly six registered cabinets")
    normalized = {}
    for cabinet, required in CABINETS.items():
        supplied = data[cabinet]
        if not isinstance(supplied, dict) or set(supplied) != set(required):
            raise CredentialTransferError("missing or extra credential fields for " + cabinet)
        clean = {}
        for field in required:
            value = supplied[field]
            if not isinstance(value, str) or not 1 <= len(value) <= 8192:
                raise CredentialTransferError("invalid credential format for " + cabinet)
            if value != value.strip() or any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
                raise CredentialTransferError("credential contains whitespace or control character for " + cabinet)
            if cabinet.startswith("wb_") and field == "token":
                if not re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", value):
                    raise CredentialTransferError("WB token is not JWT-shaped for " + cabinet)
            if cabinet.startswith("ozon_") and field == "client_id" and not value.isascii():
                raise CredentialTransferError("Ozon client ID must contain ASCII digits for " + cabinet)
            if cabinet.startswith("ozon_") and field == "client_id" and not value.isdecimal():
                raise CredentialTransferError("Ozon client ID must contain digits for " + cabinet)
            clean[field] = value
        normalized[cabinet] = clean
    return normalized


def _regular(path: Path):
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(metadata.st_mode):
        raise CredentialTransferError("destination is not a regular file")
    if metadata.st_uid != os.geteuid() or metadata.st_mode & 0o077:
        raise CredentialTransferError("existing destination owner/mode unsafe")
    return metadata


def _secure_directory(path: Path):
    parent = path.parent
    try:
        parent_info = parent.lstat()
    except FileNotFoundError:
        raise CredentialTransferError("secrets parent directory absent") from None
    if not stat.S_ISDIR(parent_info.st_mode):
        raise CredentialTransferError("secrets parent directory unsafe")
    if parent_info.st_uid != os.geteuid() or parent_info.st_mode & 0o022:
        raise CredentialTransferError("secrets parent ownership/mode unsafe")
    try:
        info = path.lstat()
    except FileNotFoundError:
        path.mkdir(mode=0o700)
        info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or (info.st_mode & 0o777) != 0o700:
        raise CredentialTransferError("credential directory must be owned and private (0700)")


def check_ready(destination: Path = DESTINATION):
    """Read-only preflight; reject missing/insecure parent before token prompts."""
    destination = Path(destination)
    parent = destination.parent.parent
    try:
        details = parent.lstat()
    except FileNotFoundError:
        raise CredentialTransferError("secrets parent directory absent") from None
    if (not stat.S_ISDIR(details.st_mode)
            or details.st_uid != os.geteuid()
            or details.st_mode & 0o022):
        raise CredentialTransferError("secrets parent directory unsafe")
    try:
        child = destination.parent.lstat()
    except FileNotFoundError:
        child = None
    if child is not None and (not stat.S_ISDIR(child.st_mode)
                              or child.st_uid != os.geteuid()
                              or (child.st_mode & 0o777) != 0o700):
        raise CredentialTransferError("credential directory unsafe")
    _regular(destination)


def _write_exclusive(path: Path, raw: bytes):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(str(path), flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            os.fchmod(f.fileno(), 0o600)
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        try:
            path.unlink()
        except OSError:
            pass
        raise


def receive_bundle(raw: bytes, *, destination: Path = DESTINATION, replace: bool = False) -> str:
    """Install validated credentials; existing values never displayed.

    For tests only, destination may be overridden by the Python caller. The
    CLI intentionally does not accept an arbitrary destination argument.
    """
    validate_bundle(raw)
    destination = Path(destination)
    _secure_directory(destination.parent)
    existing = _regular(destination)
    if existing is not None:
        old = destination.read_bytes()
        if hmac.compare_digest(old, raw):
            return "UNCHANGED"
        if not replace:
            raise CredentialTransferError("existing credentials present; explicit replacement required")
        backup = destination.with_name(destination.name + ".backup-" + secrets.token_hex(8))
        _write_exclusive(backup, old)
    candidate = destination.with_name(".cabinet-incoming-" + secrets.token_hex(12))
    try:
        _write_exclusive(candidate, raw)
        if not hmac.compare_digest(candidate.read_bytes(), raw):
            raise CredentialTransferError("staging verification failed")
        os.replace(candidate, destination)
        fd = os.open(str(destination.parent), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        if not hmac.compare_digest(destination.read_bytes(), raw):
            raise CredentialTransferError("post-publication verification failed")
    finally:
        if candidate.exists():
            candidate.unlink()
    return "UPDATED" if existing is not None else "CREATED"



def interactive_bundle(prompt=None) -> bytes:
    """Collect nine secrets on a real terminal; no shell history or local file."""
    import getpass

    if not sys.stdin.isatty():
        raise CredentialTransferError("interactive input requires a real SSH terminal")
    read_secret = prompt or getpass.getpass
    data = {}
    labels = {
        "wb_laser_master": "WB Лазер-Мастер",
        "wb_novokshenov": "WB Новокшенов",
        "wb_dmitrieva": "WB Дмитриева",
        "ozon_laser_master": "Ozon Лазер-Мастер",
        "ozon_novokshenov": "Ozon Новокшенов",
        "ozon_dmitrieva": "Ozon Дмитриева",
    }
    for cabinet, keys in CABINETS.items():
        fields = {}
        for key in keys:
            value = read_secret("%s — %s: " % (labels[cabinet], key))
            if not isinstance(value, str) or not value or value != value.strip():
                raise CredentialTransferError("empty or malformed credential for " + cabinet)
            fields[key] = value
        data[cabinet] = fields
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    validate_bundle(raw)
    return raw


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Secure 6-cabinet credential receiver")
    parser.add_argument("--check", action="store_true", help="validate receiver readiness only; no secret input")
    parser.add_argument("--interactive", action="store_true", help="enter nine secrets in a hidden SSH terminal")
    parser.add_argument("--replace", action="store_true", help="explicitly allow credential replacement with backup")
    args = parser.parse_args(argv)
    if os.geteuid() != 0:
        print("ERROR=ROOT_REQUIRED", file=sys.stderr)
        return 2
    os.umask(0o077)
    if args.check:
        try:
            check_ready()
        except (CredentialTransferError, OSError) as e:
            message = str(e) if isinstance(e, CredentialTransferError) else "filesystem check failed"
            print("ERROR=" + message, file=sys.stderr)
            return 1
        print("RECEIVER_READY=YES;SECRETS_RECEIVED=NO")
        return 0
    try:
        if args.interactive:
            # Refuse before prompting if a target already exists. Rotation
            # requires a distinct deliberate --replace operation.
            check_ready()
            if DESTINATION.exists() and not args.replace:
                raise CredentialTransferError("credential file already exists; not asking for secrets")
            raw = interactive_bundle()
        else:
            raw = sys.stdin.buffer.read(MAX_BYTES + 1)
        status = receive_bundle(raw, replace=args.replace)
    except (CredentialTransferError, OSError, EOFError, KeyboardInterrupt) as e:
        message = str(e) if isinstance(e, CredentialTransferError) else "filesystem operation failed"
        print("ERROR=" + message, file=sys.stderr)
        return 1
    print("RESULT=" + status + ";CABINETS=6;SECRETS_PRINTED=NO;SERVICES_RESTARTED=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
