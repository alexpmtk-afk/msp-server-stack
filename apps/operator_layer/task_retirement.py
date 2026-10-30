"""Manual, opt-in retirement of idle BLOCKED tasks. Never calls a runtime/API.

Dry-run opens SQLite read-only. Apply requires an idle worker lifetime lock,
then task locks and a SQLite write fence. Original records remain in SQLite;
private verified backup/history files precede one atomic retirement transaction.
"""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path
from .tasks import stamp


def _safe_file(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError('unsafe_file')
    st = path.stat()
    if st.st_uid != os.getuid() or st.st_mode & 0o077:
        raise ValueError('unsafe_permissions')


def _read_only(path):
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=5)
    db.execute('PRAGMA query_only=ON')
    return db


def _inspect(db, ids):
    retired = []
    for tid in ids:
        tomb = db.execute('SELECT state,retry_allowed FROM recovery_tombstones WHERE task_id=?', (tid,)).fetchone()
        if tomb:
            if tomb != ('ARCHIVED', 0):
                raise ValueError('other_quarantine_present')
            if not db.execute("SELECT 1 FROM sqlite_master WHERE name='archived_tasks' AND type='table'").fetchone():
                raise ValueError('archive_missing')
            if not db.execute('SELECT 1 FROM archived_tasks WHERE task_id=?', (tid,)).fetchone():
                raise ValueError('archive_missing')
            row = db.execute('SELECT body FROM tasks WHERE id=?', (tid,)).fetchone()
            if row and json.loads(row[0]).get('status') != 'ARCHIVED':
                raise ValueError('retirement_state_mismatch')
            if db.execute('SELECT 1 FROM task_queue WHERE task=?', (tid,)).fetchone():
                raise ValueError('retirement_state_mismatch')
            retired.append(tid)
    if retired:
        if len(retired) != len(ids):
            raise ValueError('mixed_retirement_batch')
        return None
    records = []
    for tid in ids:
        row = db.execute('SELECT body FROM tasks WHERE id=?', (tid,)).fetchone()
        if not row:
            raise ValueError('unknown_task')
        body = json.loads(row[0])
        if body.get('status') != 'BLOCKED' or body.get('lease'):
            raise ValueError('task_not_idle_blocked')
        for table, error in [('task_executions', 'execution_present'), ('operations', 'operation_present'), ('outbox', 'outbox_present')]:
            if db.execute(f'SELECT 1 FROM {table} WHERE task=?', (tid,)).fetchone():
                raise ValueError(error)
        q = db.execute('SELECT state,worker,token,lease_expires,request FROM task_queue WHERE task=?', (tid,)).fetchone()
        if q and q[:4] != ('BLOCKED', None, None, None):
            raise ValueError('queue_not_idle')
        if q and db.execute("SELECT 1 FROM sqlite_master WHERE name='runtime_receipts' AND type='table'").fetchone() and db.execute('SELECT 1 FROM runtime_receipts WHERE request=?', (q[4],)).fetchone():
            raise ValueError('receipt_present')
        if body.get('input_reference'):
            raise ValueError('multipart_link_present')
        for other, raw in db.execute('SELECT id,body FROM tasks'):
            if other not in ids and tid in raw:
                raise ValueError('dependent_task')
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='multipart' AND type='table'").fetchone():
            for (raw,) in db.execute('SELECT body FROM multipart'):
                if tid in raw:
                    raise ValueError('multipart_link_present')
        records.append((tid, row[0]))
    return records


def _write_private(path, value):
    data = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    if path.read_bytes() != data:
        raise ValueError('archive_readback_failed')


