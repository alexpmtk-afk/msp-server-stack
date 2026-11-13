import unittest,sys,json,calendar,tempfile,importlib.util,subprocess
from pathlib import Path
from unittest.mock import patch
B=Path(__file__).parent;P=B/'payload'
sys.path.insert(0,str(P));import chain as c;import start_root as s

def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

class ChainTests(unittest.TestCase):
 def test_fixed_order_and_each_verified_before_next(self):
  calls=[]
  def run(args,**kw):
   calls.append(args)
   return b'{"verification":"PASS"}' if args[-1].endswith('verify_results.py') else b''
  with patch.object(c.os,'geteuid',return_value=0),patch.object(c.r,'verify_payload'),patch.object(c.r,'trust'),patch.object(c.Path,'read_bytes',return_value=json.dumps(dict(cabinets=list(c.CABINETS),start_before_epoch=c.time.time()+600)).encode()),patch.object(c.r,'save'),patch.object(c.r,'run',side_effect=run),patch.object(c,'progress'):
   self.assertEqual(c.execute(),0)
  self.assertEqual([Path(a[3]).parent.name for a in calls],['ozon_novokshenov']*3+['ozon_laser_master']*3)
  self.assertEqual([Path(a[3]).name for a in calls],['year_root.py','year_root.py','verify_results.py']*2)
 def test_unknown_outcome_stops_chain(self):
  calls=[]
  def run(args,**kw):
   calls.append(args)
   if args[-1]!='--cleanup':raise RuntimeError('fixture')
   return b''
  with patch.object(c.os,'geteuid',return_value=0),patch.object(c.r,'verify_payload'),patch.object(c.r,'trust'),patch.object(c.Path,'read_bytes',return_value=json.dumps(dict(cabinets=list(c.CABINETS),start_before_epoch=c.time.time()+600)).encode()),patch.object(c.r,'save'),patch.object(c.r,'run',side_effect=run),patch.object(c,'progress') as progress:
   self.assertEqual(c.execute(),1);self.assertEqual(progress.call_args.args[0],'HOLD')
  self.assertFalse(any('ozon_laser_master' in str(a) for a in calls))
 def test_nonroot_installer_refuses(self):
  with patch.object(s.os,'geteuid',return_value=1001),patch.object(s.r,'verify_payload') as verify:
   with self.assertRaises(PermissionError):s.main()
   verify.assert_not_called()
 def test_fixed_start_only_policy_no_pkcheck(self):
  text=s.rule_text().decode();self.assertIn('subject.user === "hermes"',text);self.assertIn('action.lookup("verb") === "start"',text);self.assertIn(c.UNIT,text)
  self.assertNotIn('pkcheck',s.main.__code__.co_consts)
 def test_service_no_restart_and_cleanup(self):
  text=s.service_text().decode();self.assertIn('Restart=no',text);self.assertIn(' --cleanup',text)

class ChildTests(unittest.TestCase):
 def test_both_cabinets_all_ten_months_and_corruption(self):
  # Separate processes ensure no cross-cabinet module-global leakage.
  for cabinet in c.CABINETS:
   out=subprocess.run([sys.executable,str(B/'test_remaining.py'),'--child',cabinet],capture_output=True,text=True)
   self.assertEqual(out.returncode,0,out.stdout+out.stderr)

 def test_dmitrieva_and_november_excluded(self):
  for cabinet in c.CABINETS:
   worker=(P/cabinet/'capture_worker.py').read_text();self.assertNotIn("CABINET='ozon_dmitrieva'",worker);self.assertIn("re.fullmatch('2026-(0[1-9]|10)'",worker)
   self.assertNotIn("if PERIOD=='2026-01'",worker)

