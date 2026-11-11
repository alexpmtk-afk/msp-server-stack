"""Start exactly one deterministic root supervisor, not a timer or LLM job."""
import os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_root as r
import history_root as h

def main():
    if os.geteuid()!=0:raise PermissionError('root console required')
    r.verify_payload()
    # Preflight before scheduling, AND again under controller.lock in supervisor.
    h.preflight()
    service='msp-ozon-history-20261111.service'
    loaded=r.run(['/usr/bin/systemctl','show',service,'-p','LoadState']).decode()
    if loaded.strip()!='LoadState=not-found':raise ValueError('prior history service exists; reconcile instead of restart')
    r.run(['/usr/bin/systemd-run','--no-block','--unit='+service,'--description=Ozon Jan-Oct2026 fixed realization archive',
           '--property=Type=oneshot','--property=Restart=no','--property=UMask=0077',
           '--property=TimeoutStartSec=7200','--property=RuntimeMaxSec=7200',
           '--property=NoNewPrivileges=yes',
           '--property=ExecStopPost=/usr/bin/python3 -I -B '+str(h.ROOT/'history_root.py')+' --cleanup',
           '/usr/bin/python3','-I','-B',str(h.ROOT/'history_root.py')])
    state=r.run(['/usr/bin/systemctl','show',service,'-p','LoadState','-p','ActiveState']).decode()
    print('HISTORY_SCHEDULED_NOT_YET_COMPLETE')
    print(state.strip())
    print('PROGRESS '+str(h.PUBLIC))

if __name__=='__main__':main()
