"""Configuration/rendering and guard shared by installer and offline tests."""
import hashlib
import os
from pathlib import Path
import stat

PREFIX=Path('/opt/mcp/quota-redis')
CONFIG=Path('/etc/msp-quota-redis')
DATA=Path('/var/lib/msp-quota-redis')
STATE=Path('/var/lib/msp-quota-redis-install')
BACKUP=Path('/opt/mcp/backups/msp-quota-redis')
READONLY=Path('/etc/msp-marketplace-reports/redis-readonly.env')
RUNTIME=Path('/etc/msp-marketplace-reports-executor/redis-runtime.env')
SERVICE='msp-quota-redis.service'
PORT=16379
USER='msp-quota-redis'
RELEASE=Path('/opt/mcp/projects/msp-marketplace-reports-releases/c1fee070e9efa0c925a78f266fdf03cb12a173cf')


def sha(data):return hashlib.sha256(data).hexdigest()


def trusted(p,uid=0,mode=None):
    st=p.lstat()
    if st.st_uid!=uid or st.st_mode&0o022 or stat.S_ISLNK(st.st_mode):raise ValueError('untrusted path')
    if mode is not None and stat.S_IMODE(st.st_mode)!=mode:raise ValueError('mode mismatch')
    if stat.S_ISREG(st.st_mode) and st.st_nlink!=1:raise ValueError('hardlink')
    if not stat.S_ISDIR(st.st_mode) and not stat.S_ISREG(st.st_mode):raise ValueError('inode type')
    return st


def syncdir(p):
    fd=os.open(p,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)


def write_new(p,data,mode=0o600,uid=0,gid=0):
    fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
    try:
        with os.fdopen(fd,'wb',closefd=False) as f:
            f.write(data);f.flush();os.fchown(fd,uid,gid);os.fchmod(fd,mode);os.fsync(fd)
    finally:os.close(fd)
    syncdir(p.parent)


def config_text(data,acl,*,port=PORT,socket_path=None):
    for p in [str(data),str(acl),str(socket_path or '')]:
        if any(c in p for c in ['\n','\r','"','\\']):raise ValueError('config path encoding')
    return f'''bind 127.0.0.1
protected-mode yes
port {port}
daemonize no
supervised no
logfile ""
save ""
appendonly yes
appendfilename "appendonly.aof"
appenddirname "appendonlydir"
appendfsync always
no-appendfsync-on-rewrite no
aof-load-truncated no
aof-use-rdb-preamble yes
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 16mb
stop-writes-on-bgsave-error yes
maxmemory 64mb
maxmemory-policy noeviction
databases 1
aclfile "{acl}"
dir "{data}"
''' + (f'unixsocket "{socket_path}"\nunixsocketperm 700\n' if socket_path else '')


def acl_text(runtime_password,readonly_password):
    hashes=[sha(p.encode()) for p in [runtime_password,readonly_password]]
    if any(len(p)<32 or not all(c in '0123456789abcdef' for c in p) for p in [runtime_password,readonly_password]):
        raise ValueError('generated random hex required')
    connect='+auth +hello +ping +select +quit +client|setname'
    patterns='~marketplace-rate:v1:wb:* ~marketplace-rate:v1:ozon:*'
    return ('user default off resetpass resetkeys -@all\n'
       f'user quota_runtime on #{hashes[0]} {patterns} -@all {connect} +time +get +set +eval +scan +mget\n'
       f'user quota_readonly on #{hashes[1]} {patterns} -@all {connect} +time +info|server +exists +pttl\n')


def guard(data,initialized,permit,uid,marker_uid=0,hold=None):
    """Refuse a silent empty reinitialization after successful bootstrap."""
    trusted(data,uid,0o700)
    if hold is not None and hold.exists():
        trusted(hold,marker_uid,0o640)
        raise ValueError('operator recovery hold')
    if initialized.exists():
        trusted(initialized,marker_uid,0o640)
        manifest=data/'appendonlydir/appendonly.aof.manifest'
        trusted(manifest,uid)
        if not manifest.read_bytes():raise ValueError('missing persistence manifest')
    else:
        trusted(permit,marker_uid,0o640)
        if list(data.iterdir()):raise ValueError('first start must be empty')


def assert_local_listener(ss_text,port=PORT):
    found=[]
    for row in ss_text.splitlines():
        fields=row.split()
        if len(fields)<5:continue
        local=fields[3]
        if local.rsplit(':',1)[-1]==str(port):found.append(local)
    if not found or any(x!='127.0.0.1:'+str(port) for x in found):
        raise ValueError('expected loopback-only Redis listener')
