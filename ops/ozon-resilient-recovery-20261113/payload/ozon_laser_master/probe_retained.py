import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import capture_worker as w
from recovery import reconcile_retained
w.PERIOD="2026-11";w.STATE=w.HISTORY/w.PERIOD;w.BUDGET=128
if w.STATE.exists():
 d=reconcile_retained(w);print(json.dumps(dict(completed_days=len(d),entries=len(list(w.STATE.glob("*/*.entry.json"))))))
else:print(json.dumps(dict(completed_days=0,entries=0)))
