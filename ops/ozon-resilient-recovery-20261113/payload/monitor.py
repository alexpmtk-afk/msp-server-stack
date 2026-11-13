"""Unprivileged wait through root-service recovery cycles; no provider calls."""
import sys,time,json,subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import controller as c
window=json.loads((c.ROOT/'monitor-window.json').read_bytes())
while time.time()<window['deadline']+180:
    if c.PUBLIC.exists():
        d=json.loads(c.PUBLIC.read_bytes())
        if d.get('root_release')!=str(c.ROOT):raise ValueError('foreign recovery progress')
        if d.get('status')=='VERIFIED':raise SystemExit(0)
        if d.get('status','').startswith('HOLD'):raise SystemExit(2)
    try:
        p=subprocess.run(['/usr/bin/systemctl','show',c.UNIT,'-p','ActiveState','-p','ExecMainStatus'],capture_output=True,text=True,timeout=10)
        if p.returncode:time.sleep(3);continue
        s=dict(x.split('=',1) for x in p.stdout.splitlines() if '=' in x)
        if s.get('ActiveState')=='failed' and s.get('ExecMainStatus')=='2':raise SystemExit(2)
        if s.get('ActiveState') in ('inactive','failed'):
            # Safe fixed-scope same-unit admission, only after confirming no live unit.
            subprocess.run(['/usr/bin/systemctl','--no-ask-password','start','--no-block',c.UNIT],capture_output=True,timeout=10)
    except (OSError,subprocess.TimeoutExpired):pass
    time.sleep(3)
raise SystemExit(2)
