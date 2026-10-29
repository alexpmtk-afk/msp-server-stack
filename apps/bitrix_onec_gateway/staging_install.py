"""Install a TEST-ONLY loopback gateway as an unprivileged user systemd service.

No sudo, no nginx, no public proxy, no Bitrix or OneC connectivity.
Never print generated credentials. Requires explicit workflow execution.
"""
from __future__ import annotations

import os
import re
import secrets
import shutil
import socket
import subprocess
from pathlib import Path

UNIT = "bitrix-onec-gateway-staging.service"
PORT = 9794
MEMBER = "STAGING_ONLY_20261029"


def run(*args):
    result = subprocess.run(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            timeout=25, check=False)
    if result.returncode != 0:
        action = "UNKNOWN"
        if "daemon-reload" in args:
            action = "RELOAD"
        elif "enable" in args:
            action = "ENABLE"
        elif "is-active" in args:
            action = "ACTIVE"
        raise RuntimeError("SYSTEMD_" + action + "_FAILED")
    return result


def main():
    os.umask(0o077)
    home = Path.home().resolve()
    if home == Path("/") or not str(home).startswith("/home/"):
        raise RuntimeError("NOT_UNPRIVILEGED_HOME")
    code_dir = home / ".local/share/bitrix-onec-gateway-staging"
    db_dir = home / ".local/state/bitrix-onec-gateway-staging"
    conf_dir = home / ".config/bitrix-onec-gateway-staging"
    unit_dir = home / ".config/systemd/user"
    source = (Path(__file__).resolve().parent / "gateway.py")
    if not source.is_file():
        raise RuntimeError("GATEWAY_SOURCE_MISSING")
    # Do not replace any existing service not created by this installer.
    unit_path = unit_dir / UNIT
    if unit_path.exists():
        contents = unit_path.read_text(encoding="utf-8")
        if "Bitrix OneC STAGING ONLY" not in contents or str(code_dir) not in contents:
            raise RuntimeError("UNRECOGNIZED_EXISTING_UNIT")
    elif not unit_dir.is_dir() or not os.access(unit_dir, os.W_OK):
        raise RuntimeError("USER_SYSTEMD_NOT_WRITABLE")
    if not unit_path.exists():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            if sock.connect_ex(("127.0.0.1", PORT)) == 0:
                raise RuntimeError("STAGING_PORT_ALREADY_USED")
    for folder in (code_dir, db_dir, conf_dir):
        if folder.is_symlink():
            raise RuntimeError("SYMLINK_DIRECTORY")
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        folder.chmod(0o700)
    target = code_dir / "gateway.py"
    if target.is_symlink():
        raise RuntimeError("SYMLINK_GATEWAY")
    shutil.copyfile(source, target)
    target.chmod(0o600)
    envfile = conf_dir / "gateway.env"
    if envfile.is_symlink():
        raise RuntimeError("SYMLINK_SECRETS")
    created_secrets = False
    if not envfile.exists():
        app_key = secrets.token_urlsafe(48)
        srv_key = secrets.token_urlsafe(48)
        content = (
            "B24_GW_APP_HMAC_KEY=" + app_key + "\n"
            "B24_GW_SRV_BEARER=" + srv_key + "\n"
            "B24_GW_MEMBER_ID=" + MEMBER + "\n"
            "B24_GW_DB=" + str(db_dir / "commands.sqlite3") + "\n"
            "B24_GW_PORT=" + str(PORT) + "\n"
        )
        # Exclusive creation to prevent overwriting an existing secret.
        fd = os.open(str(envfile), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="ascii") as handle:
            handle.write(content)
        created_secrets = True
    envfile.chmod(0o600)
    # Verify current config is staging-only; refuse replacing real deployment.
    settings = {}
    for line in envfile.read_text(encoding="ascii").splitlines():
        name, sep, value = line.partition("=")
        if not sep:
            raise RuntimeError("INVALID_ENV_FILE")
        settings[name] = value
    if settings.get("B24_GW_MEMBER_ID") != MEMBER or settings.get("B24_GW_PORT") != str(PORT):
        raise RuntimeError("NOT_STAGING_CREDENTIALS")
    if settings.get("B24_GW_DB") != str(db_dir / "commands.sqlite3"):
        raise RuntimeError("WRONG_STAGING_DATABASE")
    if (len(settings.get("B24_GW_APP_HMAC_KEY", "")) < 48 or
        len(settings.get("B24_GW_SRV_BEARER", "")) < 48):
        raise RuntimeError("INVALID_CREDENTIALS")
    unit = f"""# Bitrix OneC STAGING ONLY: loopback and synthetic requests, not live CRM.
[Unit]
Description=Bitrix OneC STAGING ONLY - local command queue
After=network.target

[Service]
Type=simple
WorkingDirectory={code_dir}
EnvironmentFile={envfile}
ExecStart=/usr/bin/python3 -I {target}
Restart=on-failure
RestartSec=3
UMask=0077
NoNewPrivileges=yes
PrivateTmp=yes
RestrictSUIDSGID=yes
LockPersonality=yes
LimitNOFILE=256
MemoryMax=180M
TasksMax=32

[Install]
WantedBy=default.target
"""
    if not unit_path.exists():
        fd = os.open(str(unit_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(unit)
    unit_path.chmod(0o600)
    run("systemctl", "--user", "daemon-reload")
    run("systemctl", "--user", "enable", "--now", UNIT)
    # Prevent false claims: verify the unit is active and responds only on loopback.
    run("systemctl", "--user", "is-active", "--quiet", UNIT)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(2)
        if sock.connect_ex(("127.0.0.1", PORT)) != 0:
            raise RuntimeError("STAGING_LISTENER_NOT_READY")
    print("B24_GATEWAY_STAGING_INSTALL")
    print("MEMBER_SCOPE=STAGING_ONLY")
    print("SYSTEMD_USER_SERVICE=ACTIVE")
    print("LISTENER=LOOPBACK_9794")
    print("SECRETS_CREATED=" + ("YES" if created_secrets else "NO"))
    print("EXTERNAL_HTTPS=NOT_CONFIGURED")
    print("ONEC_WRITES=0")
    print("CRM_WRITES=0")
    print("RESULT=PASS")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("B24_GATEWAY_STAGING_INSTALL")
        print("RESULT=FAIL")
        print("ERROR_TYPE=" + type(exc).__name__)
        allowed = {"NOT_UNPRIVILEGED_HOME","GATEWAY_SOURCE_MISSING",
                   "UNRECOGNIZED_EXISTING_UNIT","USER_SYSTEMD_NOT_WRITABLE",
                   "STAGING_PORT_ALREADY_USED","SYMLINK_DIRECTORY",
                   "SYMLINK_GATEWAY","SYMLINK_SECRETS","INVALID_ENV_FILE",
                   "NOT_STAGING_CREDENTIALS","WRONG_STAGING_DATABASE",
                   "INVALID_CREDENTIALS","STAGING_LISTENER_NOT_READY",
                   "SYSTEMD_RELOAD_FAILED","SYSTEMD_ENABLE_FAILED",
                   "SYSTEMD_ACTIVE_FAILED","SYSTEMD_UNKNOWN_FAILED"}
        print("ERROR_CODE=" + (str(exc) if str(exc) in allowed else "UNCLASSIFIED"))
        try:
            proc = subprocess.run(["systemctl","--user","show",UNIT,
                    "-p","LoadState","-p","ActiveState","-p","Result",
                    "-p","ExecMainStatus","--no-pager"],capture_output=True,
                    text=True,timeout=5)
            if proc.returncode == 0:
                for item in proc.stdout.splitlines():
                    key, _, val = item.partition("=")
                    if key in ("LoadState","ActiveState","Result","ExecMainStatus") and re.fullmatch(r"[A-Za-z0-9_-]{1,60}",val):
                        print("SERVICE_"+key.upper()+"="+val)
        except Exception:
            pass
        raise SystemExit(1)
