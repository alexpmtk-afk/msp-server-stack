"""Temporarily use the installed finance executor for a single Ozon FINAL read."""
import fcntl
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import pwd
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
STATE = Path('/opt/mcp/data/msp-marketplace-reports/ozon-pilot-20261110')
ARCHIVE = STATE.parent
SERVICE = 'msp-wb-pilot.service'
DROP = Path('/run/systemd/system/msp-wb-pilot.service.d/91-ozon-final-pilot.conf')
ENV = Path('/etc/msp-marketplace-reports-executor/redis-runtime.env')
MASTER = Path('/etc/msp-marketplace-reports/cabinets.json')
RESULT = Path('/var/lib/msp-finance-control/results/ozon-dmitrieva-2026-01-pilot.json')

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
    raw = run(['/usr/bin/systemctl', 'show', SERVICE, '-p', 'ActiveState', '-p', 'PrivateNetwork', '-p', 'DropInPaths']).decode()
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

def preflight():
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
    if sha(synthetic.read_bytes()) != old['synthetic_probe_sha256']:
        raise ValueError('accepted Redis evidence drift')
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
    status = show()
    if status['ActiveState'] not in ('inactive', 'failed') or status['DropInPaths'] or status['PrivateNetwork'] != 'yes':
        raise ValueError('executor busy or has unknown controls')
    for p in (STATE, RESULT, DROP, ROOT / 'cabinets.json', ROOT / 'approval.json'):
        if p.exists() or p.is_symlink():
            raise ValueError('prior or partial pilot exists; reconcile first')
    account = pwd.getpwnam('msp-reports')
    if (account.pw_uid, account.pw_gid) != (995, 985):
        raise ValueError('executor identity drift')
    trust(ARCHIVE, 0o711, account.pw_uid)
    trust(MASTER, 0o600)
    all_credentials = json.loads(MASTER.read_bytes())
    cred = all_credentials.get('ozon_dmitrieva')
    if not isinstance(cred, dict) or any(not isinstance(cred.get(k), str) or not cred[k].strip() for k in ('client_id', 'api_key')):
        raise ValueError('selected Ozon credentials unavailable')
    if not cred['client_id'].isascii() or not cred['client_id'].isdecimal():
        raise ValueError('Ozon quota identity unavailable')
    # Never expose other cabinets or unrelated metadata to the executor.
    minimal = {'ozon_dmitrieva': {k: cred[k] for k in ('client_id', 'api_key')}}
    addresses = {str(ipaddress.ip_address(x[4][0])) for x in socket.getaddrinfo('api-seller.ozon.ru', 443, type=socket.SOCK_STREAM)}
    if not addresses or len(addresses) > 32 or any(not ipaddress.ip_address(x).is_global for x in addresses):
        raise ValueError('provider DNS bounds')
    dns = {str(ipaddress.ip_address(l.split()[1])) for l in Path('/etc/resolv.conf').read_text().splitlines() if l.split()[:1] == ['nameserver']}
    if not dns or len(dns) > 6:
        raise ValueError('DNS resolver inventory')
    allow = [x + ('/32' if ipaddress.ip_address(x).version == 4 else '/128') for x in sorted(addresses | dns | {'127.0.0.1'})]
    return minimal, allow

