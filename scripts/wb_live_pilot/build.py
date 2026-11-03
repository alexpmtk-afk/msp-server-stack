"""Build reproducible self-contained E launcher; never executes root/API code."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tarfile

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'docs/marketplace-reports/live-pilot-20261103'

def sha(d):return hashlib.sha256(d).hexdigest()

def assets():
    manifest=json.loads((ROOT/'docs/marketplace-reports/deployment/autonomous-wb/INSTALL_MANIFEST.json').read_text())
    for n,digest in manifest['files'].items():
        assert sha((ROOT/n).read_bytes())==digest,'accepted PR104 drift'
    spec=importlib.util.spec_from_file_location('bootstrap_package_reader',ROOT/'scripts/wb_bootstrap/install.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    wheel=Path('/home/hermes/.hermes/cache/scratch/redis-8.1.0-py3-none-any.whl')
    assert sha(wheel.read_bytes())==manifest['dependency_candidate']['sha256']
    files={'lib/python3.12/site-packages/'+n:sha(v) for n,v in mod.wheel_files(wheel).items()}
    files.update(json.loads((ROOT/'docs/marketplace-reports/recovery-20261103/REPAIR_MANIFEST.json').read_text())['generated_runtime_files'])
    tar=ROOT/'docs/marketplace-reports/bootstrap-20261103/bootstrap.tar'
    assert sha(tar.read_bytes())=='eb2ac87f8ad6221c230fdf28b2cb384645e1018f1845b4d7e60f7a943c67767b'
    with tarfile.open(tar) as archive:
        template=archive.extractfile('staged.service.in').read()
        plan=archive.extractfile('pilot-plan.json').read()
    unit=template.decode().replace('@RELEASE_SHA@',mod.CODE)+'\nPrivateNetwork=yes\n'
    runner=(ROOT/'scripts/wb_live_pilot/runner.py').read_bytes()
    return {'code_sha':mod.CODE,'app_files':manifest['files'],'app_code_sha256':manifest['code_sha256'],
            'runtime_files':files,'runtime_links':{'lib64':'lib','bin/python':'python3','bin/python3':'/usr/bin/python3','bin/python3.12':'python3'},
            'python_sha256':mod.PYTHON_SHA,'base_unit_sha256':sha(unit.encode()),
            'plan_file_sha256':sha(plan),'runner_sha256':sha(runner),'runner_base64':base64.b64encode(runner).decode(),
            'synthetic_probe_sha256':sha((ROOT/'docs/marketplace-reports/pilot-next-20261103/synthetic_quota.py').read_bytes())}

def build():
    OUT.mkdir(exist_ok=True)
    doc=assets();raw=(ROOT/'scripts/wb_live_pilot/launch.py').read_text()
    prepared=raw.replace('ASSETS = {}  # BUILD_EMBED_ASSETS','ASSETS = '+repr(doc)).encode()
    assert prepared==raw.replace('ASSETS = {}  # BUILD_EMBED_ASSETS','ASSETS = '+repr(assets())).encode()
    (OUT/'pilot.py').write_bytes(prepared)
    local=Path('/home/hermes/workspace/msp-wb-E.py');local.write_bytes(prepared)
    digest=sha(prepared)
    command='wb_E_stage=$(mktemp -d /var/lib/msp-wb-E-entry.XXXXXXXX) && install -o root -g root -m 600 '+str(local)+' "$wb_E_stage/pilot.py" && printf \'%s  %s\\n\' '+digest+' "$wb_E_stage/pilot.py" | sha256sum -c - && /usr/bin/python3 -I -B "$wb_E_stage/pilot.py"'
    for suffix,name in [('', 'ROOT_ONE_LINE.txt'),(' --hold','ROOT_HOLD_ONE_LINE.txt')]:
        line=command+suffix;assert len(line.splitlines())==1
        subprocess.run(['/bin/bash','-n','-c',line],check=True)
        (OUT/name).write_text(line+'\n')
    (OUT/'MANIFEST.json').write_text(json.dumps({**{k:v for k,v in doc.items() if k not in ('runner_base64','runtime_files')},
        'launcher_sha256':digest,'launcher_bytes':len(prepared),'runtime_regular_files':len(doc['runtime_files']),
        'prepared_source_sha':'55db8ceaa3cc93210e624243d6384331379bcdd3','root_execution':'NOT_EXECUTED',
        'purpose':'OWNER_APPROVED_E_ONE_REPORT_MAX3','source_expected_outputs':'/opt/mcp/report-run-results/wb-883801632-E.json',
        'reproducible_build':'MATCH'},indent=2)+'\n')
    print(json.dumps({'launcher_sha256':digest,'runner_sha256':doc['runner_sha256'],'runtime_files':len(doc['runtime_files']),'shell_syntax':'PASS','root_execution':'NOT_EXECUTED'}))

if __name__=='__main__':build()
