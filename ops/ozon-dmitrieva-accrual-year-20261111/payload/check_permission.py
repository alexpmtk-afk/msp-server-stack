"""Permission check only; never starts a unit."""
import os,subprocess
if os.geteuid()!=1001:raise PermissionError('expected owner agent identity')
raise SystemExit(subprocess.run(['/usr/bin/pkcheck','--action-id','org.freedesktop.systemd1.manage-units','--process',str(os.getpid()),'--detail','unit','msp-ozon-dmitrieva-accruals-2026.service','--detail','verb','start'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode)
