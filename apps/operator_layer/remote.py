"""Registered MSP operations. Production entrypoint loads root-owned policy only."""
import hashlib,io,json,os,shutil,stat,subprocess,tarfile,time,urllib.request
from pathlib import Path,PurePosixPath
from .security import fields,ident,sha,lock,protected_file,digest_file
COMPONENT='msp-data-catalog'
ALLOW=('apps/msp_data_sync/','config/msp-data/')

def extract_release(data,destination,commit):
    sha(commit);destination=Path(destination)
    if destination.exists():raise ValueError('release_exists')
    if len(data)>20_000_000:raise ValueError('archive_too_large')
    files={};total=0
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
        for member in archive:
            parts=PurePosixPath(member.name).parts
            if member.name.startswith('/') or '\\' in member.name or '..' in parts or member.issym() or member.islnk() or member.isdev():raise ValueError('unsafe_archive_member')
            if len(parts)<2 or member.isdir():continue
            relative='/'.join(parts[1:])
            if not member.isfile():raise ValueError('unsafe_archive_type')
            if not relative.startswith(ALLOW):continue
            if relative in files or member.size>5_000_000:raise ValueError('invalid_archive_member')
            total+=member.size
            if total>10_000_000:raise ValueError('release_too_large')
            with archive.extractfile(member) as f:files[relative]=f.read()
    if not {'apps/msp_data_sync/sync.py','apps/msp_data_sync/schema.sql','config/msp-data/sync.json'}<=files.keys():raise ValueError('incomplete_release')
    destination.mkdir(mode=0o700)
    for name,content in files.items():
        p=destination/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(content);p.chmod(0o444)
    metadata={'sha':commit,'digests':{n:hashlib.sha256(v).hexdigest() for n,v in files.items()}}
    p=destination/'release.json';p.write_text(json.dumps(metadata));p.chmod(0o444)
    for p in sorted(destination.rglob('*'),reverse=True):
        if p.is_dir():p.chmod(0o555)
    destination.chmod(0o555)
    return metadata

def release_status(path):
    path=Path(path);m=json.loads((path/'release.json').read_text());sha(m['sha'])
    for name,expected in m['digests'].items():
        if name.startswith('/') or '..' in PurePosixPath(name).parts or not name.startswith(ALLOW):raise ValueError('invalid_manifest')
        p=path/name
        if p.is_symlink() or digest_file(p)!=expected:raise ValueError('release_digest_mismatch')
    return m

class PublicReleaseVerifier:
    def __init__(self,policy):self.policy=policy
    def get(self,path):
        class DenyRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*a):raise ValueError('redirect_denied')
        with urllib.request.build_opener(DenyRedirect).open(urllib.request.Request('https://api.github.com/repos/alexpmtk-afk/msp-server-stack'+path,headers={'User-Agent':'MSP-Release-Verifier'}),timeout=20) as r:
            b=r.read(3_000_001)
            if len(b)>3_000_000:raise ValueError('response_too_large')
            return json.loads(b)
    def verify(self,commit):
        sha(commit)
        if self.get('/git/ref/heads/main')['object']['sha']!=commit:raise ValueError('not_exact_canonical_main')
        candidates=[p for p in self.get('/commits/'+commit+'/pulls?per_page=100') if p.get('merged_at') and p.get('merge_commit_sha')==commit and p['base']['ref']=='main']
        if not candidates:raise ValueError('merged_pr_provenance_missing')
        pr=candidates[0];number=str(pr['number']);files=[];reviews=[];checks=[]
        for path,key,out in [('/pulls/'+number+'/files',None,files),('/pulls/'+number+'/reviews',None,reviews),('/commits/'+pr['head']['sha']+'/check-runs','check_runs',checks)]:
            for page in range(1,101):
                j=self.get(path+f'?per_page=100&page={page}');rows=j[key] if key else j;out.extend(rows)
                if len(rows)<100:break
            else:raise ValueError('pagination_limit')
        from .github import merge_gate
        merge_gate(self.policy,{**pr,'state':'open','draft':False},pr['head']['sha'],[x['filename'] for x in files],checks,reviews)
        # Canonical merge commit must also have successful trusted CI, not merely the PR head.
        merged_checks=self.get('/commits/'+commit+'/check-runs?per_page=100')['check_runs']
        merge_gate(self.policy,{'state':'open','draft':False,'head':{'sha':commit},'base':{'ref':'main'}},commit,['apps/msp_data_sync/sync.py'],merged_checks,[])
        return {'sha':commit,'pr':pr['number'],'head_sha':pr['head']['sha'],'ci_verified':True}
    def archive(self,commit):
        class DenyRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*a):raise ValueError('redirect_denied')
        with urllib.request.build_opener(DenyRedirect).open('https://codeload.github.com/alexpmtk-afk/msp-server-stack/tar.gz/'+sha(commit),timeout=30) as r:
            b=r.read(20_000_001)
            if len(b)>20_000_000:raise ValueError('archive_too_large')
            return b

