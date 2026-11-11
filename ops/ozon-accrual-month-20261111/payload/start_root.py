import os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import capture_root as c
import root_common as r

def main():
    if os.geteuid()!=0:raise PermissionError('root console required')
    c.preflight()
    if r.run(['/usr/bin/systemctl','show',c.SERVICE,'-p','LoadState']).strip()!=b'LoadState=not-found':
        raise ValueError('prior capture service; reconcile instead of restart')
    r.run(['/usr/bin/systemd-run','--no-block','--unit='+c.SERVICE,'--description=Ozon January accrual month capture',
           '--property=Type=oneshot','--property=Restart=no','--property=UMask=0077',
           '--property=TimeoutStartSec=11000','--property=RuntimeMaxSec=11000','--property=NoNewPrivileges=yes',
           '--property=ExecStopPost=/usr/bin/python3 -I -B '+str(c.ROOT/'capture_root.py')+' --cleanup',
           '/usr/bin/python3','-I','-B',str(c.ROOT/'capture_root.py')])
    print('ACCRUAL_MONTH_SCHEDULED_NOT_COMPLETE')
    print('PROGRESS '+str(c.PUBLIC))
if __name__=='__main__':main()
