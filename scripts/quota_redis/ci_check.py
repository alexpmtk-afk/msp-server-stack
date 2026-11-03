"""Verify published bundle and run all Redis tests against its actual binaries."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[2]

def main():
    spec=importlib.util.spec_from_file_location('safe_bundle',ROOT/'scripts/wb_bootstrap/package.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    doc=ROOT/'docs/marketplace-reports/redis-package-20261103'
    summary=json.loads((doc/'PACKAGE_SUMMARY.json').read_text())
    raw=(doc/'redis-package.tar').read_bytes()
    if module.sha(raw)!=summary['bundle_sha256']:raise ValueError('published bundle checksum')
    files,manifest=module.validate(raw,summary['manifest_sha256'])
    entries={e['path']:e for e in json.loads(manifest)['files']}
    if module.sha((doc/'entry.py').read_bytes())!=summary['entry_sha256']:raise ValueError('entry checksum')
    for name in ['common.py','guard.py','install.py','manage.py','service.in','runtime-lock.json']:
        if files[name]!=(ROOT/'scripts/quota_redis'/name).read_bytes():raise ValueError('source vs artifact drift')
    import redis
    if redis.__version__!='8.1.0':raise ValueError('client version drift')
    with tempfile.TemporaryDirectory() as d:
        runtime=Path(d)
        for name,data in files.items():
            p=runtime/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);p.chmod(entries[name]['mode'])
        env=dict(os.environ,MSP_REDIS_TEST_RUNTIME=str(runtime))
        return subprocess.run([sys.executable,'-B','-m','unittest','discover','-s','tests','-p','test_msp_quota_redis.py','-v'],cwd=ROOT,env=env).returncode

if __name__=='__main__':raise SystemExit(main())
