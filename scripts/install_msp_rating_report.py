#!/usr/bin/env python3
"""Pin the ordinary read-only SKU report and its Python modules to a git commit.

Updates only the active default-profile report launcher, with a backup and
file hashes. No service restart, marketplace/database write or git pull.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-commit', required=True)
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f]{40}', args.source_commit):
        raise SystemExit('Exact commit required')
    repo = Path(__file__).resolve().parents[1]
    def git(*argv):
        return subprocess.check_output(['git', '-C', str(repo), *argv])
    git('cat-file', '-e', args.source_commit+'^{commit}')
    files = [p for p in git('ls-tree', '-r', '--name-only', args.source_commit,
                           'apps/msp_self_analytics').decode().splitlines() if p.endswith('.py')]
    entry = 'scripts/remote/msp_self_sku_report_cli.py'
    files.append(entry)
    root = Path.home()/'.local/share/msp/rating-report'
    bundle = root/args.source_commit
    bundle.mkdir(parents=True, exist_ok=True, mode=0o700)
    hashes = {}
    for name in files:
        data = git('show', args.source_commit+':'+name)
        dest = bundle/name
        if dest.exists() and dest.read_bytes() != data:
            raise SystemExit('Immutable source mismatch')
        dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        dest.write_bytes(data)
        dest.chmod(0o600)
        hashes[name] = hashlib.sha256(data).hexdigest()
    target = Path.home()/'.hermes/skills/productivity/msp-self-purchases/scripts/msp_self_sku_report_cli.py'
    launcher = ('#!/usr/bin/env python3\nimport runpy\n'
                'runpy.run_path('+repr(str(bundle/entry))+', run_name="__main__")\n')
    if target.exists():
        shutil.copy2(target, root/('launcher-backup-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.py'))
    temp = target.with_suffix('.installing')
    temp.write_text(launcher)
    temp.chmod(0o700)
    os.replace(temp, target)
    manifest = {'source_commit': args.source_commit, 'bundle': str(bundle),
                'entrypoint': str(target), 'files_sha256': hashes,
                'entrypoint_sha256': hashlib.sha256(launcher.encode()).hexdigest(),
                'installed_at_utc': datetime.now(timezone.utc).isoformat(),
                'services_restarted': False, 'marketplace_writes': False}
    for p in (bundle/'manifest.json', root/'active-manifest.json'):
        p.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
        p.chmod(0o600)
    print(json.dumps({'source_commit': args.source_commit, 'entrypoint': str(target), 'files': len(files)}))


if __name__ == '__main__':
    main()
