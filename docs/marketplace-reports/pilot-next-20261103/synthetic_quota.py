"""Bounded synthetic-only quota exercise; never imports/constructs HTTP transport.
Prepared, NOT executed on installed Redis. Main runs only as msp-reports UID995.
"""
import asyncio
import base64
import json
import os
import secrets
import sys
from urllib.parse import urlsplit

RELEASE='/opt/mcp/projects/msp-marketplace-reports-releases/c1fee070e9efa0c925a78f266fdf03cb12a173cf'


def loopback_url(url):
    p=urlsplit(url)
    if (p.scheme!='redis' or p.hostname!='127.0.0.1' or p.port!=16379
            or p.path!='/0' or p.username!='quota_runtime' or not p.password
            or p.query or p.fragment):
        raise ValueError('approved local runtime endpoint required')
    return url


def fake_credentials(suffix):
    payload=base64.urlsafe_b64encode(json.dumps({'sid':'synthetic-only-no-seller'}).encode()).decode().rstrip('=')
    return {'token':'synthetic.'+payload+'.'+suffix}


async def exercise(url):
    from apps.msp_marketplace_reports.shared_rate_limit import GlobalRateController,RateRule
    from apps.msp_marketplace_reports.quota import request_rules
    from apps.msp_marketplace_reports.providers import Request,WB_DETAIL,WB_LIST
    # Check accepted account identity/finance group without loading any credential.
    detail=request_rules('wb',fake_credentials('first'),Request('wb',WB_DETAIL+'883801632',{}))
    aliases=request_rules('wb',fake_credentials('second'),Request('wb',WB_LIST,{}))
    if detail!=aliases or sorted(r.interval_seconds for r in detail)!=[60.0,65.0]:
        raise ValueError('accepted seller finance rules drift')
    # Replace the entire seller component: no actual or hashed seller key is used.
    prefix='marketplace-rate:v1:wb:synthetic-pilot-'+secrets.token_hex(16)
    rules=[RateRule(prefix+':'+r.key.split(':',4)[4],r.interval_seconds) for r in detail]
    other=[RateRule(prefix+'-other:'+r.key.split(':',4)[4],r.interval_seconds) for r in detail]
    one=GlobalRateController(redis_url=url);two=GlobalRateController(redis_url=url)
    try:
        if one.backend!='redis' or two.backend!='redis':raise ValueError('Redis required')
        # Two simultaneous clients for one synthetic owner: exactly one admission.
        admissions=await asyncio.gather(one.try_acquire(rules),two.try_acquire(rules))
        if sorted(x[0] for x in admissions)!=[False,True]:raise ValueError('atomic admission failed')
        if not 0<next(wait for ok,wait in admissions if not ok)<=66:raise ValueError('safety wait failed')
        if not (await one.try_acquire(other))[0]:raise ValueError('owner isolation failed')
        await one.defer(rules,90)
        admitted,wait=await two.try_acquire(rules)
        if admitted or not 85<wait<=91:raise ValueError('cooldown failed')
        # No SCAN, DEL, FLUSH, CONFIG or real keys; four synthetic keys, TTL<=715s.
        return {'synthetic_quota':'PASS','clients':2,'keys':4,'ttl_ceiling_seconds':715,
                'provider_calls':0,'live_seller_keys_touched':0,'api_enabled':False,
                'cross_host_exclusion_proven':False}
    finally:
        for ctl in (one,two):
            if ctl._redis is not None:await ctl._redis.aclose()


def main():
    if os.geteuid()!=995 or sys.argv[1:]!=['--synthetic-write-approved']:
        print(json.dumps({'synthetic_quota':'BLOCKED','reason':'approved isolated write scope and msp-reports required'}));return 2
    try:
        if os.environ.get('MARKETPLACE_REQUIRE_REDIS')!='1':raise ValueError('Redis required')
        url=loopback_url(os.environ.get('MARKETPLACE_MCP_REDIS_URL',''))
        sys.path.insert(0,RELEASE)
        result=asyncio.run(asyncio.wait_for(exercise(url),timeout=20))
        print(json.dumps(result,sort_keys=True));return 0
    except Exception as exc:
        # No URL, credential, exception text or traceback in output.
        print(json.dumps({'synthetic_quota':'FAIL','error_type':type(exc).__name__,'provider_calls':0}));return 1

if __name__=='__main__':raise SystemExit(main())
