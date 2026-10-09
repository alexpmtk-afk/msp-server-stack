#!/usr/bin/env python3
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from apps.operator_layer.preflight import evaluate
p=argparse.ArgumentParser();p.add_argument('--required',nargs='+');p.add_argument('--offline',action='store_true');p.add_argument('--manifest',type=Path);a=p.parse_args()
required=json.loads(a.manifest.read_text())['required_capabilities'] if a.manifest else a.required
try:
 r=evaluate(required,live=not a.offline);print(json.dumps(r,indent=2));sys.exit(0 if r['ready'] else 2)
except ValueError as e:print(json.dumps({'error':str(e)}));sys.exit(2)
