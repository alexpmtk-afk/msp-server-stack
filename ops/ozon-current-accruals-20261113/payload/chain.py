"""Fixed two-cabinet sequence, no model calls or repeat of Dmitrieva."""
import os,sys,json,time,subprocess,uuid,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import root_common as r
ROOT=Path(__file__).resolve().parent
CABINETS=('ozon_dmitrieva','ozon_novokshenov','ozon_laser_master')
UNIT='msp-ozon-current-accruals-2026.service'
RULE=Path('/etc/polkit-1/rules.d/48-msp-ozon-current-accruals-2026.rules')
PUBLIC=Path('/var/lib/msp-finance-control/results/ozon-current-accruals-2026.json')
TASK='ozon-current-accruals-2026-20261113'

def replace(path,value):
    if path.exists():r.trust(path,0o644)
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    r.save(temp,r.doc(value),0o644);os.replace(temp,path);r.syncdir(path.parent)

def progress(status,done,**extra):
    replace(PUBLIC,dict(status=status,cabinets=list(CABINETS),year=2026,from_month=11,to_month=11,completed_cabinets=done,background_model_calls=0,**extra))

def child(cabinet,script,*args):
    return ['/usr/bin/python3','-I','-B',str(ROOT/cabinet/script),*args]

def cleanup():
    if os.geteuid()!=0:raise PermissionError('root required')
    # Cleanup only known child controls; each child authenticates exact hashes.
    for cabinet in CABINETS:r.run(child(cabinet,'year_root.py','--cleanup'))
    own=ROOT/'ownership.json';r.trust(own,0o600);expected=json.loads(own.read_bytes())
    if RULE.exists():
        r.trust(RULE,0o644)
        if r.sha(RULE.read_bytes())!=expected['rule_sha256']:raise ValueError('foreign rule')
        RULE.unlink();r.syncdir(RULE.parent)
    if PUBLIC.exists():
        value=json.loads(PUBLIC.read_bytes());value['activation_policy_removed']=not RULE.exists();replace(PUBLIC,value)

def execute():
    if os.geteuid()!=0:raise PermissionError('root required')
    r.verify_payload();approval=ROOT/'approval.json';r.trust(approval,0o644);a=json.loads(approval.read_bytes())
    if a.get('cabinets')!=list(CABINETS) or not time.time()<a['start_before_epoch']<=time.time()+1200:raise ValueError('approval scope/expiry')
    done=[];progress('RUNNING',done)
    try:
        for cabinet in CABINETS:
            progress('RUNNING',done,current_cabinet=cabinet)
            r.save(ROOT/cabinet/'approval.json',r.doc(dict(cabinet=cabinet,year=2026,from_month=11,to_month=11,start_before_epoch=time.time()+1200,max_new_send_entries=128)),0o644)
            try:r.run(child(cabinet,'year_root.py'),timeout=100000)
            finally:r.run(child(cabinet,'year_root.py','--cleanup'))
            verification=json.loads(r.run(child(cabinet,'verify_results.py'),timeout=3600))
            if verification.get('verification')!='PASS':raise ValueError('cabinet verification failed')
            done.append(dict(cabinet=cabinet,**verification));progress('RUNNING',done)
        progress('SOURCE_COLLECTION_COMPLETE',done)
        return 0
    except Exception as exc:
        progress('HOLD',done,error_type=type(exc).__name__,frames=[dict(file=Path(f.filename).name,function=f.name,line=f.lineno) for f in traceback.extract_tb(exc.__traceback__)[-6:]])
        return 1

def verify():
    value=json.loads(PUBLIC.read_bytes())
    if value['status']!='SOURCE_COLLECTION_COMPLETE' or value.get('activation_policy_removed') is not True or [x['cabinet'] for x in value['completed_cabinets']]!=list(CABINETS):raise ValueError('chain incomplete')
    verified=[json.loads(r.run(child(c,'verify_results.py'),timeout=3600)) for c in CABINETS]
    if any(x.get('verification')!='PASS' for x in verified):raise ValueError('verification failed')
    print(json.dumps(dict(verification='PASS',cabinets=list(CABINETS),verified_snapshots=3,verified_days=sum(x['verified_days'] for x in verified),verified_rows=sum(x['verified_rows'] for x in verified))))

if __name__=='__main__':
    if sys.argv[1:]==['--cleanup']:cleanup()
    elif sys.argv[1:]==['--verify']:verify()
    elif not sys.argv[1:]:raise SystemExit(execute())
    else:raise ValueError('fixed command only')
