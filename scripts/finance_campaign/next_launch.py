"""Root-owned immutable history release plus first bounded existing-unit run.
Completed provisioning, accepted pilot and runtime remain untouched.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import types

PACKAGE = {}  # BUILD_PACKAGE

def digest(raw):return hashlib.sha256(raw).hexdigest()

def install_release(core):
    root=Path(PACKAGE['release']);core.parents(root.parent)
    files={n:base64.b64decode(v) for n,v in PACKAGE['files'].items()}
    if any(digest(v)!=PACKAGE['hashes'][n] for n,v in files.items()):raise ValueError('release payload integrity')
    for name in files:
        p=Path(name)
        if p.is_absolute() or '..' in p.parts or not name.startswith(('apps/','worker.py','templates/')):raise ValueError('unsafe release member')
    def verify(folder):
        core.parents(folder)
        if any(p.is_symlink() for p in folder.rglob('*')):raise ValueError('release symlink forbidden')
        actual={str(p.relative_to(folder)) for p in folder.rglob('*') if not p.is_dir()}
        if actual!=set(files):raise ValueError('existing history release differs; preserve for review')
        for n,raw in files.items():
            p=folder/n;core.parents(p.parent);core.trusted(p,mode=0o644)
            if digest(p.read_bytes())!=PACKAGE['hashes'][n]:raise ValueError('immutable release drift')
    if root.exists() or root.is_symlink():verify(root);return
    # Staging is intentionally retained after failure; no recursive cleanup or rollback of data.
    staging=root.with_name(root.name+'.staging')
    if staging.exists() or staging.is_symlink():raise ValueError('partial release requires review')
    staging.mkdir(mode=0o755);os.chmod(staging,0o755)
    for n,raw in sorted(files.items()):
        p=staging/n;p.parent.mkdir(parents=True,exist_ok=True)
        # Only new release directories; never chmod an existing runtime/data directory.
        for directory in [p.parent,*p.parent.parents]:
            if directory==staging.parent:break
            os.chmod(directory,0o755)
        core.write_new(p,raw,0o644)
    verify(staging)
    for directory in sorted((p for p in staging.rglob('*') if p.is_dir()),key=lambda p:len(p.parts),reverse=True):
        core.syncdir(directory)
    core.syncdir(staging)
    os.rename(staging,root);core.syncdir(root.parent);verify(root)

def setup():
    raw=base64.b64decode(PACKAGE['core_base64'])
    if digest(raw)!=PACKAGE['core_sha256']:raise ValueError('reviewed supervisor integrity')
    core=types.ModuleType('reviewed_pilot_supervisor');core.__file__=__file__
    exec(compile(raw,'<reviewed pilot supervisor>','exec'),core.__dict__)
    core.ASSETS=PACKAGE['accepted_assets']
    core.STATE=Path('/var/lib/msp-wb-history-next-865431404')
    core.RESULT_NAME='wb-history-next-865431404.json'
    core.PLAN=PACKAGE['batch']
    old_preflight=core.preflight;old_plan={'schema':1,'cabinet':'wb_laser_master','year':2026,'report_id':883801632,'report_type':1,'max_send_entries':3}
    def preflight():
        batch=core.PLAN;core.PLAN=old_plan
        # Permit accepted E event evidence only for the original preflight, not E recovery.
        core.ASSETS['recovery']=True
        try:guards,summary=old_preflight()
        finally:core.PLAN=batch;core.ASSETS.pop('recovery',None)
        receipt=Path('/opt/mcp/report-run-results/wb-883801632-E-recovery1.json')
        core.parents(receipt.parent);core.trusted(receipt,mode=0o644)
        accepted=core.strict_json(receipt.read_bytes())
        o=accepted.get('outcome',{})
        if (accepted.get('status')!='PASS' or accepted.get('api_enabled_after_run') is not False
            or o.get('report_id')!=883801632 or o.get('report_type')!=1 or o.get('rows')!=841
            or o.get('report_detail_complete') is not True or o.get('executor',{}).get('send_entries')!=2):raise ValueError('accepted pilot receipt mismatch')
        previous=Path('/opt/mcp/report-run-results/wb-history-october-first.json')
        core.parents(previous.parent);core.trusted(previous,mode=0o644)
        result=core.strict_json(previous.read_bytes());r=result.get('outcome',{}).get('receipt',{})
        if result.get('status')!='PASS' or result.get('api_enabled_after_run') is not False or r.get('report_id')!=883801636 or r.get('rows')!=46 or r.get('terminal_http_status')!=204 or r.get('verified') is not True:
            raise ValueError('completed buyout receipt mismatch')
        install_release(core)
        return guards,{**summary,'accepted_report_skipped':883801632,'history_release':PACKAGE['release']}
    core.preflight=preflight
    # Fixed installed worker, not a writable checkout or a second service/scheduler.
    old_dropin=core.dropin_text
    def dropin(program,allow):
        result=old_dropin(program,allow)
        # Keep the same runtime; load source exclusively from verified new release.
        return result.replace(str(program).encode(),str(Path(PACKAGE['release'])/'worker.py').encode())
    core.dropin_text=dropin
    original_approval=core.write_approval
    def approval(raw):
        original_approval(raw)
        args=['/usr/bin/systemd-run','--quiet','--wait','--pipe','--collect','--unit=msp-wb-history-next-readcheck',
              '-p','User=msp-reports','-p','Group=msp-reports','-p','NoNewPrivileges=yes',
              '-p','CapabilityBoundingSet=','-p','ProtectSystem=strict','-p','ProtectHome=yes',
              '-p','PrivateNetwork=yes','-p','IPAddressDeny=any','-p','RuntimeMaxSec=20',
              str(core.RELEASE/'.venv/bin/python'),'-I','-B',str(Path(PACKAGE['release'])/'worker.py'),'--check-approval-only']
        result=core.strict_json(core.run(args,timeout=30))
        if result!={'approval_read':'PASS','uid':995,'gid':985,'provider_calls':0}:raise ValueError('actual UID release/auth readcheck failed')
        core.write_new(core.STATE/'actual-uid-release-read.json',core.encoded(result))
    core.write_approval=approval
    return core

def main():
    if os.geteuid()!=0:print('ROOT_REQUIRED;NO_CHANGES');return 2
    return setup().main()

if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({'status':'STOP_OR_UNCERTAIN','error_type':type(exc).__name__,'auto_retry':False}));raise SystemExit(1)
