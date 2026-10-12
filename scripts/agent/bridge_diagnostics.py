#!/usr/bin/env python3
"""Bounded public host/service metadata; no secrets, proc env or private sessions."""
import argparse,json,os,platform,subprocess
from datetime import datetime,timezone
COMMANDS=['status','agent-status','telegram-config-status','telegram-status','telegram-routing-status','telegram-comments-status','telegram-discussion-access','canonical-snapshot-audit','capability-probes','logs-status','audit']
p=argparse.ArgumentParser();p.add_argument('command',choices=COMMANDS);a=p.parse_args()
r={'command':a.command,'checked_at':datetime.now(timezone.utc).isoformat(),'uid':os.getuid(),'kernel':platform.system(),'scope':'bounded_public_metadata'}
for unit in ['hermes-gateway.service','hermes-dashboard.service','msp-data-sync.service','msp-data-sync.timer']:
 r[unit]=subprocess.run(['/usr/bin/systemctl','show',unit,'-p','Id','-p','ActiveState','-p','MainPID','-p','User'],capture_output=True,text=True,timeout=10).stdout
if a.command.startswith('telegram'):r['private_details']='not_exposed_to_runner'
print(json.dumps(r,indent=2))
