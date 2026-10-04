#!/usr/bin/env python3
"""Whitelisted read-only QRsite client for the MSP REMOTE bridge.

Request JSON example:
{"operation":"api_stocks_1c","params":{"page_size":5}}

Secrets are supplied only through GitHub Actions environment variables.
Token values are never printed.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

BASE = "https://qrbott.ru"

API_OPERATIONS = {
    "api_stocks_1c": ("/api/v1/stocks/1c/", {"date","blockid","offer_id","aggregate","page","page_size"}),
    "api_marketplaces_blocks": ("/api/v1/marketplaces/blocks/", {"q","page","page_size"}),
    "api_wb_orders": ("/api/v1/wb/orders/", {
        "blockid","nmId","chrtId","orderId","orderStatus","rejectType","warehouseType",
        "orderType","currency","arrivalRegion","arrivalCity","date_from","date_to",
        "changed_from","changed_to","ordering","page","page_size"
    }),
    "api_plansite_orders": ("/api/v1/plansite/orders/", {
        "q","order_id","type_order","as_of","ordering","page","page_size"
    }),
}

MCP_TOOLS = {"marketplaces_blocks","stock_1c_history","stocks_1c","wb_orders"}


def normalize(value: str) -> str:
    value = (value or "").strip().strip('"').strip("'")
    low = value.lower()
    if low.startswith("token "):
        value = value[6:].strip()
    elif low.startswith("bearer "):
        value = value[7:].strip()
    return value


_values = [
    normalize(os.environ.get("ANDREY_API_TOKEN","")),
    normalize(os.environ.get("ANDREY_MCP_TOKEN","")),
]
API_TOKEN = next((v for v in _values if v.startswith("qra_")), "")
MCP_TOKEN = next((v for v in _values if v.startswith("qr_")), "")


def http(url: str, *, method="GET", headers=None, payload=None):
    h = dict(headers or {})
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, dict(r.headers), r.read(2_000_000).decode("utf-8","replace"), r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read(500_000).decode("utf-8","replace"), e.geturl()


def parse_mcp(body: str):
    body = body.strip()
    if not body:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        out=[]
        for line in body.splitlines():
            if line.startswith("data:"):
                try:
                    out.append(json.loads(line[5:].strip()))
                except Exception:
                    pass
        return out[0] if len(out)==1 else out


def header_ci(headers, key):
    for k,v in headers.items():
        if k.lower()==key.lower():
            return v
    return None


def sanitize_params(params: dict[str, Any], allowed: set[str]):
    unknown=set(params)-allowed
    if unknown:
        raise SystemExit("Unknown parameters: "+",".join(sorted(unknown)))
    out=dict(params)
    if "page_size" in out:
        out["page_size"]=max(1,min(int(out["page_size"]),50))
    return out


def api_call(operation: str, params: dict[str, Any]):
    if not API_TOKEN:
        raise SystemExit("API token not available")
    path, allowed = API_OPERATIONS[operation]
    params=sanitize_params(params,allowed)
    query=urllib.parse.urlencode(params, doseq=False)
    url=BASE+path+("?" + query if query else "")
    s,_,body,final=http(url,headers={
        "Authorization":"Token "+API_TOKEN,
        "Accept":"application/json",
        "User-Agent":"msp-remote-andrey-readonly/1.0",
    })
    try:
        data=json.loads(body)
    except Exception:
        data={"raw":body[:10000]}
    print(json.dumps({"operation":operation,"status":s,"url":final,"data":data},ensure_ascii=False))


def mcp_session():
    if not MCP_TOKEN:
        raise SystemExit("MCP token not available")
    headers={
        "Authorization":"Bearer "+MCP_TOKEN,
        "Accept":"application/json, text/event-stream",
        "User-Agent":"msp-remote-andrey-readonly/1.0",
    }
    init={"jsonrpc":"2.0","id":1,"method":"initialize","params":{
        "protocolVersion":"2025-06-18","capabilities":{},
        "clientInfo":{"name":"msp-remote","version":"1.0"}}}
    s,rh,body,_=http(BASE+"/mcp",method="POST",headers=headers,payload=init)
    if s!=200:
        raise SystemExit("MCP initialize failed HTTP "+str(s)+": "+body[:1000])
    sid=header_ci(rh,"mcp-session-id")
    if sid:
        headers["Mcp-Session-Id"]=sid
    headers["MCP-Protocol-Version"]="2025-06-18"
    http(BASE+"/mcp",method="POST",headers=headers,payload={
        "jsonrpc":"2.0","method":"notifications/initialized","params":{}})
    return headers


def mcp_tools_list():
    headers=mcp_session()
    s,_,body,_=http(BASE+"/mcp",method="POST",headers=headers,payload={
        "jsonrpc":"2.0","id":2,"method":"tools/list","params":{}})
    print(json.dumps({"operation":"mcp_tools_list","status":s,"data":parse_mcp(body)},ensure_ascii=False))


def mcp_tool_call(params: dict[str, Any]):
    name=params.get("name")
    args=params.get("arguments") or {}
    if name not in MCP_TOOLS:
        raise SystemExit("MCP tool not in read-only allowlist")
    if not isinstance(args,dict):
        raise SystemExit("arguments must be an object")
    if "page_size" in args:
        args["page_size"]=max(1,min(int(args["page_size"]),50))
    headers=mcp_session()
    s,_,body,_=http(BASE+"/mcp",method="POST",headers=headers,payload={
        "jsonrpc":"2.0","id":3,"method":"tools/call",
        "params":{"name":name,"arguments":args}})
    print(json.dumps({"operation":"mcp_tool_call","tool":name,"status":s,"data":parse_mcp(body)},ensure_ascii=False))


def main():
    request_path=sys.argv[1] if len(sys.argv)>1 else "requests/andrey-readonly.json"
    with open(request_path,"r",encoding="utf-8") as f:
        req=json.load(f)
    op=req.get("operation")
    params=req.get("params") or {}
    if op in API_OPERATIONS:
        api_call(op,params)
    elif op=="mcp_tools_list":
        mcp_tools_list()
    elif op=="mcp_tool_call":
        mcp_tool_call(params)
    else:
        raise SystemExit("Unsupported read-only operation")


if __name__=="__main__":
    main()
