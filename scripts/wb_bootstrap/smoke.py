"""Executed only in new no-network transient unit as msp-reports; no provider."""
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from apps.msp_marketplace_reports.runtime import load_credentials


def main():
    root=Path('/opt/mcp/data/msp-marketplace-reports')
    if os.geteuid()==0: raise ValueError('nonroot required')
    if os.stat(root).st_uid!=os.geteuid(): raise ValueError('archive owner')
    creds=load_credentials(Path(os.environ['CREDENTIALS_DIRECTORY'])/'cabinets.json')
    if set(creds)!={'wb_laser_master'} or set(creds['wb_laser_master'])!={'token'}:
        raise ValueError('single pilot field required')
    for forbidden in [Path('/etc/msp-marketplace-reports/cabinets.json'),
                      Path('/etc/msp-marketplace-reports-pilot/wb_laser_master.json')]:
        try: forbidden.open('rb')
        except PermissionError: pass
        else: raise ValueError('master/direct copy accessible')
    release=Path(__file__).resolve().parent
    if os.access(release,os.W_OK): raise ValueError('release writable')
    p=root/'.bootstrap-smoke'
    p.mkdir(mode=0o700)
    data=b'MSP offline storage acceptance\n'
    fd=os.open(p/'first',os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    os.write(fd,data);os.fsync(fd);os.close(fd)
    os.rename(p/'first',p/'renamed')
    dfd=os.open(p,os.O_DIRECTORY|os.O_RDONLY);os.fsync(dfd)
    assert hashlib.sha256((p/'renamed').read_bytes()).digest()==hashlib.sha256(data).digest()
    (p/'renamed').unlink();os.fsync(dfd);os.close(dfd);p.rmdir()
    dfd=os.open(root,os.O_DIRECTORY|os.O_RDONLY);os.fsync(dfd);os.close(dfd)
    # No network request: a UDP connect syscall checks route/network policy only.
    # PrivateNetwork + IPAddressDeny should reject even a numeric non-provider test route.
    s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    try:
        try: s.connect(('192.0.2.1',9))
        except OSError: pass
        else: raise ValueError('network not blocked')
    finally:s.close()
    print(json.dumps({'status':'PASS','nonroot':True,'pilot_fields':1,'storage_fsync_rename_hash':True,
                      'release_readonly':True,'master_denied':True,'network_blocked':True}))

if __name__=='__main__':main()
