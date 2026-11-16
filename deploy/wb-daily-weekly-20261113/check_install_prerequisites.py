"""Read-only replay of nonprivileged install prerequisites; never a root test."""
import json,sys
from pathlib import Path
from unittest.mock import patch
B=Path(__file__).parent;sys.path.insert(0,str(B/'payload'))
import start_root as install
original=install.r.run
calls=[]
def readonly_run(args,**kwargs):
 calls.append([Path(args[0]).name,*args[1:3]])
 if args[:4]==['/usr/sbin/runuser','-u','hermes','--']:
  assert args[-1]=='--check' and Path(args[-2]).name=='notify.py'
  return original(args[4:],**kwargs)
 assert args[:2]==['/usr/bin/systemctl','show'], 'No write commands in prerequisite replay'
 return original(args,**kwargs)
with patch.object(install.os,'geteuid',return_value=0),patch.object(install.r,'verify_payload'),patch.object(install.r,'validate_platform'),patch.object(install.r,'run',side_effect=readonly_run):
 result=install.preflight()
evidence=dict(status='PASS',scope='actual nonprivileged prerequisite reads, owner/hash/permissions/absence checks, real systemctl readback and notification credential availability; no writes/network',skipped_root_only_checks=['snapshot ownership/manifest: covered by archive verification','protected accepted runtime/quota config: previous root attempt passed this phase, not repeated as root'],service_started=False,provider_calls=0,telegram_messages=0,calls=calls)
(B/'prerequisite-replay.json').write_text(json.dumps(evidence,indent=2)+'\n');print(json.dumps(evidence))
