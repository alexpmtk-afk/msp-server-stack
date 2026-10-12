"""Fail-closed policy loading, request validation and durable operation journal."""
import contextlib,fcntl,hashlib,json,os,re,sqlite3,stat,time
from pathlib import Path

def fields(params,required,optional=()):
    if not isinstance(params,dict) or set(params)-set(required)-set(optional) or set(required)-set(params):raise ValueError('invalid_fields')

def ident(value):
    if not isinstance(value,str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,100}',value):raise ValueError('invalid_identifier')
    return value

def sha(value):
    if not isinstance(value,str) or not re.fullmatch('[0-9a-f]{40}',value):raise ValueError('invalid_sha')
    return value

def protected_file(path,owner=0,secret=False):
    p=Path(path)
    for x in [p,*p.parents]:
        s=x.lstat()
        if stat.S_ISLNK(s.st_mode) or s.st_uid not in {0,owner} or s.st_mode & 0o022:raise ValueError('untrusted_file_ownership')
    s=p.lstat()
    if not stat.S_ISREG(s.st_mode) or (secret and s.st_mode & 0o077):raise ValueError('untrusted_secret_permissions')
    return p

def load_policy(path):return json.loads(protected_file(path).read_text())

def digest_file(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

@contextlib.contextmanager
def lock(path):
    fd=os.open(path,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:fcntl.flock(fd,fcntl.LOCK_EX);yield
    finally:os.close(fd)

class Journal:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as c:c.execute('CREATE TABLE IF NOT EXISTS operation(id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,status TEXT NOT NULL,result TEXT,updated REAL NOT NULL)')
        os.chmod(self.path,0o600)
    def connect(self):return sqlite3.connect(self.path,timeout=30)
    def read(self,key):
        ident(key)
        with self.connect() as c:r=c.execute('select status,result from operation where id=?',(key,)).fetchone()
        return None if r is None else {'status':r[0],'result':json.loads(r[1]) if r[1] else None}
    def run(self,key,payload,fn):
        ident(key);h=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
        with lock(self.path.with_suffix('.lock')):
            with self.connect() as c:
                r=c.execute('select fingerprint,status,result from operation where id=?',(key,)).fetchone()
                if r:
                    if r[0]!=h:raise ValueError('idempotency_conflict')
                    if r[1]!='complete':raise ValueError('uncertain_operation_readback_required')
                    return json.loads(r[2])
                c.execute('insert into operation values(?,?,?,NULL,?)',(key,h,'pending',time.time()))
            # A crash leaves pending; never automatically execute the uncertain mutation again.
            value=fn()
            with self.connect() as c:c.execute('update operation set status=?,result=?,updated=? where id=?',('complete',json.dumps(value),time.time(),key))
            return value
