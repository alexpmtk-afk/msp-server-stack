#!/usr/bin/env python3
import json,subprocess,sys,urllib.request
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from apps.operator_layer.release import version_report
from apps.operator_layer.rpc import call
workspace=subprocess.run(['git','rev-parse','HEAD'],cwd=Path(__file__).resolve().parents[2],capture_output=True,text=True,check=True).stdout.strip()
with urllib.request.urlopen(urllib.request.Request('https://api.github.com/repos/alexpmtk-afk/msp-server-stack/git/ref/heads/main',headers={'User-Agent':'MSP-Version-Acceptance'}),timeout=20) as r:canonical=json.load(r)['object']['sha']
try:state=call('/run/msp-operator/remote.sock','registered_service_status',{'component':'msp-data-catalog'})
except (OSError,ValueError):state={}
print(json.dumps(version_report(workspace,canonical,state.get('installed_release_sha'),state.get('running_release_sha')),indent=2))
