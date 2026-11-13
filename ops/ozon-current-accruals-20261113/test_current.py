import unittest,subprocess,sys,tempfile,json,calendar,tarfile,hashlib,os
from pathlib import Path
B=Path(__file__).parent;P=Path(os.environ.get('OZON_TEST_PAYLOAD',str(B/'payload')))
CABINETS=('ozon_dmitrieva','ozon_novokshenov','ozon_laser_master')
class CurrentTests(unittest.TestCase):
 def test_three_cabinet_current_snapshot_and_scope_guards(self):
  for cabinet in CABINETS:
   p=subprocess.run([sys.executable,str(B/'test_current.py'),'--child',cabinet],capture_output=True,text=True)
   self.assertEqual(p.returncode,0,p.stdout+p.stderr)
 def test_packed_artifact_nested_manifests(self):
  with tarfile.open(B/'ozon-current-accruals.tar.gz') as tar:
   files={m.name:tar.extractfile(m).read() for m in tar.getmembers()}
   for cabinet in CABINETS:
    key=cabinet+'/MANIFEST.json';self.assertIn(key,files)
    for n,h in json.loads(files[key]).items():self.assertEqual(hashlib.sha256(files[cabinet+'/'+n]).hexdigest(),h)
   self.assertNotIn('cabinets.json',files)
 def test_nonroot_refuses_before_protected_reads(self):
  sys.path.insert(0,str(P));import start_root as s
  from unittest.mock import patch
  with patch.object(s.os,'geteuid',return_value=1001),patch.object(s.r,'verify_payload') as verify:
   with self.assertRaises(PermissionError):s.main()
   verify.assert_not_called()
 def test_three_cabinet_sequence_and_hold(self):
  sys.path.insert(0,str(P));import chain as c
  from unittest.mock import patch
  self.assertEqual(c.CABINETS,CABINETS)
  for fail,expected in [(False,0),(True,1)]:
   calls=[]
   def run(args,**kw):
    calls.append(args)
    if fail and args[-1]!='--cleanup':raise RuntimeError('fixture')
    return b'{"verification":"PASS"}' if str(args[-1]).endswith('verify_results.py') else b''
   with patch.object(c.os,'geteuid',return_value=0),patch.object(c.r,'verify_payload'),patch.object(c.r,'trust'),patch.object(c.Path,'read_bytes',return_value=json.dumps(dict(cabinets=list(CABINETS),start_before_epoch=c.time.time()+600)).encode()),patch.object(c.r,'save'),patch.object(c.r,'run',side_effect=run),patch.object(c,'progress'):
    self.assertEqual(c.execute(),expected)
   if not fail:self.assertEqual([Path(a[3]).parent.name for a in calls],[x for cabinet in CABINETS for x in [cabinet]*3])
   else:self.assertFalse(any('ozon_laser_master' in str(a) for a in calls))

def child(cabinet):
 from unittest.mock import patch
 sys.path.insert(0,str(P/cabinet));import capture_worker as w;import verify_results as v
 assert Path(w.__file__).resolve().parent==(P/cabinet).resolve()
 from apps.msp_marketplace_reports.archive import _location
 from apps.msp_marketplace_reports.providers import Request
 with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as tmp:
  archive=Path(tmp)/'archive';archive.mkdir();history=archive/'history';history.mkdir();w.ARCHIVE=v.ARCHIVE=archive;w.HISTORY=v.HISTORY=history
  w.PERIOD='2026-11';w.STATE=history/w.PERIOD;w.STATE.mkdir();w.BUDGET=128
  selfscope=_location(archive,'ozon_current_accruals',cabinet,w.PERIOD);assert 'CURRENT' in selfscope.parts and 'PERMANENT' not in selfscope.parts
  days=[]
  for n in range(1,14):
   day=f'2026-11-{n:02d}';folder=w.STATE/day;folder.mkdir()
   # An empty latest day is a retained observation, not proof financial coverage is final.
   rows=[] if n==13 else [dict(date=day,accrual_id=n,accrued_category='NON_ITEM',total_amount=dict(amount='-0.10',currency='RUB'),non_item_fee=dict(type_id=46,accrued=dict(amount='-0.10',currency='RUB')))]
   raw=w.doc(dict(accruals=rows,last_id=''));assert w.inspect_page(raw,day)['rows']==rows;(folder/'001.response.json').write_bytes(raw);(folder/'001.meta.json').write_bytes(w.doc(dict(status=200,sha256=w.sha(raw),bytes=len(raw),truncated=False)));(folder/'001.entry.json').write_bytes(w.doc(dict(cabinet=cabinet,method=w.PATH,body=dict(date=day,last_id=''))))
   days.append(dict(date=day,rows=rows,pages=[dict(page=1,sha256=w.sha(raw))],status='CURSOR_EXHAUSTED_UNRECONCILED'))
  result=w.write_views(days,{46:dict(description='Placement')});result.update(days_collected=13,send_entries=13);result=w.publish_month(result)
  checked=v.verify_months(dict(cabinet=cabinet,from_month=11,to_month=11,months=[result]),check_inodes=False)
  assert checked['verified_days']==13 and checked['verified_rows']==12 and checked['latest_nonempty_date']=='2026-11-12'
  job=dict(cabinet=cabinet,period='2026-11',max_send_entries=128,nonce='a'*32,expires_epoch=w.time.time()+600)
  with patch.object(w.Path,'lstat',return_value=type('St',(),dict(st_mode=0o100644,st_uid=0,st_nlink=1))()),patch.object(w.Path,'read_bytes',side_effect=lambda:w.doc(job)):
   w.check_job()
   job['period']='2026-10'
   try:w.check_job()
   except ValueError:pass
   else:raise AssertionError('old period admitted')
  # Scope gate runs before quota/transport.
  for date in ('2026-10-31','2026-11-14'):
   with patch.object(w.MonthQuota,'_approved_url',side_effect=AssertionError('quota touched')):
    try:w.MonthQuota('ozon',{}).reserve(Request('ozon',w.PATH,dict(date=date,last_id='')))
    except ValueError:pass
    else:raise AssertionError('out-of-range transport')
  # Never replay an unknown transport outcome.
  other=history/'unknown';other.mkdir();w.STATE=other
  class Opener:
   def open(self,*args,**kwargs):raise TimeoutError('fixture')
  with patch.object(w,'check_job'),patch.object(w.MonthQuota,'reserve',return_value=[]),patch.object(w,'_headers',return_value={}):
   try:w.fetch_day_page('2026-11-01',1,'',{},factory=Opener)
   except TimeoutError:pass
   else:raise AssertionError('timeout did not occur')
   try:w.fetch_day_page('2026-11-01',1,'',{},factory=Opener)
   except ValueError:pass
   else:raise AssertionError('unknown outcome replayed')
  w.STATE=history/'2026-11'
  f=history/'2026-11/2026-11-01/001.response.json';f.write_bytes(f.read_bytes()+b' ')
  try:v.verify_months(dict(cabinet=cabinet,from_month=11,to_month=11,months=[result]),check_inodes=False)
  except ValueError:pass
  else:raise AssertionError('corruption accepted')
 print(cabinet,'13 source days/current publication/empty latest day and guards PASS')
if __name__=='__main__':
 def deny(event,args):
  if event in ('socket.connect','socket.bind','socket.getaddrinfo'):raise RuntimeError('NETWORK DENIED')
 sys.addaudithook(deny)
 if len(sys.argv)>1 and sys.argv[1]=='--child':child(sys.argv[2])
 else:unittest.main(verbosity=2)
