#!/usr/bin/env python3
"""Install approved report instructions only; explicit --apply, no service changes.

Private registry is supplied separately. Google sources and business SQLite are
never modified; refresh writes only the new local instruction catalog.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

START='<!-- MSP_APPROVED_REPORTS_START -->'
END='<!-- MSP_APPROVED_REPORTS_END -->'
BLOCK='''## Отчёты, которыми можно пользоваться

Общее правило МСП для Hermes и других агентов: если в QRsite MCP нет нужных
данных по заказам, использовать утверждённый отчёт `_01_заказы`, не искать
произвольные файлы на Drive. Сначала читать
`/opt/mcp/projects/msp-server-stack/docs/data-sources/APPROVED_REPORTS.md`
или выполнить `python3 /home/hermes/.local/share/msp/approved-reports/report_catalog.py guide --report orders`.
SQL-инструкция: `/opt/mcp/data/msp/msp_report_catalog.sqlite3`.
Серверный readonly-аккаунт проверяется отдельно от Google-коннектора ChatGPT:
его 403 не означает отсутствия серверного доступа. Исходный отчёт не менять.
'''


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--registry-file',type=Path,required=True)
    p.add_argument('--apply',action='store_true')
    a=p.parse_args()
    repo=Path(__file__).resolve().parents[2]
    runtime=Path('/home/hermes/.local/share/msp/approved-reports')
    server=Path('/opt/mcp/projects/msp-server-stack')
    registry=json.loads(a.registry_file.read_text())
    if not registry.get('reports'):raise ValueError('Private registry has no reports')
    sources={repo/'apps/msp_report_catalog/catalog.py':runtime/'report_catalog.py',
             repo/'docs/data-sources/APPROVED_REPORTS.md':runtime/'GUIDE.md',
             repo/'docs/data-sources/MARKETPLACE_ORDERS.md':server/'docs/data-sources/MARKETPLACE_ORDERS.md'}
    for source in sources:
        if not source.is_file():raise ValueError('Missing prepared source '+str(source))
    if not a.apply:
        print('PREPARED; use --apply only with owner authorization');return
    runtime.mkdir(mode=0o700,parents=True,exist_ok=True)
    backup=runtime/'backups'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    backup.mkdir(mode=0o700,parents=True)
    manifest=[]
    def write(target,data,mode=0o644):
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():
            key=hashlib.sha256(str(target).encode()).hexdigest()[:16]
            shutil.copy2(target,backup/(key+'-'+target.name))
        target.write_bytes(data);target.chmod(mode)
        assert target.read_bytes()==data
        manifest.append(dict(path=str(target),sha256=hashlib.sha256(data).hexdigest()))
    for source,target in sources.items():write(target,source.read_bytes())
    write(server/'docs/data-sources/APPROVED_REPORTS.md',(runtime/'GUIDE.md').read_bytes())
    write(runtime/'registry.json',json.dumps(registry,ensure_ascii=False,indent=2).encode(),0o600)
    for target in (server/'AGENTS.md',Path('/home/hermes/workspace/AGENTS.md')):
        old=target.read_text() if target.exists() else ''
        if START in old:
            left,rest=old.split(START,1);_,right=rest.split(END,1);old=left+right
        write(target,(START+'\n'+BLOCK+END+'\n\n'+old.lstrip()).encode())
    command=[sys.executable,str(runtime/'report_catalog.py'),'refresh']
    result=subprocess.run(command,capture_output=True,text=True,timeout=90)
    if result.returncode:raise RuntimeError('Report refresh failed; files retained for diagnosis: '+result.stdout[:500])
    os.chmod('/opt/mcp/data/msp/msp_report_catalog.sqlite3',0o600)
    write(runtime/'installation.json',json.dumps(dict(files=manifest,google_writes=0,business_rows_imported=0,schedules_changed=0,refresh=result.stdout.strip()),ensure_ascii=False,indent=2).encode(),0o600)
    print(result.stdout.strip())
    print('INSTALLED_LOCAL_REPORT_REGISTRY; source code and guide readback verified')


if __name__=='__main__':main()
