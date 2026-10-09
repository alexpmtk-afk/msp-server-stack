#!/usr/bin/env python3
"""Read-only task discovery/context; execution uses the held Turn context API."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from apps.operator_layer.tasks import Journal
p=argparse.ArgumentParser();p.add_argument('--journal',required=True);p.add_argument('--task');a=p.parse_args()
j=Journal(a.journal)
print(json.dumps(j.get(a.task) if a.task else j.unfinished(),ensure_ascii=False,indent=2))
