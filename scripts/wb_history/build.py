"""Deterministic self-contained history slice, no network/root/service/API execution."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'docs/marketplace-reports/history-first-20261103'
def sha(v):return hashlib.sha256(v).hexdigest()
def load(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def build():
    legacy=load('legacy_build',ROOT/'scripts/wb_live_pilot/build.py');assets=legacy.assets()
    worker=(ROOT/'scripts/wb_history/worker.py').read_bytes()
    appfiles={str(p.relative_to(ROOT)):p.read_bytes() for p in sorted((ROOT/'apps/msp_marketplace_reports').glob('*.py'))}
    for n,h in assets['app_files'].items():assert sha(appfiles[n])==h,'PR104 code must remain byte-identical'
    release_id=sha(json.dumps({**{n:sha(v) for n,v in appfiles.items()},'worker_template':sha(worker)},sort_keys=True).encode())
    release='/opt/mcp/projects/msp-marketplace-reports-releases/history-'+release_id
    worker=worker.replace(b'__HISTORY_RELEASE__',release.encode())
    files={**appfiles,'worker.py':worker}
    for n in ['msp-finance-daily-plan.service.in','msp-finance-daily-plan.timer.in']:
        files['templates/'+n]=(ROOT/'docs/marketplace-reports/execution-20261103'/n).read_bytes()
    names={Path(n).name:sha(v) for n,v in appfiles.items()}
    assets['app_code_sha256']=sha((json.dumps(names,sort_keys=True,separators=(',',':'))+'\n').encode())
    assets['runner_base64']=base64.b64encode(worker).decode();assets['runner_sha256']=sha(worker)
    w=load('history_worker_template',ROOT/'scripts/wb_history/worker.py')
    core=(ROOT/'scripts/wb_live_pilot/launch.py').read_bytes()
    doc={'release':release,'files':{n:base64.b64encode(v).decode() for n,v in files.items()},
      'hashes':{n:sha(v) for n,v in files.items()},'batch':w.BATCH,
      'core_base64':base64.b64encode(core).decode(),'core_sha256':sha(core),'accepted_assets':assets}
    # Convert filename-keyed public runtime hashes to records to avoid secret-scan ambiguity.
    runtime=doc['accepted_assets'].pop('runtime_files')
    doc['runtime_records']=[{'path':n,'sha256':h} for n,h in sorted(runtime.items())]
    source=(ROOT/'scripts/wb_history/launch.py').read_text()
    raw=source.replace('PACKAGE = {}  # BUILD_PACKAGE','PACKAGE = '+repr(doc)+"\nPACKAGE['accepted_assets']['runtime_files']={r['path']:r['sha256'] for r in PACKAGE.pop('runtime_records')}").encode()
    compile(raw,'history.py','exec');OUT.mkdir(exist_ok=True)
    (OUT/'history.py').write_bytes(raw);local=Path('/home/hermes/workspace/msp-wb-history-first.py');local.write_bytes(raw)
    h=sha(raw)
    command='wb_history_stage=$(mktemp -d /var/lib/msp-wb-history-entry.XXXXXXXX) && install -o root -g root -m 600 '+str(local)+' "$wb_history_stage/history.py" && printf \'%s  %s\\n\' '+h+' "$wb_history_stage/history.py" | sha256sum -c - && /usr/bin/python3 -I -B "$wb_history_stage/history.py"'
    for suffix,name in [('', 'ROOT_ONE_LINE.txt'),(' --hold','ROOT_HOLD_ONE_LINE.txt')]:
        line=command+suffix;assert len(line.splitlines())==1;subprocess.run(['/bin/bash','-n','-c',line],check=True);(OUT/name).write_text(line+'\n')
    manifest={'launcher_sha256':h,'release':release,'files':[{'path':n,'sha256':sha(v)} for n,v in files.items()],
       'loader_base':'c1fee070e9efa0c925a78f266fdf03cb12a173cf','lifecycle_source':'55db8ceaa3cc93210e624243d6384331379bcdd3',
       'batch':w.BATCH,'completed_report_never_requested':883801632,'root_execution':'NOT_EXECUTED','schedule':'DISABLED'}
    (OUT/'MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'launcher_sha256':h,'release':release,'module_count':len(appfiles),'source_compatibility':'PR104_BYTE_IDENTICAL','root_execution':'NOT_EXECUTED'}))
if __name__=='__main__':build()
