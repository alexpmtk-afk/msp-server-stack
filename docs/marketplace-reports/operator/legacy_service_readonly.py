"""Operator-only READ_ONLY probe; do not run on the already audited new VPS.
No network, application imports, job payloads, credential files or writes.
"""
import hashlib
import json
import os
import socket
import subprocess
from pathlib import Path

SERVICE = 'mcp-marketplaces.service'


def collect():
    if socket.gethostname().casefold() == 'vm-817589':
        return {'status': 'STOP_WRONG_CONSOLE_NEW_VPS', 'service_probe_executed': False}
    result = {'service': SERVICE, 'status': 'NOT_VERIFIED'}
    try:
        probe = subprocess.run(['systemctl', 'show', SERVICE, '--no-pager',
            '--property=LoadState,ActiveState,SubState,User,MainPID,WorkingDirectory'],
            capture_output=True, text=True, timeout=10)
        if probe.returncode:
            return {**result, 'service_probe': 'UNAVAILABLE'}
        data = dict(line.split('=', 1) for line in probe.stdout.splitlines() if '=' in line)
        result['service_state'] = {key: data.get(key, '') for key in
                                  ('LoadState', 'ActiveState', 'SubState', 'User')}
        pid = int(data.get('MainPID', '0'))
        if data.get('LoadState') != 'loaded' or data.get('ActiveState') != 'active' or pid <= 0:
            return {**result, 'status': 'SERVICE_NOT_RUNNING_OR_NOT_FOUND'}
        root = Path(os.readlink('/proc/' + str(pid) + '/cwd'))
        # Do not print arguments, env values, hostname, endpoint or service URL.
        source = root / 'core' / 'archive_queue.py'
        if source.is_file():
            result['queue_source_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
            result['source_location'] = str(source)
        else:
            result['queue_source'] = 'NOT_FOUND_AT_PROCESS_CWD'
        git = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'],
                             capture_output=True, text=True, timeout=10)
        result['checkout_sha_not_loaded_code_proof'] = git.stdout.strip() if git.returncode == 0 else 'NOT_VERIFIED'
        try:
            raw = Path('/proc/' + str(pid) + '/environ').read_bytes()
            env = dict(part.split(b'=', 1) for part in raw.split(b'\0') if b'=' in part)
            names = ('MARKETPLACE_MCP_REDIS_URL', 'MARKETPLACE_MCP_REDIS_HOST',
                     'MARKETPLACE_MCP_REDIS_DB', 'MARKETPLACE_MCP_REDIS_TLS',
                     'MARKETPLACE_MCP_ARCHIVE_BUCKET', 'MARKETPLACE_MCP_ARCHIVE_LOCAL_ROOT')
            result['effective_process_fields_present'] = {name: bool(env.get(name.encode())) for name in names}
            result['backend_selection_flags_only'] = {
                name: env.get(name.encode(), b'').strip().lower() in (b'1', b'true', b'yes', b'on')
                for name in ('MARKETPLACE_MCP_ARCHIVE_DIRECT_GOOGLE', 'MARKETPLACE_MCP_ARCHIVE_LOCAL_DURABLE')}
            result['actual_store_class_and_redis_identity'] = 'NOT_VERIFIED_FROM_FLAGS_ALONE'
        except (PermissionError, FileNotFoundError, ProcessLookupError):
            result['effective_process_fields_present'] = 'NOT_ACCESSIBLE'
        result['status'] = 'RUNNING_SERVICE_OBSERVED_NOT_P01_COMPLETE'
        return result
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {**result, 'status': 'PROBE_UNAVAILABLE_NO_RAW_ERROR'}


if __name__ == '__main__':
    print(json.dumps(collect(), ensure_ascii=False, sort_keys=True))
