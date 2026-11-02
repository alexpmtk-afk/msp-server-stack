"""PREPARED READ_ONLY probe. Not run against any real Redis during preparation.

Only PING/TIME/INFO server and optional EXISTS/PTTL of <=3 explicitly supplied
private keys. No provider imports, EVAL, key scan, SET or job scheduling.
"""
import argparse
import json
import sys
from pathlib import Path


def one(client, keys):
    if len(keys) > 3 or any(type(k) is not str or not k.startswith('marketplace-rate:v1:') for k in keys):
        raise ValueError('explicit canonical bucket inventory required')
    if client.ping() is not True:
        raise ValueError('PING failed')
    stamp = client.time()
    if not isinstance(stamp, (list,tuple)) or len(stamp) != 2 or any(type(n) is not int for n in stamp):
        raise ValueError('TIME response mismatch')
    info = client.info('server')
    if type(info) is not dict or type(info.get('redis_version')) is not str:
        raise ValueError('INFO response mismatch')
    observations = []
    for index,key in enumerate(keys):
        exists = client.exists(key)
        ttl = client.pttl(key)
        if type(exists) is not int or exists not in (0,1) or type(ttl) is not int:
            raise ValueError('EXISTS/PTTL response mismatch')
        observations.append({'index':index,'exists':bool(exists),
             'ttl_state':'ABSENT' if ttl == -2 else 'NO_EXPIRY' if ttl == -1 else 'EXPIRING'})
    # Identity is private, used ONLY for comparing two protocols to this endpoint.
    identity = info.get('run_id')
    return {'read_commands':'PASS','server_version':info['redis_version'],
            'standalone_mode':'PASS' if info.get('redis_mode')=='standalone' else 'NOT_VERIFIED',
            'buckets':observations}, identity


def probe(factory, keys=()):
    results=[]
    identities=[]
    for protocol in (None,2):
        client=factory(protocol)
        try:
            result,identity=one(client,keys)
            actual=getattr(getattr(client,'connection_pool',None),'connection_kwargs',{}).get('protocol')
            result['protocol_request']='PASS' if protocol is None or actual==protocol else 'NOT_VERIFIED'
            results.append({'protocol_case':'DEFAULT' if protocol is None else 'RESP2',**result})
            identities.append(identity)
        finally:
            client.close()
    same = bool(identities[0]) and identities[0] == identities[1]
    status='PASS' if same and all(r['standalone_mode']=='PASS' and r['protocol_request']=='PASS' for r in results) else 'NOT_VERIFIED'
    return {'read_only_protocol_check':status,'cases':results,'same_backend_across_protocol_cases':'MATCH' if same else 'NOT_VERIFIED',
            'shared_across_other_integrations':'NOT_VERIFIED','atomic_lua_admission':'NOT_TESTED_READ_ONLY',
            'provider_calls':0}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--release',type=Path,required=True)
    p.add_argument('--explicit-keys-json',type=Path)
    args=p.parse_args(argv)
    try:
        # Operator must first verify the root-owned approved release manifest.
        sys.path.insert(0,str(args.release))
        from apps.msp_marketplace_reports.shared_rate_limit import redis_url_from_env, redis_connection_kwargs
        from apps.msp_marketplace_reports.standalone_wb import read_control
        import redis
        url=redis_url_from_env()
        if not url.startswith(('redis://','rediss://')):
            raise ValueError('approved backend not configured')
        keys=[]
        if args.explicit_keys_json:
            obj=read_control(args.explicit_keys_json)
            if type(obj) is not dict or set(obj)!={'keys'} or type(obj['keys']) is not list:
                raise ValueError('invalid private key inventory')
            keys=obj['keys']
        def factory(protocol):
            options=dict(decode_responses=True,socket_connect_timeout=3,socket_timeout=3,
                         **redis_connection_kwargs(url))
            if protocol is not None:
                options['protocol']=protocol
            return redis.Redis.from_url(url,**options)
        result=probe(factory,keys)
        result['client_version']=redis.__version__
    except Exception as exc:
        print(json.dumps({'status':'FAIL_OR_UNAVAILABLE','error_type':type(exc).__name__,
                          'provider_calls':0}))
        return 1
    print(json.dumps(result,sort_keys=True))
    return 0 if result['read_only_protocol_check']=='PASS' else 2


if __name__=='__main__':
    raise SystemExit(main())
