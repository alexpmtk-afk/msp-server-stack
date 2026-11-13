import sys,os,json,tempfile,hashlib
from pathlib import Path
from unittest.mock import patch
def deny(event,args):
 if event in ('socket.connect','socket.bind','socket.getaddrinfo'):raise RuntimeError('NETWORK DENIED')
sys.addaudithook(deny)
P=Path(os.environ.get('RECOVERY_TEST_PAYLOAD',str(Path(__file__).parent/'payload')))
sys.path.insert(0,str(P/'ozon_novokshenov'));sys.path.insert(0,str(P))
import capture_worker as w
import verify_results as v
with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as tmp:
 base=Path(tmp);archive=base/'archive';history=archive/'history';state=history/'2026-11';state.mkdir(parents=True)
 for m in (w,v):m.ARCHIVE=archive;m.HISTORY=history
 w.STATE=state;w.PERIOD='2026-11';w.BUDGET=128
 # Retained source fixture, including a complete old multi-page day.
 for n in range(1,14):
  day=f'2026-11-{n:02d}';d=state/day;d.mkdir();pages=2 if n==1 else 1
  for i in range(1,pages+1):
   row={'date':day,'accrual_id':n*10+i,'accrued_category':'NON_ITEM','total_amount':{'amount':'-1.00','currency':'RUB'},'non_item_fee':{'type_id':46,'accrued':{'amount':'-1.00','currency':'RUB'}}}
   raw=w.doc({'accruals':[row],'last_id':'next' if i<pages else ''});stem=d/f'{i:03d}'
   stem.with_suffix('.entry.json').write_bytes(w.doc({'cabinet':w.CABINET,'method':w.PATH,'body':{'date':day,'last_id':'' if i==1 else 'next'},'send_entry_number':n+i-1 if n==1 else n+1}))
   stem.with_suffix('.response.json').write_bytes(raw);stem.with_suffix('.meta.json').write_bytes(w.doc({'status':200,'sha256':w.sha(raw),'bytes':len(raw),'truncated':False,'received_epoch':1}))
 # Recovery lease extends time only, never the original cumulative128-entry budget.
 lease={'cabinet':w.CABINET,'period':'2026-11','max_send_entries':128,'nonce':'a'*32,'expires_epoch':w.time.time()+23*3600}
 with patch.object(w.Path,'lstat',return_value=type('St',(),dict(st_mode=0o100644,st_uid=0,st_nlink=1))()),patch.object(w.Path,'read_bytes',return_value=w.doc(lease)):
  w.check_job()
 original={str(p):p.read_bytes() for p in state.glob('*/*.json')}
 job={'cabinet':w.CABINET,'period':'2026-11','max_send_entries':128,'nonce':'a'*32,'expires_epoch':w.time.time()+600}
 with patch.object(w,'check_job',return_value=job),patch.object(w,'seed',return_value=b'fixture'),patch.object(w,'strict_json',return_value={}),patch.object(w,'types_catalog',return_value={46:{'description':'Placement'}}),patch.object(w,'load_credentials',return_value={w.CABINET:{}}),patch.dict(os.environ,{'CREDENTIALS_DIRECTORY':str(base)}),patch.object(w.MonthQuota,'reserve',side_effect=AssertionError('NO HTTP OR QUOTA')),patch.object(w.time,'sleep'):
  result=w.execute();again=w.execute()
 assert result['rows']==14 and result['send_entries']==14 and again['generation']==result['generation']
 assert all(Path(p).read_bytes()==raw for p,raw in original.items())
 checked=v.verify_months({'cabinet':w.CABINET,'from_month':11,'to_month':11,'months':[result]},check_inodes=False);assert checked['verified_days']==13
 # A disconnected quota backend before sender entry is safely pausable.
 fresh=base/'fresh';fresh.mkdir();w.STATE=fresh
 with patch.object(w,'check_job',return_value=job),patch.object(w.MonthQuota,'reserve',side_effect=ConnectionError('quota unavailable')):
  try:w.fetch_day_page('2026-11-02',1,'',{})
  except w.Paused:pass
  else:raise AssertionError('quota disconnect not paused')
 assert not list(fresh.glob('*/*.entry.json'))
 print('PASS: replay14retainedpages/13days, zero quota/HTTP, stable generation/budget, independent verifier and pre-entry quota pause')
