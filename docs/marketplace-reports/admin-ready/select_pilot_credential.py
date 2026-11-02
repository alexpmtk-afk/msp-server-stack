"""FUTURE OWNER-APPROVED ROOT ACTION ONLY. Never print secrets.

Reads original cabinets.json without changing it; creates only the pilot copy.
No directory creation, replacement, permissions changes, network or imports of
marketplace applications. Existing destination or sync uncertainty => stop.
"""
import json
import os
import stat
from pathlib import Path

SOURCE = Path('/etc/msp-marketplace-reports')
DESTINATION = Path('/etc/msp-marketplace-reports-pilot')
NAME = 'wb_laser_master.json'


def strict(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise ValueError('duplicate credential JSON key')
        result[k] = v
    return result


def select(raw):
    doc = json.loads(raw, object_pairs_hook=strict)
    entry = doc.get('wb_laser_master') if type(doc) is dict else None
    if type(entry) is not dict or type(entry.get('token')) is not str or not entry['token'].strip():
        raise ValueError('pilot credential missing or malformed')
    return (json.dumps({'wb_laser_master': {'token': entry['token']}},
                       ensure_ascii=False, sort_keys=True, separators=(',', ':'))+'\n').encode()


def private_dir(path, uid):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    st = os.fstat(fd)
    if st.st_uid != uid or stat.S_IMODE(st.st_mode) != 0o700:
        os.close(fd)
        raise ValueError('private directory ownership/mode mismatch')
    return fd


def copy_one(source, destination, *, expected_uid=0):
    """Directories must exist. expected_uid injection is for synthetic tests."""
    src = private_dir(source, expected_uid)
    dst = None
    try:
        fd = os.open('cabinets.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=src)
        try:
            st = os.fstat(fd)
            if (not stat.S_ISREG(st.st_mode) or st.st_uid != expected_uid or st.st_nlink != 1
                    or stat.S_IMODE(st.st_mode) != 0o600 or st.st_size > 65536):
                raise ValueError('source ownership/type/mode/size mismatch')
            raw = os.read(fd, 65537)
            if len(raw) > 65536:
                raise ValueError('source too large')
        finally:
            os.close(fd)
        selected = select(raw)  # Entire parse/selection BEFORE destination writes.
        dst = private_dir(destination, expected_uid)
        fd = os.open(NAME, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=dst)
        try:
            remaining = memoryview(selected)
            while remaining:
                n = os.write(fd, remaining)
                if n <= 0:
                    raise OSError('short credential write')
                remaining = remaining[n:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(dst)
    finally:
        if dst is not None:
            os.close(dst)
        os.close(src)


def root_path(path):
    for part in [path, *path.parents]:
        st = part.lstat()
        if stat.S_ISLNK(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o022:
            raise ValueError('root-controlled path required')


def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--owner-approved-create-pilot-copy', action='store_true')
    args = p.parse_args()
    if os.geteuid() != 0 or not args.owner_approved_create_pilot_copy:
        print('BLOCKED: root and separate owner approval required')
        return 2
    try:
        root_path(SOURCE)
        root_path(DESTINATION)
        copy_one(SOURCE, DESTINATION)
    except Exception as exc:
        # Partial copy may exist; never unlink or overwrite uncertain evidence.
        print('STOP_OR_UNCERTAIN;ERROR_TYPE='+type(exc).__name__)
        return 1
    print('PILOT_COPY_CREATED;CABINETS=1;FIELDS=1;SOURCE_UNCHANGED_BY_DESIGN')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
