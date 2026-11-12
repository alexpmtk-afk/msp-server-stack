"""Admit one scheduled sync through the existing common task supervisor."""
from datetime import datetime
from pathlib import Path
import subprocess
from zoneinfo import ZoneInfo

def main():
    today=datetime.now(ZoneInfo('Europe/Moscow')).date().isoformat()
    script=str(Path(__file__).resolve().with_name('sync.py'))
    command=['/usr/bin/python3','/home/hermes/workspace/task-visibility/run.py',
        'msp-defects-daily-'+today,'--title','Браки и обратная связь: ежедневное обновление',
        '--verify-command','["/usr/bin/python3", "'+script+'", "verify"]',
        '--','/usr/bin/python3',script,'sync']
    return subprocess.run(command,check=False).returncode

if __name__=='__main__':raise SystemExit(main())
