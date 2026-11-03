"""Root-only hold/consistent backup/offline restore-check for NEW Redis only.

Never replaces live data, edits credentials, repairs/truncates AOF, starts provider
jobs or resets quota keys. Live restore requires separate operator reconciliation.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import *


def run(args,*,binary=False):
    env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'}
    if binary:env['LD_LIBRARY_PATH']=str(PREFIX/'lib')
    p=subprocess.run(args,capture_output=True,env=env,timeout=120)
    if p.returncode:raise RuntimeError('operation failed')
    return p.stdout


def verified():
    trusted(STATE,mode=0o700);trusted(STATE/'complete.json',mode=0o600)
    receipt=json.loads((STATE/'complete.json').read_text())
    for entry in receipt['files']:
        p=Path(entry['path']);trusted(p,entry['uid'],entry['mode'])
        if sha(p.read_bytes())!=entry['sha256'] or p.stat().st_gid!=entry['gid']:raise ValueError('installed drift')
    for entry in receipt['directories']:
        p=Path(entry['path']);trusted(p,entry['uid'],entry['mode'])
        if p.stat().st_gid!=entry['gid']:raise ValueError('directory group drift')
    return receipt


def snapshot(source,destination,*,uid):
    trusted(source,uid,0o700)
    if destination.exists() or destination.is_symlink():raise ValueError('backup target exists')
    # Inventory everything before copying; no symlink/hardlink or special files.
    files=[]
    for p in source.rglob('*'):
        st=trusted(p,uid)
        if p.is_file():files.append(p)
    destination.mkdir(mode=0o700)
    result=[]
    for p in files:
        rel=p.relative_to(source);dest=destination/rel;dest.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        before=sha(p.read_bytes());write_new(dest,p.read_bytes())
        if sha(dest.read_bytes())!=before or sha(p.read_bytes())!=before:raise ValueError('snapshot changed')
        result.append({'path':str(rel),'sha256':before})
    for d in sorted([p for p in destination.rglob('*') if p.is_dir()]+[destination],key=lambda p:len(p.parts),reverse=True):syncdir(d)
    return result


def main():
    if os.geteuid()!=0:print('ROOT_REQUIRED;NO_CHANGES');return 2
    p=argparse.ArgumentParser();p.add_argument('operation',choices=['status','hold','backup','verify-backup','resume-after-reconcile']);p.add_argument('--name');p.add_argument('--owner-reconciled',action='store_true')
    a=p.parse_args()
    try:
        doc=verified()
        if a.operation=='hold':
            import pwd
            role=pwd.getpwnam(USER)
            hold=CONFIG/'HOLD'
            if hold.exists():trusted(hold,mode=0o640)
            else:write_new(hold,b'STOPPED_FOR_OPERATOR_RECONCILIATION\n',0o640,0,role.pw_gid)
            run(['/usr/bin/systemctl','stop',SERVICE]);print('NEW_REDIS_HELD;PROVIDER_FAIL_CLOSED;DATA_PRESERVED');return 0
        if a.operation=='resume-after-reconcile':
            import pwd
            if not a.owner_reconciled:raise ValueError('explicit operator reconciliation required')
            if Path('/etc/msp-marketplace-reports-executor/approval.json').exists():raise ValueError('provider approval must be withdrawn before recovery')
            provider=run(['/usr/bin/systemctl','show','msp-wb-pilot.service','--property=ActiveState','--value']).strip()
            if provider not in (b'inactive',b'failed'):raise ValueError('provider unit not stopped')
            hold=CONFIG/'HOLD';trusted(hold,mode=0o640)
            if hold.read_bytes()!=b'STOPPED_FOR_OPERATOR_RECONCILIATION\n':raise ValueError('unknown hold')
            guard(DATA,CONFIG/'initialized',CONFIG/'bootstrap-permit',pwd.getpwnam(USER).pw_uid)
            hold.unlink();syncdir(CONFIG)
            run(['/usr/bin/systemctl','start',SERVICE])
            print('ONLY_QUOTA_REDIS_RESUMED;PROVIDER_APPROVAL_REMAINS_ABSENT');return 0
        state=run(['/usr/bin/systemctl','show',SERVICE,'--property=ActiveState','--value']).strip().decode()
        if a.operation=='status':print(json.dumps({'service':SERVICE,'state':state,'files':'MATCH','api_enabled':False}));return 0
        if state not in ('inactive','failed'):raise ValueError('stop only quota Redis before backup/check')
        if not a.name or not re.fullmatch('[A-Za-z0-9_-]{1,64}',a.name):raise ValueError('simple backup name required')
        trusted(BACKUP,mode=0o700)
        import pwd
        uid=pwd.getpwnam(USER).pw_uid
        if a.operation=='backup':
            dest=BACKUP/a.name;rows=snapshot(DATA,dest,uid=uid)
            write_new(dest/'BACKUP.json',json.dumps({'files':rows,'live_restore':'NOT_AUTHORIZED_BY_CHECK'}).encode())
            print('STOPPED_CONSISTENT_BACKUP_HASHES_PASS;NO_CREDENTIAL_BACKUP');return 0
        source=BACKUP/a.name;trusted(source,mode=0o700)
        meta=json.loads((source/'BACKUP.json').read_text())
        target=BACKUP/(a.name+'-verify')
        if target.exists() or target.is_symlink():raise ValueError('verify target exists')
        expected={r['path']:r['sha256'] for r in meta['files']}
        for name,digest in expected.items():
            if name.startswith('/') or any(p in ('','..','.') for p in name.split('/')):raise ValueError('backup path')
            f=source/name;trusted(f)
            if sha(f.read_bytes())!=digest:raise ValueError('backup checksum')
        target.mkdir(mode=0o700)
        for name in expected:
            out=target/name;out.parent.mkdir(parents=True,exist_ok=True,mode=0o700);write_new(out,(source/name).read_bytes())
        manifest=target/'appendonlydir/appendonly.aof.manifest'
        run([str(PREFIX/'bin/redis-check-aof'),str(manifest)],binary=True)
        print('OFFLINE_RESTORE_COPY_HASH_AND_AOF_CHECK_PASS;LIVE_DATA_UNCHANGED;SERVICE_STAYS_HELD');return 0
    except Exception as e:
        print('STOP_OR_UNCERTAIN;ERROR_TYPE='+type(e).__name__);return 1


if __name__=='__main__':raise SystemExit(main())
