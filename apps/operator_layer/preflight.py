"""Read-only, fixed probes; registry data never becomes an executable command."""
import hashlib,json,os,socket,stat,urllib.request,urllib.error
from datetime import datetime,timedelta,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
FACETS=('tool_visible','authenticated','authorized','acceptance_verified')

def load_registry():
    r=json.loads((ROOT/'config/agent/capabilities.yaml').read_text())
    if r.get('schema_version')!=1 or not isinstance(r.get('capabilities'),dict):raise ValueError('invalid_registry')
    for c in r['capabilities'].values():
        if set(c)-{'provider','target','probe','ttl','enabled'} or c['probe'] not in {'github_public','github_ci','google_public','filesystem','broker','disabled'}:raise ValueError('unknown_probe')
        if not 1<=c['ttl']<=3600:raise ValueError('invalid_ttl')
    return r

def result(capability,spec,facets,reason,revision):
    t=datetime.now(timezone.utc);f={k:facets.get(k) for k in FACETS}
    if not spec.get('enabled',True):state='DISABLED'
    elif all(f[k] is True for k in ('tool_visible','authenticated','authorized')):state='PASS'
    elif any(v is False for v in f.values()):state='FAIL'
    else:state='UNKNOWN'
    e=hashlib.sha256(json.dumps([capability,spec,f,reason,revision,t.isoformat()],sort_keys=True).encode()).hexdigest()
    return {'capability':capability,'state':state,'provider':spec['provider'],'target':spec['target'],'reason_code':reason,'checked_at':t.isoformat(),'expires_at':(t+timedelta(seconds=spec['ttl'])).isoformat(),'ttl':spec['ttl'],'evidence_id':e,'policy_revision':revision,**f,'gap':f'CAPABILITY GAP: {capability} ({reason})' if state in ('FAIL','UNKNOWN') else None}

def _get(url):
    req=urllib.request.Request(url,headers={'User-Agent':'MSP-Operator-Preflight'})
    with urllib.request.urlopen(req,timeout=15) as r:
        if r.status!=200:raise ValueError('http_failure')
        return json.loads(r.read(2_000_000))

def probe(cap,spec,live):
    f=dict.fromkeys(FACETS,False)
    if spec['probe']=='disabled':return f,'disabled_by_policy'
    if not live:return dict.fromkeys(FACETS,None),'offline_not_probed'
    if spec['probe']=='filesystem':
        ok=all(os.access(p,os.W_OK) for p in spec['target']);return dict.fromkeys(FACETS,ok),'unix_access_checked'
    if spec['probe']=='github_public':
        _get('https://api.github.com/repos/alexpmtk-afk/msp-server-stack');return dict.fromkeys(FACETS,True),'anonymous_public_read_verified'
    if spec['probe']=='github_ci':
        _get('https://api.github.com/repos/alexpmtk-afk/msp-server-stack/actions/runs?per_page=1');return dict.fromkeys(FACETS,True),'public_ci_read_verified'
    if spec['probe']=='google_public':
        from .google_ro import PublicSheets
        cfg=json.loads((ROOT/'config/msp-data/sync.json').read_text());p=PublicSheets(cfg)
        for source in cfg['sources']:p.read_source(source)
        return dict.fromkeys(FACETS,True),'four_registered_csv_verified'
    if spec['probe']=='broker':
        sock={'github':'github','remote':'remote','google':'google','tasks':'tasks'}[spec['provider']]
        path=Path('/run/msp-operator')/(sock+'.sock')
        if not path.exists():return f,'broker_not_installed'
        from .rpc import call
        j=call(path,'capability_status',{'capability':cap})
        return {k:j.get(k) for k in FACETS},j.get('reason_code','broker_status')
    raise ValueError('unknown_probe')

def evaluate(required=None,live=True):
    r=load_registry();selected=list(r['capabilities']) if required is None else required
    if any(k not in r['capabilities'] for k in selected):raise ValueError('unknown_required_capability')
    rows=[]
    for k in selected:
        try:f,reason=probe(k,r['capabilities'][k],live)
        except Exception as e:f=dict.fromkeys(FACETS,None);reason='probe_failed_'+type(e).__name__
        rows.append(result(k,r['capabilities'][k],f,reason,r['policy_revision']))
    return {'schema_version':1,'results':rows,'ready':all(x['state']=='PASS' for x in rows)}
