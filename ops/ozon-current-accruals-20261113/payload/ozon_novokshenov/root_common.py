"""Accepted shared executor primitives for a fixed Ozon accrual capture."""
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import pwd
import re
import socket
import stat
import subprocess
import sys
import time
import traceback
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
ACCEPTED = Path('/opt/mcp/projects/msp-marketplace-reports-releases/control-read-access-20261109')
RUNTIME = Path('/opt/mcp/projects/msp-marketplace-reports-releases/c1fee070e9efa0c925a78f266fdf03cb12a173cf/.venv')
ARCHIVE=Path('/opt/mcp/data/msp-marketplace-reports')
SERVICE='msp-wb-pilot.service'
DROP=Path('/run/systemd/system/msp-wb-pilot.service.d/94-ozon-current-accruals-20261113.conf')
ENV=Path('/etc/msp-marketplace-reports-executor/redis-runtime.env')
MASTER=Path('/etc/msp-marketplace-reports/cabinets.json')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def trust(path, mode=None, uid=0):
    st = path.lstat()
    if stat.S_ISLNK(st.st_mode) or st.st_uid != uid or st.st_mode & 0o022:
        raise ValueError('untrusted inode: ' + path.name)
    if mode is not None and stat.S_IMODE(st.st_mode) != mode:
        raise ValueError('unexpected mode: ' + path.name)
    if not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):
        raise ValueError('unsupported inode')
    if stat.S_ISREG(st.st_mode) and st.st_nlink != 1:
        raise ValueError('hardlink')

def syncdir(path):
    fd = os.open(path, os.O_DIRECTORY | os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

def save(path, raw, mode=0o600, gid=0):
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            stream.write(raw)
            stream.flush()
        os.fchown(fd, 0, gid)
        os.fchmod(fd, mode)
        os.fsync(fd)
    finally:
        os.close(fd)
    syncdir(path.parent)

def doc(value):
    return (json.dumps(value, sort_keys=True, allow_nan=False) + '\n').encode()

def run(args, timeout=30):
    p = subprocess.run(args, capture_output=True, timeout=timeout,
                       env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8'})
    if p.returncode:
        raise RuntimeError('command failed: ' + Path(args[0]).name)
    return p.stdout

def show():
    raw = run(['/usr/bin/systemctl', 'show', SERVICE, '-p', 'ActiveState', '-p', 'PrivateNetwork', '-p', 'DropInPaths', '-p', 'ConditionResult', '-p', 'Result', '-p', 'ExecMainStatus', '-p', 'ExecMainStartTimestamp']).decode()
    return dict(line.split('=', 1) for line in raw.splitlines() if '=' in line)

def verify_payload():
    for parent in (ROOT, *ROOT.parents):
        trust(parent)
    expected = json.loads((ROOT / 'MANIFEST.json').read_bytes())
    for name, digest in expected.items():
        path = ROOT / name
        if Path(name).is_absolute() or '..' in Path(name).parts:
            raise ValueError('unsafe manifest')
        trust(path)
        if sha(path.read_bytes()) != digest:
            raise ValueError('payload hash mismatch')

def verify_synthetic(raw, expected_probe_hash):
    """Match the installed supervisor's probe-origin AND acceptance contract.

    synthetic_probe_sha256 identifies the tested probe program, not the JSON
    receipt bytes. Receipt formatting/timestamps are not that program's digest.
    """
    def unique(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate evidence key')
            result[key] = value
        return result
    evidence = json.loads(raw, object_pairs_hook=unique)
    if not isinstance(evidence, dict) or evidence.get('probe_sha256') != expected_probe_hash:
        raise ValueError('synthetic evidence origin')
    expected = {'synthetic_quota': 'PASS', 'clients': 2, 'keys': 4,
                'ttl_ceiling_seconds': 715, 'provider_calls': 0,
                'live_seller_keys_touched': 0, 'api_enabled': False}
    result = evidence.get('result')
    if not isinstance(result, dict) or any(type(result.get(k)) is not type(v) or result[k] != v for k, v in expected.items()):
        raise ValueError('synthetic acceptance evidence')

def unit_condition_override(approval, archive=ARCHIVE):
    # Replace WB's approval condition with this attempt's own root approval.
    # Empty condition assignment resets the condition list; explicitly retain
    # the original archive-directory guard, not only the new approval guard.
    return ('[Unit]\nConditionPathExists=\nConditionPathIsDirectory=' + str(archive)
            + '\nConditionPathExists=' + str(approval) + '\n')

def prepare_drop_directory(path, *, recovering):
    if not path.exists():
        os.mkdir(path, 0o755)
        # mkdir's mode is masked by umask077; set the final mode explicitly.
        os.chmod(path, 0o755)
    else:
        trust(path)
        if any(path.iterdir()):
            raise ValueError('nonempty activation directory')
        if stat.S_IMODE(path.stat().st_mode) == 0o700 and recovering:
            os.chmod(path, 0o755)  # literal known empty directory only
    trust(path, 0o755)
    syncdir(path)
    syncdir(path.parent)

def validate_platform():
    assets = json.loads((ROOT / 'accepted-assets.json').read_bytes())
    if sha((ACCEPTED / 'assets.json').read_bytes()) != assets['accepted_assets_sha256']:
        raise ValueError('accepted assets changed')
    old = json.loads((ACCEPTED / 'assets.json').read_bytes())
    unit = Path('/etc/systemd/system') / SERVICE
    trust(unit)
    if sha(unit.read_bytes()) != old['base_unit_sha256']:
        raise ValueError('finance unit drift')
    if sha(Path('/usr/bin/python3').resolve().read_bytes()) != old['python_sha256']:
        raise ValueError('interpreter drift')
    for name, digest in old['runtime_files'].items():
        path = RUNTIME / name
        trust(path)
        if sha(path.read_bytes()) != digest:
            raise ValueError('runtime drift')
    for name, target in old['runtime_links'].items():
        path = RUNTIME / name
        if not path.is_symlink() or os.readlink(path) != target or path.lstat().st_uid != 0:
            raise ValueError('runtime link drift')
    synthetic = Path('/var/lib/msp-quota-probe-i8kqe69o/result.json')
    trust(synthetic)
    verify_synthetic(synthetic.read_bytes(), old['synthetic_probe_sha256'])
    if run(['/usr/bin/systemctl', 'is-active', 'msp-quota-redis.service']).strip() != b'active':
        raise ValueError('quota service inactive')
    trust(ENV, 0o600)
    pairs = {}
    for line in ENV.read_text().splitlines():
        k, sep, v = line.partition('=')
        if not sep or k in pairs or k not in ('MARKETPLACE_MCP_REDIS_URL', 'MARKETPLACE_REQUIRE_REDIS') or any(c in v for c in '\\"\'\r\x00'):
            raise ValueError('Redis environment format')
        pairs[k] = v
    if pairs.get('MARKETPLACE_REQUIRE_REDIS') != '1':
        raise ValueError('Redis required')
    u = urlsplit(pairs.get('MARKETPLACE_MCP_REDIS_URL', ''))
    if (u.scheme, u.hostname, u.port, u.path, u.username) != ('redis', '127.0.0.1', 16379, '/0', 'quota_runtime') or not u.password or u.query or u.fragment:
        raise ValueError('approved Redis target required')
