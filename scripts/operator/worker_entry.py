"""Load the same packaged dependency bootstrap as the official Hermes launcher."""
import os,sys
from pathlib import Path
sys.path.insert(0,str(Path.home()/'.hermes/hermes-agent'))
import hermes_bootstrap
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from apps.operator_layer.worker_service import main
if __name__=='__main__':main()
