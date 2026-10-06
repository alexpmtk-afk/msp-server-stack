#!/usr/bin/env python3
"""Install/update the MPSTATS remote MCP entry in the live Codex configs.

The real MPSTATS token is read only from /opt/mcp/secrets/mpstats.env.
It is never accepted as a CLI argument and must never be printed.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import stat
import tempfile
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

SECRET_FILE = pathlib.Path("/opt/mcp/secrets/mpstats.env")
TARGETS = (
    pathlib.Path("/home/hermes/.codex/config.toml"),
    pathlib.Path("/home/hermes/.codex-dashboard/config.toml"),
)
SECTION = "mcp_servers.mpstats"
ENDPOINT_BASE = "https://mcp.mpstats.io/mcp"


def read_token() -> str:
    raw = SECRET_FILE.read_text(encoding="utf-8")
    token = None
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("MPSTATS_API_TOKEN="):
            token = line.split("=", 1)[1].strip()
            if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):
                token = token[1:-1]
            break
    if not token:
        raise SystemExit("MPSTATS_API_TOKEN is missing or empty in protected secret file")
    if any(ch in token for ch in "\r\n\x00"):
        raise SystemExit("MPSTATS_API_TOKEN contains an invalid control character")
    return token


def remove_section(text: str, section: str) -> str:
    """Remove an existing TOML table and its body until the next table header."""
    lines = text.splitlines(keepends=True)
    start = None
    end = None
    header = f"[{section}]"
    for i, line in enumerate(lines):
        if line.strip() == header:
            start = i
            break
    if start is None:
        return text
    end = len(lines)
    for j in range(start + 1, len(lines)):
        stripped = lines[j].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            end = j
            break
    del lines[start:end]
    return "".join(lines).rstrip() + "\n"


def build_section(token: str) -> str:
    endpoint = ENDPOINT_BASE + "?token=" + quote(token, safe="")
    # The URL itself is intentionally not printed by this script.
    return (
        "\n[mcp_servers.mpstats]\n"
        f'url = "{endpoint}"\n'
        "enabled = true\n"
        "startup_timeout_sec = 30.0\n"
        "tool_timeout_sec = 600.0\n"
    )


def atomic_write(path: pathlib.Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp_name, 0o600)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def main() -> int:
    if not SECRET_FILE.exists():
        raise SystemExit(f"Protected secret file is missing: {SECRET_FILE}")
    st = SECRET_FILE.stat()
    if stat.S_IMODE(st.st_mode) & 0o077:
        raise SystemExit("Protected MPSTATS secret file permissions are too broad; require mode 0600")
    token = read_token()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for path in TARGETS:
        if not path.exists():
            raise SystemExit(f"Codex config is missing: {path}")
        current = path.read_text(encoding="utf-8")
        updated = remove_section(current, SECTION) + build_section(token)

        backup = path.with_name(path.name + f".pre-mpstats.{stamp}.bak")
        shutil.copy2(path, backup)
        os.chmod(backup, 0o600)

        atomic_write(path, updated)

        # Verify only non-secret properties.
        new_text = path.read_text(encoding="utf-8")
        if "[mcp_servers.mpstats]" not in new_text:
            raise SystemExit(f"MPSTATS section missing after write: {path}")
        m = re.search(r'^url\s*=\s*"([^"]+)"', new_text.split("[mcp_servers.mpstats]",1)[1], re.M)
        if not m:
            raise SystemExit(f"MPSTATS URL missing after write: {path}")
        u = urlsplit(m.group(1))
        if u.scheme != "https" or u.netloc != "mcp.mpstats.io" or u.path != "/mcp" or not u.query.startswith("token="):
            raise SystemExit(f"MPSTATS URL shape verification failed: {path}")
        os.chmod(path, 0o600)
        print(f"configured={path} mode=0600 backup={backup.name}")

    print("result=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
