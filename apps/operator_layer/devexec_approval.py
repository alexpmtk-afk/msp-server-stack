"""Review candidate: root-administered, single-operation-per-block approvals.

No approval creation API is exposed to Hermes. Missing/stale/mismatched grants
always deny. Not deployed to REMOTE by this package.
"""
import hashlib
import json
import os
import re
import stat
import time
from pathlib import Path

GRANT_DIR = Path('/etc/hermes-devexec-grants')
MUTATIONS = frozenset({'dev.write_file', 'dev.apply_patch', 'dev.run_tests', 'dev.git_add', 'dev.git_commit'})
HEX64 = re.compile(r'^[0-9a-f]{64}$')
TASK_ID = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')


def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def block_hash(block):
    return hashlib.sha256(canonical(block)).hexdigest()


def check_context(context):
    if not isinstance(context, dict) or context.get('requires_decomposition'):
        raise ValueError('NOT_APPROVED')
    task = context.get('task_id')
    index = context.get('current_block')
    block = context.get('block')
    if not isinstance(task, str) or not TASK_ID.fullmatch(task) or type(index) is not int or index < 0 or not isinstance(block, dict):
        raise ValueError('NOT_APPROVED')
    if block.get('acceptance') != ['verified']:
        raise ValueError('NOT_APPROVED')
    ops = block.get('allowed_mutations')
    if not isinstance(ops, list) or len(ops) != 1 or ops[0] not in MUTATIONS:
        raise ValueError('NOT_APPROVED')
    return task, index, ops[0]


def relative(path):
    if not isinstance(path, str) or not path or len(path) > 512 or '\\' in path or '\x00' in path:
        raise ValueError('INVALID_PATH')
    chunks = path.split('/')
    if path.startswith('/') or any(p in ('', '.', '..', '.git', '.ssh', '.env', 'secrets', 'credentials', '.codex', '.hermes') or p.endswith(('.pem', '.key')) for p in chunks):
        raise ValueError('INVALID_PATH')
    return path


class GrantStore:
    def __init__(self, directory=GRANT_DIR, *, trusted_uid=0):
        self.directory = Path(directory)
        self.trusted_uids = frozenset(trusted_uid) if isinstance(trusted_uid, (tuple, list, set, frozenset)) else frozenset({trusted_uid})

    def read(self, context, *, now=None, allow_expired=False):
        task, index, operation = check_context(context)
        # Protect every parent, not only the final file, against symlink swaps.
        directory = self.directory
        if not directory.is_absolute():
            raise ValueError('UNTRUSTED_GRANT_DIR')
        fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        try:
            parts = directory.parts[1:]
            for component in parts:
                next_fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd)
                fd = next_fd
                st = os.fstat(fd)
                if st.st_uid not in self.trusted_uids or st.st_mode & 0o022 or not stat.S_ISDIR(st.st_mode):
                    raise ValueError('UNTRUSTED_GRANT_DIR')
            name = task + '.json'
            grant_fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            try:
                st = os.fstat(grant_fd)
                if st.st_uid not in self.trusted_uids or st.st_mode & 0o022 or not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_size > 8192:
                    raise ValueError('UNTRUSTED_GRANT')
                raw = os.read(grant_fd, 8193)
            finally:
                os.close(grant_fd)
        except OSError as exc:
            raise ValueError('APPROVAL_NOT_AVAILABLE') from exc
        finally:
            os.close(fd)
        if len(raw) > 8192:
            raise ValueError('INVALID_GRANT')
        try:
            grant = json.loads(raw)
        except (ValueError, UnicodeError) as exc:
            raise ValueError('INVALID_GRANT') from exc
        keys = {'schema_version', 'task_id', 'block_index', 'block_sha256', 'workspace_id', 'operation', 'paths', 'expires_at'}
        if not isinstance(grant, dict) or set(grant) != keys or type(grant['schema_version']) is not int or grant['schema_version'] != 1:
            raise ValueError('INVALID_GRANT')
        now = time.time() if now is None else now
        if (grant['task_id'] != task or type(grant['block_index']) is not int or grant['block_index'] != index
                or grant['block_sha256'] != block_hash(context['block']) or grant['workspace_id'] != 'operator'
                or grant['operation'] != operation or type(grant['expires_at']) not in (int, float)
                or not (grant['expires_at'] <= now + 3600 if allow_expired else now < grant['expires_at'] <= now + 3600)):
            raise ValueError('APPROVAL_MISMATCH')
        paths = grant['paths']
        if not isinstance(paths, list) or not 1 <= len(paths) <= 32 or len(set(paths)) != len(paths):
            raise ValueError('INVALID_GRANT')
        for path in paths:
            relative(path)
        if operation in ('dev.write_file','dev.apply_patch') and len(paths) != 1:
            raise ValueError('INVALID_GRANT')
        return grant
