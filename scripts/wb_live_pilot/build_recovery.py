"""Build a separate fail-closed recovery package; never overwrite PR115 evidence."""
import base64
import json
from pathlib import Path
import subprocess
import build as original

ROOT=original.ROOT
OUT=ROOT/'docs/marketplace-reports/live-pilot-recovery-20261103'

def build():
    doc=original.assets()
    guard=(ROOT/'scripts/wb_live_pilot/recovery_guard.py').read_bytes()
    doc.update(recovery=True,recovery_guard_sha256=original.sha(guard),recovery_guard_base64=base64.b64encode(guard).decode())
    # Public file checksums as records, avoiding misleading filename-as-secret keys.
    runtime=doc.pop('runtime_files')
    doc['runtime_records']=[{'path':k,'sha256':v} for k,v in sorted(runtime.items())]
    source=(ROOT/'scripts/wb_live_pilot/launch.py').read_text()
    source=source.replace("STATE=Path('/var/lib/msp-wb-E-883801632')", "STATE=Path('/var/lib/msp-wb-E-883801632-recovery1')")
    source=source.replace("RESULT_NAME='wb-883801632-E.json'", "RESULT_NAME='wb-883801632-E-recovery1.json'")
    marker='ASSETS = {}  # BUILD_EMBED_ASSETS'
    assert source.count(marker)==1
    prepared=source.replace(marker,'ASSETS = '+repr(doc)+"\nASSETS['runtime_files']={r['path']:r['sha256'] for r in ASSETS.pop('runtime_records')}").encode()
    compile(prepared,'recovery.py','exec')
    OUT.mkdir(exist_ok=True)
    (OUT/'recovery.py').write_bytes(prepared)
    local=Path('/home/hermes/workspace/msp-wb-E-recovery.py');local.write_bytes(prepared)
    digest=original.sha(prepared)
    command='wb_recovery_stage=$(mktemp -d /var/lib/msp-wb-E-recovery-entry.XXXXXXXX) && install -o root -g root -m 600 '+str(local)+' "$wb_recovery_stage/recovery.py" && printf \'%s  %s\\n\' '+digest+' "$wb_recovery_stage/recovery.py" | sha256sum -c - && /usr/bin/python3 -I -B "$wb_recovery_stage/recovery.py"'
    for suffix,name in [('', 'ROOT_ONE_LINE.txt'),(' --hold','ROOT_HOLD_ONE_LINE.txt')]:
        line=command+suffix
        assert len(line.splitlines())==1
        subprocess.run(['/bin/bash','-n','-c',line],check=True)
        (OUT/name).write_text(line+'\n')
    manifest={'launcher_sha256':digest,'runner_sha256':doc['runner_sha256'],'guard_sha256':doc['recovery_guard_sha256'],
        'accepted_loader_sha':doc['code_sha'],'original_failed_launcher_sha':'67e73523c38bfa6049a9fb4ee9fa7dfe3c6ed07ae565a1b1ef6ffac5724b9d93',
        'root_execution':'NOT_EXECUTED','budget':'ORIGINAL_PLAN_MAX3_CUMULATIVE_NOT_RESET',
        'old_evidence':'PRESERVED','actual_uid_read_test':'REQUIRED_BEFORE_PROVIDER_START',
        'new_result':'/opt/mcp/report-run-results/wb-883801632-E-recovery1.json',
        'root_state':'/var/lib/msp-wb-E-883801632-recovery1'}
    (OUT/'MANIFEST.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest))

if __name__=='__main__':build()
