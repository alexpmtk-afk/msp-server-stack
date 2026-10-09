"""Scoped GitHub App broker; installation credentials never cross RPC."""
import base64,contextlib,fnmatch,json,re,subprocess,time,urllib.request
from .security import fields,sha,protected_file
REPO='alexpmtk-afk/msp-server-stack'
PROTECTED=['.github/**','apps/operator_layer/**','config/agent/**','scripts/agent/**','scripts/deploy/**','scripts/operator/**','systemd/**','AGENTS.md','**/AGENTS.md','**/SKILL.md','.hermes*','**/.hermes*','CLAUDE.md','**/CLAUDE.md','SOUL.md','**/SOUL.md']

def validate_branch(b):
    if not isinstance(b,str) or not re.fullmatch(r'hermes/[A-Za-z0-9_-]+/[A-Za-z0-9_/-]+',b) or '..' in b or '//' in b or b.endswith('/') or any(x.endswith('.lock') for x in b.split('/')):raise ValueError('invalid_branch')
    return b

def validate_files(files):
    if not isinstance(files,dict) or not 1<=len(files)<=100:raise ValueError('invalid_files')
    for p,v in files.items():
        if not isinstance(p,str) or not p or p.startswith('/') or '\\' in p or any(x in ('','..','.git','.') for x in p.split('/')) or len(p)>400:raise ValueError('invalid_path')
        if p.startswith('.github/workflows/'):raise ValueError('workflow_write_disabled')
        if v is not None and (not isinstance(v,str) or len(v.encode())>500000):raise ValueError('invalid_content')
    return files

def is_protected(paths):return any(fnmatch.fnmatch(p,g) for p in paths for g in PROTECTED)

def merge_gate(policy,pr,head,paths,checks,reviews):
    sha(head)
    if pr.get('state')!='open' or pr.get('draft') or pr['head']['sha']!=head or pr['base']['ref']!='main':raise ValueError('pr_not_ready')
    for name,app_id in policy['required_checks'].items():
        matches=[c for c in checks if c['name']==name and c.get('app',{}).get('id')==app_id]
        if not matches or any(c.get('head_sha')!=head or c.get('status')!='completed' or c.get('conclusion')!='success' for c in matches):raise ValueError('ci_not_pass')
    if is_protected(paths):
        owner=[r for r in reviews if r.get('user',{}).get('login')==policy['owner_login']]
        if not owner or owner[-1].get('state')!='APPROVED' or owner[-1].get('commit_id')!=head:raise ValueError('owner_approval_required')