def _archive(db_path, db, ids, dest):
    # An existing destination (even an empty directory) is never overwritten.
    if dest.parent.is_symlink() or dest.is_symlink() or dest.parent.resolve() != dest.parent:
        raise ValueError('unsafe_archive_path')
    st = dest.parent.stat()
    if st.st_uid != os.getuid() or st.st_mode & 0o077:
        raise ValueError('unsafe_archive_permissions')
    dest.mkdir(mode=0o700)
    history = {}
    for table, key in [('tasks', 'id'), ('events', 'task'), ('task_queue', 'task'), ('task_queue_events', 'task'), ('task_executions', 'task'), ('operations', 'task'), ('outbox', 'task')]:
        marks = ','.join('?' for _ in ids)
        history[table] = {'columns': [r[1] for r in db.execute(f'PRAGMA table_info({table})')],
                          'rows': db.execute(f'SELECT * FROM {table} WHERE {key} IN ({marks}) ORDER BY rowid', ids).fetchall()}
    _write_private(dest / 'task-history.json', history)
    backup = dest / 'journal-before.sqlite'
    fd = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    os.close(fd)
    # Writer holds BEGIN IMMEDIATE without edits. A second RO connection can
    # take an online snapshot while every competing writer is fenced.
    with contextlib.closing(_read_only(db_path)) as source, contextlib.closing(sqlite3.connect(backup)) as target:
        source.backup(target)
        if target.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('backup_integrity_failed')
        for tid in ids:
            if target.execute('SELECT body FROM tasks WHERE id=?', (tid,)).fetchone() != db.execute('SELECT body FROM tasks WHERE id=?', (tid,)).fetchone():
                raise ValueError('backup_snapshot_mismatch')
    with backup.open('rb') as stream:
        os.fsync(stream.fileno())
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (backup, dest / 'task-history.json')}
    _write_private(dest / 'manifest.json', {'version': 1, 'task_ids': ids, 'files': hashes})
    for name, digest in hashes.items():
        if hashlib.sha256((dest / name).read_bytes()).hexdigest() != digest:
            raise ValueError('archive_hash_mismatch')
    fd = os.open(dest, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    fd = os.open(dest.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return hashes['task-history.json']


def retire(root, task_ids, archive_dir, *, apply=False):
    root = Path(root).absolute()
    if root.is_symlink() or root.resolve() != root or not root.is_dir():
        raise ValueError('unsafe_root')
    st = root.stat()
    if st.st_uid != os.getuid() or st.st_mode & 0o077:
        raise ValueError('unsafe_permissions')
    ids = tuple(task_ids)
    if not ids or len(ids) > 100 or len(ids) != len(set(ids)) or any(not isinstance(t, str) or not re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', t) for t in ids):
        raise ValueError('invalid_task_ids')
    path = root / 'journal.sqlite'
    _safe_file(path)
    with contextlib.closing(_read_only(path)) as db:
        records = _inspect(db, ids)
    if records is None:
        return {'status': 'ALREADY_ARCHIVED', 'count': len(ids)}
    if not apply:
        return {'status': 'PREFLIGHT_PASS', 'count': len(ids)}
    locks = []
    try:
        lock = root / 'worker-service.lock'
        _safe_file(lock)
        fd = os.open(lock, os.O_RDWR | os.O_NOFOLLOW)
        locks.append(fd)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('worker_active') from None
        for tid in sorted(ids):
            fd = os.open(root / (tid + '.lock'), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
            locks.append(fd)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError('task_active') from None
        with contextlib.closing(sqlite3.connect(path, timeout=5)) as db:
            db.execute('PRAGMA synchronous=FULL')
            try:
                db.execute('BEGIN IMMEDIATE')
                records = _inspect(db, ids)
                if records is None:
                    db.rollback()
                    return {'status': 'ALREADY_ARCHIVED', 'count': len(ids)}
                digest = _archive(path, db, ids, Path(archive_dir).absolute())
                db.execute('CREATE TABLE IF NOT EXISTS archived_tasks(task_id TEXT PRIMARY KEY,body TEXT NOT NULL,archived_at TEXT NOT NULL,reason TEXT NOT NULL,archive_sha256 TEXT NOT NULL)')
                now = stamp()
                for tid, raw in records:
                    db.execute('INSERT INTO archived_tasks VALUES(?,?,?,?,?)', (tid, raw, now, 'Explicit owner retirement', digest))
                    db.execute('INSERT INTO recovery_tombstones VALUES(?,?,?,?,?,0,?)', (tid, 'ARCHIVED', 'Explicit owner retirement', now, 'owner-retirement', 'ARCHIVED_NO_RETRY'))
                    body = json.loads(raw)
                    body.update(status='ARCHIVED', updated_at=now, next_action='none; retired by owner', lease=None)
                    db.execute('UPDATE tasks SET body=? WHERE id=?', (json.dumps(body), tid))
                    db.execute('DELETE FROM task_queue WHERE task=?', (tid,))
                    db.execute('INSERT INTO events(task,kind,body) VALUES(?,?,?)', (tid, 'archived', json.dumps({'task_id': tid, 'at': now, 'archive_sha256': digest, 'retry_allowed': False})))
                if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                    raise ValueError('journal_integrity_failed')
                db.commit()
            except BaseException:
                db.rollback()
                raise
        with contextlib.closing(_read_only(path)) as db:
            if _inspect(db, ids) is not None:
                raise ValueError('retirement_readback_failed')
        return {'status': 'ARCHIVED', 'count': len(ids)}
    finally:
        for fd in reversed(locks):
            os.close(fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--task-id', action='append', required=True)
    parser.add_argument('--archive-dir', required=True)
    parser.add_argument('--apply', action='store_true', help='Explicit write; requires stopped existing Worker')
    args = parser.parse_args(argv)
    print(json.dumps(retire(args.root, args.task_id, args.archive_dir, apply=args.apply)))


if __name__ == '__main__':
    main()
