"""Reviewed administrator-only bootstrap/migration; never exposed over RPC."""
import json,os,pwd,grp,shutil,subprocess
from pathlib import Path
from .security import protected_file
RUNNER_UNIT='actions.runner.alexpmtk-afk-msp-server-bridge.msp-remote-01.service'
RUNNER_ROOT=Path('/opt/actions-runner/msp-server-bridge')

def runner_plan():return {'user':'msp-runner','supplementary_groups':[],'inaccessible_paths':['/home/hermes','/opt/mcp/secrets','/run/msp-operator'],'root_access':False,'restart_units':[RUNNER_UNIT],'rollback':'restore saved unit/drop-in and ownership hermes after stopping runner'}

def run(*args):return subprocess.run(args,check=True,capture_output=True,text=True,timeout=90).stdout

def ensure_user(name):
    try:return pwd.getpwnam(name)
    except KeyError:run('/usr/sbin/useradd','--system','--user-group','--no-create-home','--home-dir','/nonexistent','--shell','/usr/sbin/nologin',name);return pwd.getpwnam(name)

def migrate_runner():
    if os.getuid()!=0:raise ValueError('administrator_required')
    protected_file(__file__)
    user=ensure_user('msp-runner');state=Path('/var/lib/msp-operator-admin');state.mkdir(mode=0o700,exist_ok=True)
    drop=Path('/etc/systemd/system')/(RUNNER_UNIT+'.d');drop.mkdir(exist_ok=True)
    target=drop/'operator-isolation.conf'
    if target.exists():raise ValueError('runner_migration_already_present')
    # Stop only runner. A deployment window must be chosen with no active bridge job.
    run('/usr/bin/systemctl','stop',RUNNER_UNIT)
    (state/'runner-original-unit.txt').write_text(run('/usr/bin/systemctl','cat',RUNNER_UNIT))
    for p in [RUNNER_ROOT,*RUNNER_ROOT.rglob('*')]:
        if p.is_symlink():continue
        os.chown(p,user.pw_uid,user.pw_gid)
    RUNNER_ROOT.chmod(0o700)
    target.write_text('[Service]\nUser=msp-runner\nGroup=msp-runner\nSupplementaryGroups=\nProtectHome=true\nNoNewPrivileges=true\nKillMode=control-group\nInaccessiblePaths=/home/hermes /opt/mcp/secrets /run/msp-operator\n')
    target.chmod(0o644);run('/usr/bin/systemctl','daemon-reload');run('/usr/bin/systemctl','start',RUNNER_UNIT)
    run('/usr/bin/systemctl','is-active',RUNNER_UNIT)
    for p in ['/home/hermes/.hermes/.env','/home/hermes/.hermes/auth.json','/opt/mcp/secrets','/home/hermes/.codex/config.toml']:
        check=subprocess.run(['/usr/sbin/runuser','-u','msp-runner','--','/usr/bin/test','-r',p])
        if check.returncode==0:raise ValueError('runner_private_access_not_denied')
    return {'status':'local_identity_PASS','live_bridge_acceptance':'REQUIRED','plan':runner_plan()}

def rollback_runner():
    if os.getuid()!=0:raise ValueError('administrator_required')
    protected_file(__file__);run('/usr/bin/systemctl','stop',RUNNER_UNIT)
    user=pwd.getpwnam('hermes')
    for p in [RUNNER_ROOT,*RUNNER_ROOT.rglob('*')]:
        if not p.is_symlink():os.chown(p,user.pw_uid,user.pw_gid)
    RUNNER_ROOT.chmod(0o755)
    p=Path('/etc/systemd/system')/(RUNNER_UNIT+'.d/operator-isolation.conf');p.unlink(missing_ok=True)
    run('/usr/bin/systemctl','daemon-reload');run('/usr/bin/systemctl','start',RUNNER_UNIT)
    return {'rolled_back':True}

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('action',choices=['runner-plan','migrate-runner','rollback-runner']);a=p.parse_args()
    print(json.dumps({'runner-plan':runner_plan,'migrate-runner':migrate_runner,'rollback-runner':rollback_runner}[a.action](),indent=2))
