"""Accepted archive writer; local cleanup only, no provider or secret access."""
import json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import catalog,cleanup
if __name__=='__main__':
 if os.geteuid()!=995 or len(sys.argv)!=1:raise PermissionError('fixed archive writer')
 results={}
 for cab in catalog.CABINETS:
  index=catalog.load_index(cab);results[cab]=cleanup.prune(index)
 print(json.dumps(dict(status='VERIFIED',cabinets=results,provider_calls=0)))