def child(cabinet):
 sys.path.insert(0,str(P/cabinet))
 import capture_worker as w;import verify_results as v
 from apps.msp_marketplace_reports.providers import Request
 with tempfile.TemporaryDirectory(dir=B) as tmp:
  archive=Path(tmp)/'archive';archive.mkdir();history=archive/'history';history.mkdir()
  w.ARCHIVE=v.ARCHIVE=archive;w.HISTORY=v.HISTORY=history
  assert w.CABINET==v.CABINET==cabinet
  months=[]
  for m in range(1,11):
   w.PERIOD=f'2026-{m:02d}';w.STATE=history/w.PERIOD;w.STATE.mkdir();w.BUDGET=128
   days=[]
   for n in range(1,calendar.monthrange(2026,m)[1]+1):
    day=f'{w.PERIOD}-{n:02d}';d=w.STATE/day;d.mkdir()
    row=dict(date=day,accrual_id=n,accrued_category='NON_ITEM',non_item_fee=dict(type_id=46,accrued=dict(amount='-0.10',currency='RUB')),total_amount=dict(amount='-0.10',currency='RUB'))
    raw=w.doc(dict(accruals=[row],last_id=''));(d/'001.response.json').write_bytes(raw)
    (d/'001.meta.json').write_bytes(w.doc(dict(status=200,sha256=w.sha(raw),bytes=len(raw),truncated=False)))
    (d/'001.entry.json').write_bytes(w.doc(dict(cabinet=cabinet,method=w.PATH,body=dict(date=day,last_id=''))))
    days.append(dict(date=day,rows=[row],pages=[dict(page=1,sha256=w.sha(raw))],status='CURSOR_EXHAUSTED_UNRECONCILED'))
   result=w.write_views(days,{46:dict(description='Placement')});result.update(days_collected=len(days),send_entries=len(days));months.append(w.publish_month(result))
  doc=dict(cabinet=cabinet,from_month=1,to_month=10,months=months)
  result=v.verify_months(doc,check_inodes=False)
  assert result['verified_days']==304 and result['verified_new_send_entries']==304 and result['verified_rows']==304
  assert result['january_external_reconciliation_complete'] is False
  # Job allowlist, including online January and rejecting cabinet/period/budget drift.
  job=dict(cabinet=cabinet,period='2026-01',max_send_entries=128,nonce='a'*32,expires_epoch=w.time.time()+600)
  with patch.object(w.Path,'lstat',return_value=type('St',(),dict(st_mode=0o100644,st_uid=0,st_nlink=1))()),patch.object(w.Path,'read_bytes',side_effect=lambda:w.doc(job)):
   assert w.check_job()['period']=='2026-01'
   for field,value in [('cabinet','ozon_dmitrieva'),('period','2026-11'),('max_send_entries',129)]:
    old=job[field];job[field]=value
    try:w.check_job()
    except ValueError:pass
    else:raise AssertionError('scope accepted')
    job[field]=old
  p=history/'2026-01/2026-01-01/001.response.json';p.write_bytes(p.read_bytes()+b' ')
  try:v.verify_months(doc,check_inodes=False)
  except ValueError:pass
  else:raise AssertionError('corruption accepted')
  w.STATE=history/'unknown';w.STATE.mkdir();w.PERIOD='2026-01'
  class Opener:
   def open(self,*args,**kwargs):raise TimeoutError('unknown')
  with patch.object(w,'check_job'),patch.object(w.MonthQuota,'reserve',return_value=[]),patch.object(w,'_headers',return_value={}):
   try:w.fetch_day_page('2026-01-01',1,'',{},factory=Opener)
   except TimeoutError:pass
   else:raise AssertionError('timeout not retained')
   try:w.fetch_day_page('2026-01-01',1,'',{},factory=Opener)
   except ValueError:pass
   else:raise AssertionError('unknown outcome retried')
 print(cabinet,'304 days, 10 months, source/publication and negative controls PASS')

if __name__=='__main__':
 def deny(event,args):
  if event in ('socket.connect','socket.bind','socket.getaddrinfo'):raise RuntimeError('NETWORK DENIED')
 sys.addaudithook(deny)
 if len(sys.argv)>1 and sys.argv[1]=='--child':child(sys.argv[2])
 else:unittest.main(verbosity=2)
