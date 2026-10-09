"""Bounded Unix RPC with kernel caller identity; no shell command transport."""
import json,os,socket,stat,struct
from pathlib import Path
LIMIT=2_000_000

def receive(s):
    b=bytearray()
    while len(b)<=LIMIT:
        p=s.recv(min(65536,LIMIT+1-len(b)))
        if not p:break
        b.extend(p)
        if b.endswith(b'\n'):break
    if len(b)>LIMIT or not b.endswith(b'\n'):raise ValueError('invalid_rpc_frame')
    return json.loads(b)

def call(path,operation,params):
    p=Path(path);a=p.lstat()
    if not stat.S_ISSOCK(a.st_mode) or a.st_uid!=0 or a.st_mode & 0o002:raise ValueError('untrusted_broker_socket')
    for ancestor in p.parents:
        a=ancestor.lstat()
        if stat.S_ISLNK(a.st_mode) or a.st_uid!=0 or a.st_mode & 0o022:raise ValueError('untrusted_socket_directory')
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(60);s.connect(str(p));s.sendall(json.dumps({'operation':operation,'params':params}).encode()+b'\n');r=receive(s)
    if not r.get('ok'):raise ValueError(r.get('error','broker_failed'))
    return r['result']

def serve(path,broker,allowed_uids):
    p=Path(path)
    if p.exists():raise ValueError('socket_already_exists')
    with socket.socket(socket.AF_UNIX) as listener:
        listener.bind(str(p));os.chmod(p,0o660);listener.listen(8)
        while True:
            conn,_=listener.accept()
            with conn:
                conn.settimeout(60)
                try:
                    _,uid,_=struct.unpack('3i',conn.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
                    if uid not in allowed_uids:raise ValueError('caller_not_authorized')
                    q=receive(conn)
                    if set(q)!={'operation','params'}:raise ValueError('invalid_fields')
                    r={'ok':True,'result':broker.execute(q['operation'],q['params'])}
                except Exception as e:
                    # Neither exception text from providers nor traceback/HTTP body crosses the tool boundary.
                    safe=str(e) if isinstance(e,ValueError) and str(e).replace('_','').isalnum() else type(e).__name__
                    r={'ok':False,'error':safe}
                conn.sendall(json.dumps(r).encode()+b'\n')
