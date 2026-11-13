"""Owner/operator entry: queue one past-date download, no secrets or model calls."""
import argparse,datetime,json,os,subprocess,uuid
from pathlib import Path
from zoneinfo import ZoneInfo
REQUESTS=Path('/home/hermes/.local/state/msp-ozon-daily-requests')
CABINETS=('ozon_dmitrieva','ozon_novokshenov','ozon_laser_master')

def main():
    p=argparse.ArgumentParser();dates=p.add_mutually_exclusive_group(required=True)
    dates.add_argument('--yesterday',action='store_true');dates.add_argument('--date')
    p.add_argument('--cabinet',choices=CABINETS,action='append');args=p.parse_args()
    if os.geteuid()!=1001:raise PermissionError('Run as hermes')
    today=datetime.datetime.now(ZoneInfo('Europe/Moscow')).date()
    day=today-datetime.timedelta(days=1) if args.yesterday else datetime.date.fromisoformat(args.date)
    if not datetime.date(2026,11,13)<=day<today:raise ValueError('Past dates only, starting 2026-11-13')
    cabinets=list(dict.fromkeys(args.cabinet or CABINETS));ident=uuid.uuid4().hex
    raw=(json.dumps({'request_id':ident,'day':day.isoformat(),'cabinets':cabinets},sort_keys=True)+'\n').encode()
    path=REQUESTS/(ident+'.json');tmp=REQUESTS/('.'+ident+'.partial')
    fd=os.open(tmp,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    try:os.write(fd,raw);os.fchmod(fd,0o600);os.fsync(fd)
    finally:os.close(fd)
    os.rename(tmp,path);fd=os.open(REQUESTS,os.O_DIRECTORY|os.O_RDONLY)
    try:os.fsync(fd)
    finally:os.close(fd)
    start=subprocess.run(['/usr/bin/systemctl','start','--no-block','msp-ozon-daily.service'],capture_output=True)
    print(json.dumps({'status':'QUEUED' if start.returncode==0 else 'QUEUED_START_UNCONFIRMED','request_id':ident,'day':day.isoformat(),'cabinets':cabinets,'receipt':'/var/lib/msp-ozon-daily/cycles/manual-'+ident+'.public.json'},ensure_ascii=False))
if __name__=='__main__':main()
