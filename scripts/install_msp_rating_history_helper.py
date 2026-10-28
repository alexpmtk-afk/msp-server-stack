#!/usr/bin/env python3
"""Install only the isolated read-only rating helper from an exact git commit.

Does not replace msp_self_sku_report_cli.py, merge branches, restart services,
change marketplace data, or modify protected /opt/mcp paths.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

FILES = (
    'apps/msp_self_analytics/marketplace_rating_sources.py',
    'apps/msp_self_analytics/ozon_rating_source.py',
    'apps/msp_self_analytics/wb_rating_source.py',
    'apps/msp_self_analytics/review_source_adapter.py',
    'apps/msp_self_analytics/dated_rating_dynamics.py',
    'apps/msp_self_analytics/rating_history_query.py',
    'apps/msp_self_analytics/wb_public_review_source.py',
    'scripts/remote/msp_rating_history_cli.py',
    'scripts/remote/msp_self_sku_report_cli.py',
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-commit', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[0-9a-f]{40}', args.source_commit):
        raise SystemExit('Exact 40-character commit SHA required')
    repo = Path(__file__).resolve().parents[1]
    subprocess.run(['git', '-C', str(repo), 'cat-file', '-e', args.source_commit + '^{commit}'], check=True)
    payloads = {name: subprocess.check_output(['git', '-C', str(repo), 'show', args.source_commit + ':' + name])
                for name in FILES}
    root = Path.home() / '.local/share/msp/rating-history'
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    bundle = root / args.source_commit
    bundle.mkdir(exist_ok=True, mode=0o700)
    hashes = {}
    for name, content in payloads.items():
        dest = bundle / name
        if dest.exists() and dest.read_bytes() != content:
            raise SystemExit('Immutable bundle differs: ' + name)
        dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        dest.write_bytes(content)
        dest.chmod(0o600)
        hashes[name] = hashlib.sha256(content).hexdigest()
    script = Path.home() / '.hermes/skills/productivity/msp-self-purchases/scripts/msp_rating_history_cli.py'
    script.parent.mkdir(parents=True, exist_ok=True)
    launcher = ('#!/usr/bin/env python3\n'
                '"""Pinned read-only rating helper; see RATING_HISTORY_SOURCES_20261028.md."""\n'
                'from pathlib import Path\nimport runpy\n'
                'bundle = Path.home() / ".local/share/msp/rating-history" / ' + repr(args.source_commit) + '\n'
                'runpy.run_path(str(bundle / "scripts/remote/msp_rating_history_cli.py"), run_name="__main__")\n')
    if script.exists() and script.read_text() != launcher:
        backup = root / ('launcher-backup-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.py')
        shutil.copy2(script, backup)
    script.write_text(launcher)
    script.chmod(0o700)
    manifest = {'source_commit': args.source_commit, 'bundle': str(bundle), 'entrypoint': str(script),
                'files_sha256': hashes, 'entrypoint_sha256': hashlib.sha256(launcher.encode()).hexdigest(),
                'installed_at_utc': datetime.now(timezone.utc).isoformat(),
                'existing_main_report_replaced': False, 'services_restarted': False}
    target = bundle / 'manifest.json'
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    (root / 'active-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(json.dumps({'installed': str(script), 'manifest': str(target), 'source_commit': args.source_commit}))


if __name__ == '__main__':
    main()
