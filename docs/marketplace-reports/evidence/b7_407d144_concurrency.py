"""Synthetic multiprocess writers and deterministic pinned-reader interleaving."""
import argparse,importlib.util,json,socket,subprocess,sys,tempfile,threading
from pathlib import Path
from unittest.mock import patch

def audit(event,args):
 if event in ('socket.connect','socket.getaddrinfo'):raise AssertionError('Network prohibited')
sys.addaudithook(audit)
p=argparse.ArgumentParser();p.add_argument('--checkout',type=Path,required=True);p.add_argument('--root',type=Path);p.add_argument('--amount');p.add_argument('--expected');a=p.parse_args();sys.path.insert(0,str(a.checkout.resolve()))
from apps.msp_marketplace_reports import generation_store as g
spec=importlib.util.spec_from_file_location('fixtures',a.checkout/'tests/test_msp_marketplace_generations.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
def args(root):return root,'wb_weekly_finance_main','wb_laser_master','2026'
if a.root:
 sys.stdin.readline()
 try:r=g.publish_batch(*args(a.root),f.wb_files(a.amount),expected_generation=a.expected);print(json.dumps(r));sys.exit(0)
 except g.GenerationError as e:print(json.dumps({'error':str(e)}));sys.exit(2)
with tempfile.TemporaryDirectory(prefix='concurrent-',dir=str(Path(__file__).resolve().parent)) as td:
 base=Path(td)
 for initial in [True,False]:
  root=base/('initial' if initial else 'existing');prior=None
  if not initial:
   for amount in ['10','15','17']:prior=g.publish_batch(*args(root),f.wb_files(amount),expected_generation=prior['generation'] if prior else None)
  children=[]
  for amount in ['20','30']:
   cmd=[sys.executable,'-B',str(Path(__file__).resolve()),'--checkout',str(a.checkout),'--root',str(root),'--amount',amount]
   if prior:cmd+=['--expected',prior['generation']]
   children.append(subprocess.Popen(cmd,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True))
  for c in children:c.stdin.write('go\n');c.stdin.flush()
  results=[]
  for c in children:
   stdout,stderr=c.communicate(timeout=30);results.append({'returncode':c.returncode,'result':json.loads(stdout),'stderr':stderr})
  assert sorted(r['returncode'] for r in results)==[0,2],results
  assert g.read_active(*args(root))['files'] in (f.wb_files('20'),f.wb_files('30'))
  if prior:assert g.read_generation(*args(root),prior['generation'],expected_digest=prior['manifest_sha256'])['files']==f.wb_files('17')
  print(json.dumps({'check':'MULTIPROCESS_WRITERS','initial':initial,'status':'PASS','results':results}),flush=True)
 # Reader has taken CURRENT=A, but generation A is opened only after B commit.
 root=base/'reader';prior=g.publish_batch(*args(root),f.wb_files('10'));reached=threading.Event();resume=threading.Event();results=[];errors=[];original=g._read_generation;paused=[False]
 def delayed(scope,generation,expected_digest=None):
  if threading.current_thread().name=='pinned-reader' and not paused[0]:
   paused[0]=True;reached.set();assert resume.wait(20)
  return original(scope,generation,expected_digest)
 def reader():
  try:results.append(g.read_active(*args(root)))
  except BaseException as e:errors.append(repr(e))
 with patch.object(g,'_read_generation',delayed):
  t=threading.Thread(target=reader,name='pinned-reader');t.start();assert reached.wait(20)
  current=g.publish_batch(*args(root),f.wb_files('20'),expected_generation=prior['generation']);resume.set();t.join(20)
 assert not t.is_alive() and not errors and results[0]['files']==f.wb_files('10')
 assert g.read_active(*args(root))['files']==f.wb_files('20')
 print(json.dumps({'check':'PINNED_READER_ACROSS_COMMIT','status':'PASS','old_result':results[0]['generation']==prior['generation'],'new_active':g.read_active(*args(root))['generation']==current['generation']}),flush=True)
