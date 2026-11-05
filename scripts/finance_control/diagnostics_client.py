"""Fixed unprivileged read-only diagnostic trigger; never starts a download."""
import json,os,subprocess,sys
from pathlib import Path
STATE=Path('/var/lib/msp-finance-control')
def main():
 if os.geteuid()!=1001 or sys.argv[1:]:raise ValueError('hermes, no arguments')
 p=subprocess.run(['/usr/bin/systemctl','--no-ask-password','start','msp-finance-diagnostics.service'],env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
 if p.returncode:raise RuntimeError('diagnostic failed; no retry/download')
 print((STATE/'results/diagnostics-latest.json').read_text())
if __name__=='__main__':main()
