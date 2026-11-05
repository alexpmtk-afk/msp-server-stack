"""Build next finite batch from the exact accepted PR117 artifact, no dependency refetch."""
import ast,base64,hashlib,importlib.util,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'docs/marketplace-reports/next-20261105'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def build():
 old=(ROOT/'docs/marketplace-reports/history-first-20261103/history.py').read_bytes()
 assert sha(old)=='cb1bb6e097c23ab3d42a505076f29ce4d7df4e76a3e30eb20694ed8e0e90c3ee'
 assignment=next(n for n in ast.parse(old).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PACKAGE' for t in n.targets))
 p=ast.literal_eval(assignment.value)
 worker=(ROOT/'scripts/finance_campaign/next_worker.py').read_bytes()
 release='/opt/mcp/projects/msp-marketplace-reports-releases/history-next-'+sha(worker)
 worker=worker.replace(b'__HISTORY_RELEASE__',release.encode())
 p['release']=release;p['files']['worker.py']=base64.b64encode(worker).decode();p['hashes']['worker.py']=sha(worker)
 p['accepted_assets']['runner_base64']=base64.b64encode(worker).decode();p['accepted_assets']['runner_sha256']=sha(worker)
 spec=importlib.util.spec_from_file_location('frozen_next_worker',ROOT/'scripts/finance_campaign/next_worker.py');w=importlib.util.module_from_spec(spec);spec.loader.exec_module(w);p['batch']=w.BATCH
 for name,raw in p['files'].items():
  data=base64.b64decode(raw);assert sha(data)==p['hashes'][name]
  if name.startswith('apps/'):assert data==(ROOT/name).read_bytes(),'accepted source drift'
 source=(ROOT/'scripts/finance_campaign/next_launch.py').read_text()
 raw=source.replace('PACKAGE = {}  # BUILD_PACKAGE','PACKAGE = '+repr(p)+"\nPACKAGE['accepted_assets']['runtime_files']={r['path']:r['sha256'] for r in PACKAGE.pop('runtime_records')}").encode();compile(raw,'next.py','exec')
 OUT.mkdir(exist_ok=True);(OUT/'next.py').write_bytes(raw)
 local=Path('/home/hermes/workspace/msp-wb-next-865431404.py');local.write_bytes(raw)
 command='wb_next_stage=$(mktemp -d /var/lib/msp-wb-next-entry.XXXXXXXX) && install -o root -g root -m 600 '+str(local)+' "$wb_next_stage/next.py" && printf \'%s  %s\\n\' '+sha(raw)+' "$wb_next_stage/next.py" | sha256sum -c - && /usr/bin/python3 -I -B "$wb_next_stage/next.py"'
 for suffix,name in [('', 'ROOT_ONE_LINE.txt'),(' --hold','ROOT_HOLD_ONE_LINE.txt')]:
  line=command+suffix;assert len(line.splitlines())==1;subprocess.run(['/bin/sh','-n','-c',line],check=True);(OUT/name).write_text(line+'\n')
 manifest={'launcher_sha256':sha(raw),'release':release,'files':[{'path':n,'sha256':h} for n,h in p['hashes'].items()],'batch':p['batch'],'completed_excluded':[883801632,883801636],'root_execution':'NOT_EXECUTED','schedule_enabled':False}
 (OUT/'MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps({'launcher_sha256':sha(raw),'release':release}))
if __name__=='__main__':build()