def execute():
    if os.geteuid() != 0:
        raise PermissionError('root console required')
    verify_payload()
    lockpath = Path('/var/lib/msp-finance-control/controller.lock')
    trust(lockpath, 0o600)
    with lockpath.open('rb') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        minimal, allow = preflight()
        # All unknown-target checks above precede mutation.
        os.mkdir(STATE, 0o711)
        os.chown(STATE, 995, 985)
        os.chmod(STATE, 0o711)
        syncdir(ARCHIVE)
        credential_raw = doc(minimal)
        save(ROOT / 'cabinets.json', credential_raw, 0o640, 985)
        # PLAN is data; do not import the network-capable worker in root.
        plan = {'cabinet': 'ozon_dmitrieva', 'year': 2026, 'month': 1,
                'path': '/v1/finance/realization/posting', 'max_send_entries': 1}
        save(ROOT / 'approval.json', doc({'plan': plan, 'expires_epoch': time.time() + 300}), 0o644)
        drop = ('[Service]\nPrivateNetwork=no\nEnvironmentFile=' + str(ENV) + '\n'
            'Environment=MARKETPLACE_REQUIRE_REDIS=1 MSP_REPORTS_SHARED_QUEUE_VERIFIED=YES\n'
            'Environment=HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= http_proxy= https_proxy= all_proxy=\n'
            'LoadCredential=\nLoadCredential=cabinets.json:' + str(ROOT / 'cabinets.json') + '\n'
            'IPAddressAllow=' + ' '.join(allow) + '\n'
            'ExecStart=\nExecStart=' + str(RUNTIME / 'bin/python') + ' -I -B ' + str(ROOT / 'pilot.py') + '\n'
            'Restart=no\nRuntimeMaxSec=180\nTimeoutStartSec=180\n'
            'StandardOutput=null\nStandardError=null\n').encode()
        if not DROP.parent.exists():
            os.mkdir(DROP.parent, 0o755)
        trust(DROP.parent, 0o755)
        save(DROP, drop, 0o644)
        cleanup = False
        start_attempted = False
        try:
            run(['/usr/bin/systemctl', 'daemon-reload'])
            start_attempted = True
            try:
                run(['/usr/bin/systemctl', 'start', SERVICE], timeout=200)
            except RuntimeError:
                pass  # Worker HOLD is a result, not permission to retry.
        finally:
            # Stop only this owned activation, never another unit or foreign drop-in.
            if sha(DROP.read_bytes()) != sha(drop):
                raise ValueError('activation changed; cleanup requires reconciliation')
            if start_attempted and show()['ActiveState'] not in ('inactive', 'failed'):
                run(['/usr/bin/systemctl', 'stop', SERVICE])
            if show()['ActiveState'] not in ('inactive', 'failed'):
                raise ValueError('executor not inactive')
            DROP.unlink()
            syncdir(DROP.parent)
            run(['/usr/bin/systemctl', 'daemon-reload'])
            restored = show()
            cleanup = restored['PrivateNetwork'] == 'yes' and not restored['DropInPaths']
            if sha((ROOT / 'cabinets.json').read_bytes()) != sha(credential_raw):
                raise ValueError('pilot credential changed')
            (ROOT / 'cabinets.json').unlink()
            syncdir(ROOT)
        worker = STATE / 'worker-result.json'
        if worker.exists():
            st = worker.lstat()
            if not stat.S_ISREG(st.st_mode) or st.st_uid != 995 or st.st_nlink != 1:
                raise ValueError('worker receipt inode')
            result = json.loads(worker.read_bytes())
        else:
            result = {'status': 'HOLD_NO_WORKER_RECEIPT', 'entry_consumed': (STATE / 'entry.json').exists()}
        # Only known fields leave the private executor state.
        allowed = {'status', 'cabinet', 'period', 'rows', 'response_sha256', 'csv_sha256',
                   'provider_http_status', 'max_send_entries', 'annual_coverage_complete',
                   'error_type', 'response_retained', 'entry_consumed', 'frames', 'response_shape'}
        result = {k: v for k, v in result.items() if k in allowed}
        result['temporary_activation_removed'] = cleanup
        result['source_method'] = plan['path']
        result['installed_release'] = str(ROOT)
        save(RESULT, doc(result), 0o644)
        if json.loads(RESULT.read_bytes()) != result:
            raise ValueError('public receipt mismatch')
        print(json.dumps(result, sort_keys=True))
        return 0 if result.get('status') == 'VALIDATED_PILOT_NOT_PUBLISHED' and cleanup else 1

if __name__ == '__main__':
    try:
        raise SystemExit(execute())
    except Exception as exc:
        print(json.dumps({'status': 'HOLD', 'error_type': type(exc).__name__,
                          'frames': [{'file': Path(f.filename).name, 'function': f.name, 'line': f.lineno}
                                     for f in traceback.extract_tb(exc.__traceback__)[-6:]]}))
        raise SystemExit(1)