class RemoteBroker:
    REQUIRED={'deploy_component':('component','release_id','expected_current_release','request_id'),'install_registered_service':('component','release_id','request_id'),'enable_registered_timer':('component','request_id'),'restart_registered_service':('component','request_id'),'registered_service_status':('component',),'registered_service_logs':('component',),'backup_registered_database':('component','request_id'),'restore_registered_database':('component','backup_id','maintenance_grant','request_id'),'operation_status':('request_id',)}
    def __init__(self,policy,verifier,journal):self.policy=policy;self.verifier=verifier;self.journal=journal
    def execute(self,op,p):
        if op=='capability_status':
            fields(p,('capability',));allowed=p['capability'] in ('remote.deploy','remote.systemd_admin','remote.backup','remote.restore')
            return {'tool_visible':True,'authenticated':True,'authorized':allowed and self.policy.get('enabled',False),'acceptance_verified':False,'reason_code':'registered_policy_readiness_only'}
        if op not in self.REQUIRED:raise ValueError('operation_not_allowed')
        fields(p,self.REQUIRED[op])
        if 'component' in p and p['component']!=COMPONENT:raise ValueError('component_not_allowed')
        if not self.policy.get('enabled',False):raise ValueError('policy_not_enabled')
        if 'release_id' in p:sha(p['release_id'])
        if 'expected_current_release' in p and p['expected_current_release'] is not None:sha(p['expected_current_release'])
        for key in ('backup_id','maintenance_grant','request_id'):
            if key in p:ident(p[key])
        if op=='operation_status':return self.journal.read(p['request_id'])
        if op=='registered_service_status':return self.status()
        if op=='registered_service_logs':
            # Raw journal may contain private business data. Return only safe systemd result fields.
            return {'logs':[],'reason_code':'raw_logs_disabled_by_policy','service_status':self.status()}
        return self.journal.run(p['request_id'],{'operation':op,**p},lambda:self.mutate(op,p))
    def systemctl(self,*args):
        p=subprocess.run(['/usr/bin/systemctl',*args],capture_output=True,text=True,timeout=60,env={'PATH':'/usr/bin:/bin','LANG':'C'})
        if p.returncode:raise ValueError('registered_systemd_failed')
        return p.stdout
    def installed(self):
        current=Path(self.policy['release_root'])/'current'
        if not current.exists():return None
        p=current.resolve();root=Path(self.policy['release_root']).resolve()
        if p.parent!=root:raise ValueError('invalid_current_release')
        return release_status(p)['sha']
    def status(self):
        data=self.systemctl('show','msp-data-sync.service','msp-data-sync.timer','-p','Id','-p','ActiveState','-p','UnitFileState','-p','ExecStart','-p','NextElapseUSecRealtime','-p','MainPID')
        return {'installed_release_sha':self.installed(),'systemd':data,'running_release_sha':self.installed() if 'ActiveState=active' in data.split('Id=msp-data-sync.timer')[0] and 'MainPID=0' not in data.split('Id=msp-data-sync.timer')[0] else None}
    def install_units(self,release):
        root=Path(self.policy['release_root'])/sha(release)
        protected_file(root/'apps/msp_data_sync/sync.py')
        service=f'''[Unit]\nDescription=Registered MSP data synchronization\nAfter=network-online.target\n[Service]\nType=oneshot\nUser=msp-sync\nGroup=msp-sync\nWorkingDirectory={root}\nExecStart=/usr/bin/python3 -B {root}/apps/msp_data_sync/sync.py --config {root}/config/msp-data/sync.json --source all\nNoNewPrivileges=true\nPrivateTmp=true\nProtectSystem=strict\nProtectHome=true\nReadWritePaths=/opt/mcp/data/msp\nRestrictSUIDSGID=true\nCapabilityBoundingSet=\n'''
        timer='[Unit]\nDescription=Registered daily MSP sync\n[Timer]\nOnCalendar=*-*-* 08:00:00 Europe/Moscow\nPersistent=true\nRandomizedDelaySec=0\nUnit=msp-data-sync.service\n[Install]\nWantedBy=timers.target\n'
        for unit,content in [('msp-data-sync.service',service),('msp-data-sync.timer',timer)]:
            target=Path('/etc/systemd/system')/unit
            if target.is_symlink():raise ValueError('unit_symlink_denied')
            tmp=target.with_suffix('.operator-new');tmp.write_text(content);tmp.chmod(0o644);os.replace(tmp,target)
        self.systemctl('daemon-reload')
    def mutate(self,op,p):
        with lock(Path(self.policy['state_dir'])/'component.lock'):
            if op=='deploy_component':
                if self.installed()!=p['expected_current_release']:raise ValueError('current_release_changed')
                provenance=self.verifier.verify(p['release_id'])
                backup=self.backups().backup()
                dest=Path(self.policy['release_root'])/p['release_id']
                if dest.exists():release_status(dest)
                else:extract_release(self.verifier.archive(p['release_id']),dest,p['release_id'])
                protected_file(dest/'apps/msp_data_sync/sync.py')
                # Freeze the old writer before switching configuration/release.
                self.systemctl('stop','msp-data-sync.timer');self.systemctl('stop','msp-data-sync.service')
                self.install_units(p['release_id'])
                current=dest.parent/'current';tmp=dest.parent/'current.new'
                if tmp.exists() or tmp.is_symlink():raise ValueError('activation_pending')
                tmp.symlink_to(dest.name);os.replace(tmp,current)
                self.systemctl('enable','--now','msp-data-sync.timer')
                return {'provenance':provenance,'backup':backup,'acceptance_required':True,**self.status()}
            if op=='install_registered_service':
                if p['release_id']!=self.installed():raise ValueError('release_not_installed')
                self.install_units(p['release_id']);return self.status()
            if op=='enable_registered_timer':
                if not self.installed():raise ValueError('release_not_installed')
                self.systemctl('enable','--now','msp-data-sync.timer');return self.status()
            if op=='restart_registered_service':
                if not self.installed():raise ValueError('release_not_installed')
                self.systemctl('restart','msp-data-sync.service');return self.status()
            if op=='backup_registered_database':return self.backups().backup()
            if op=='restore_registered_database':
                grants=self.policy.get('maintenance_grants',{});grant=grants.get(p['maintenance_grant'])
                if not grant or grant.get('backup_id')!=p['backup_id'] or grant.get('request_id')!=p['request_id'] or grant.get('expires_at',0)<time.time():raise ValueError('maintenance_grant_required')
                self.systemctl('stop','msp-data-sync.timer');self.systemctl('stop','msp-data-sync.service')
                # Protected fence must be granted only after non-systemd writers have been excluded by ACL migration.
                if not self.policy.get('exclusive_service_writer',False):raise ValueError('writer_fence_not_ready')
                r=self.backups().restore(p['backup_id'],maintenance=True)
                self.systemctl('start','msp-data-sync.service');self.systemctl('start','msp-data-sync.timer');return {**r,**self.status()}
        raise ValueError('operation_not_allowed')
    def backups(self):
        from .backup import BackupStore
        return BackupStore(self.policy['database'],self.policy['backup_root'],self.policy.get('retention',7),owner_uid=self.policy['service_uid'],owner_gid=self.policy['service_gid'])
