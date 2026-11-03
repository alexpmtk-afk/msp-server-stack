"""Service-user preflight. No network. Does not grant an empty-state restart."""
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import DATA,CONFIG,guard
if __name__=='__main__':
    try:guard(DATA,CONFIG/'initialized',CONFIG/'bootstrap-permit',os.geteuid(),hold=CONFIG/'HOLD')
    except Exception as e:
        print('PERSISTENCE_HOLD;ERROR_TYPE='+type(e).__name__);raise SystemExit(1)