class AppAPI:
    def __init__(self,app_id,installation_id,key_path):self.app_id=app_id;self.installation_id=installation_id;self.key=protected_file(key_path,owner=__import__('os').getuid(),secret=True);self.token=None
    def request(self,method,path,payload=None,jwt=None):
        if not path.startswith('/') or '..' in path or '\n' in path:raise ValueError('invalid_api_path')
        req=urllib.request.Request('https://api.github.com'+path,data=None if payload is None else json.dumps(payload).encode(),method=method,headers={'Authorization':'Bearer '+(jwt or self.token),'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'MSP-Operator-Broker'})
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args):raise ValueError('redirect_denied')
        with urllib.request.build_opener(NoRedirect).open(req,timeout=30) as r:
            b=r.read(4_000_001)
            if len(b)>4_000_000:raise ValueError('response_too_large')
            return json.loads(b) if b else {}
    @contextlib.contextmanager
    def session(self):
        enc=lambda j:base64.urlsafe_b64encode(json.dumps(j,separators=(',',':')).encode()).rstrip(b'=')
        t=int(time.time());message=enc({'alg':'RS256','typ':'JWT'})+b'.'+enc({'iat':t-30,'exp':t+540,'iss':str(self.app_id)})
        signature=subprocess.run(['/usr/bin/openssl','dgst','-sha256','-sign',str(self.key)],input=message,capture_output=True,check=True).stdout
        jwt=(message+b'.'+base64.urlsafe_b64encode(signature).rstrip(b'=')).decode()
        j=self.request('POST',f'/app/installations/{int(self.installation_id)}/access_tokens',{'repositories':['msp-server-stack'],'permissions':{'contents':'write','pull_requests':'write','checks':'read','statuses':'read','actions':'read'}},jwt=jwt)
        if set(j.get('permissions',{}))-{'contents','pull_requests','checks','statuses','actions','metadata'}:raise ValueError('unexpected_app_permissions')
        self.token=j['token']
        try:yield self
        finally:
            try:self.request('DELETE','/installation/token')
            finally:self.token=None

class GitHubBroker:
    REQUIRED={'create_branch':('branch','base_sha','request_id'),'commit_files':('branch','expected_head','files','message','request_id'),'push':('branch','expected_head','commit_sha','request_id'),'create_pr':('branch','expected_head','title','body','request_id'),'read_pr':('pr',),'read_checks':('sha',),'read_ci':('sha',),'merge_approved_pr':('pr','expected_head','request_id')}
    def __init__(self,policy,api,journal=None):
        if policy['repository']!=REPO:raise ValueError('repository_not_allowed')
        self.policy=policy;self.api=api;self.journal=journal
    def get(self,path):return self.api.request('GET','/repos/'+REPO+path)
    def pages(self,path,key=None):
        out=[]
        for page in range(1,101):
            j=self.get(path+(' & ' if False else ('&' if '?' in path else '?'))+f'per_page=100&page={page}');rows=j[key] if key else j;out+=rows
            if len(rows)<100:return out
        raise ValueError('pagination_limit')
    def execute(self,operation,p):
        if operation=='capability_status':
            fields(p,('capability',));allowed=p['capability'] in ('github.authenticated_read','github.write','github.pr','github.ci_read','github.merge')
            if self.api is None:return {'tool_visible':True,'authenticated':False,'authorized':False,'acceptance_verified':False,'reason_code':'app_not_provisioned'}
            with self.api.session():self.api.request('GET','/installation/repositories')
            return {'tool_visible':True,'authenticated':True,'authorized':allowed,'acceptance_verified':False,'reason_code':'installation_verified_readiness_only'}
        if operation not in self.REQUIRED:raise ValueError('operation_not_allowed')
        fields(p,self.REQUIRED[operation])
        if 'branch' in p:validate_branch(p['branch'])
        for key in ('base_sha','expected_head','commit_sha','sha'):
            if key in p:sha(p[key])
        if 'files' in p:validate_files(p['files'])
        if 'pr' in p and (type(p['pr']) is not int or p['pr']<1):raise ValueError('invalid_pr')
        for key in ('message','title','body'):
            if key in p and (not isinstance(p[key],str) or len(p[key])>20000):raise ValueError('invalid_text')
        if self.api is None:raise ValueError('app_not_provisioned')
        def run():
            with self.api.session():return self._run(operation,p)
        if 'request_id' in p:
            if self.journal is None:raise ValueError('journal_required')
            return self.journal.run(p['request_id'],{'operation':operation,**p},run)
        return run()
    def _run(self,op,p):
        base='/repos/'+REPO
        if op=='create_branch':
            if self.get('/git/ref/heads/main')['object']['sha']!=p['base_sha']:raise ValueError('canonical_sha_changed')
            self.api.request('POST',base+'/git/refs',{'ref':'refs/heads/'+p['branch'],'sha':p['base_sha']})
            return {'sha':self.get('/git/ref/heads/'+p['branch'])['object']['sha'],'branch':p['branch']}
        if op in ('commit_files','push'):
            current=self.get('/git/ref/heads/'+p['branch'])['object']['sha']
            if current!=p['expected_head']:raise ValueError('head_changed')
            parent=self.get('/git/commits/'+current)
            if op=='commit_files':
                tree=[]
                for path,content in p['files'].items():
                    node={'path':path,'mode':'100644','type':'blob'}
                    if content is None:node['sha']=None
                    else:node['sha']=self.api.request('POST',base+'/git/blobs',{'content':content,'encoding':'utf-8'})['sha']
                    tree.append(node)
                tr=self.api.request('POST',base+'/git/trees',{'base_tree':parent['tree']['sha'],'tree':tree})
                commit=self.api.request('POST',base+'/git/commits',{'message':p['message'],'tree':tr['sha'],'parents':[current]})['sha']
                return {'commit_sha':commit,'expected_head':current,'branch':p['branch']}
            commit=p['commit_sha'];obj=self.get('/git/commits/'+commit)
            if [x['sha'] for x in obj['parents']]!=[current]:raise ValueError('non_linear_push')
            diff=self.get('/compare/'+current+'...'+commit)
            if len(diff.get('files',[]))>=300 or diff.get('total_commits')!=1:raise ValueError('unbounded_diff')
            validate_files({x['filename']:'' for x in diff['files']})
            # GitHub non-force update enforces fast-forward; verify CAS again immediately.
            if self.get('/git/ref/heads/'+p['branch'])['object']['sha']!=current:raise ValueError('head_changed')
            self.api.request('PATCH',base+'/git/refs/heads/'+p['branch'],{'sha':commit,'force':False})
            actual=self.get('/git/ref/heads/'+p['branch'])['object']['sha']
            if actual!=commit:raise ValueError('push_readback_failed')
            return {'sha':actual,'branch':p['branch']}
        if op=='create_pr':
            if self.get('/git/ref/heads/'+p['branch'])['object']['sha']!=p['expected_head']:raise ValueError('head_changed')
            pr=self.api.request('POST',base+'/pulls',{'head':p['branch'],'base':'main','title':p['title'],'body':p['body'],'draft':False})
            return self.get('/pulls/'+str(pr['number']))
        if op=='read_pr':return self.get('/pulls/'+str(p['pr']))
        if op=='read_checks':return {'checks':self.pages('/commits/'+p['sha']+'/check-runs',key='check_runs')}
        if op=='read_ci':return {'runs':self.pages('/actions/runs?head_sha='+p['sha'],key='workflow_runs')}
        if op=='merge_approved_pr':
            number=str(p['pr']);pr=self.get('/pulls/'+number)
            if pr['base']['repo']['full_name']!=REPO or pr['head']['repo']['full_name']!=REPO:raise ValueError('repository_not_allowed')
            validate_branch(pr['head']['ref'])
            paths=[x['filename'] for x in self.pages('/pulls/'+number+'/files')]
            checks=self.pages('/commits/'+p['expected_head']+'/check-runs',key='check_runs');reviews=self.pages('/pulls/'+number+'/reviews')
            merge_gate(self.policy,pr,p['expected_head'],paths,checks,reviews)
            self.api.request('PUT',base+'/pulls/'+number+'/merge',{'sha':p['expected_head'],'merge_method':'merge'})
            pr=self.get('/pulls/'+number)
            if not pr['merged']:raise ValueError('merge_not_verified')
            return {'merged':True,'sha':pr['merge_commit_sha'],'pr':p['pr']}
        raise ValueError('operation_not_allowed')
