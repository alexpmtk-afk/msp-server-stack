from pathlib import Path
import shutil,json,hashlib
B=Path(__file__).parent; P=B/'payload';P.mkdir(exist_ok=True)
S=Path('/home/hermes/workspace/ozon-dmitrieva-accrual-year-20261111/payload')
sha=lambda b:hashlib.sha256(b).hexdigest()
for cabinet in ('ozon_novokshenov','ozon_laser_master'):
 d=P/cabinet;d.mkdir(exist_ok=True)
 for p in S.rglob('*'):
  rel=p.relative_to(S)
  if not p.is_file() or '__pycache__' in rel.parts or rel.name in ('MANIFEST.json','start_root.py','check_permission.py','accepted-month.json'):continue
  dest=d/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
 # Each child is fixed to its own cabinet; no credential or scope selection from CLI.
 for name in ('capture_worker.py','year_root.py','verify_results.py','root_common.py'):
  p=d/name;t=p.read_text().replace('ozon_dmitrieva',cabinet).replace('ozon-dmitrieva-accruals-2026',cabinet.replace('_','-')+'-accruals-2026-remaining').replace('msp-ozon-dmitrieva-accruals-20261111','msp-'+cabinet.replace('_','-')+'-accruals-20261112').replace('94-ozon-dmitrieva-accrual-year.conf','94-ozon-remaining-accrual-year.conf')
  if name=='year_root.py':
   a=t.index('    for name,digest in ');b=t.index('    r.trust(r.MASTER',a)
   t=t[:a]+"    p=SEED/'types.seed.json';r.trust(p,0o644)\n    if r.sha(p.read_bytes())!=TYPE_SHA:raise ValueError('type seed changed')\n"+t[b:]
   t=t.replace('1152','1280').replace("    if month==1:r.save(state/'month.csv',(SEED/'month.csv').read_bytes(),0o644)\n",'').replace('0 if month==1 else 128','128').replace("r.doc({CABINET:cred}) if month!=1 else None","r.doc({CABINET:cred})").replace('unit_text(allow,state,month!=1)','unit_text(allow,state,True)')
   t=t.replace('January independently reconciled with cabinet Excel, later months source/publication verified','all months source/publication verified; no independent cabinet Excel reconciliation')
   t=t.replace("    elif not sys.argv[1:]:raise SystemExit(execute())","    elif sys.argv[1:]==['--preflight']:preflight()\n    elif not sys.argv[1:]:raise SystemExit(execute())")
  if name=='capture_worker.py':
   t=t.replace("job['max_send_entries']!=(0 if job['period']=='2026-01' else 128)","job['max_send_entries']!=128").replace("body['date']<'2026-02-01'","body['date']<'2026-01-01'")
   a=t.index("    if PERIOD=='2026-01':",t.index('def execute():'));b=t.index("    return {**publish_month(result)",a)
   block=t[t.index('        catalog=types_catalog',a):b]
   t=t[:a]+''.join(line[4:] if line.startswith('    ') else line for line in block.splitlines(True))+t[b:]
  if name=='verify_results.py':
   a=t.index('        if m==1:');b=t.index('        published,pinned=',a)
   block=t[t.index('            cover=json.loads',a):b]
   t=t[:a]+''.join(line[4:] if line.startswith('    ') else line for line in block.splitlines(True))+t[b:]
   t=t.replace('sendcount>1152','sendcount>1280').replace("'january_external_reconciliation_complete':True","'january_external_reconciliation_complete':False")
  p.write_text(t);compile(t,str(p),'exec')
 manifest={str(p.relative_to(d)):sha(p.read_bytes()) for p in d.rglob('*') if p.is_file() and p.name!='MANIFEST.json'}
 (d/'MANIFEST.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n')
shutil.copyfile(S/'root_common.py',P/'root_common.py')
print('Prepared two fixed child payloads; no production execution')
