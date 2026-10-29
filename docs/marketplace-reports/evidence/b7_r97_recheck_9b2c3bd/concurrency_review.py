import argparse,base64,contextlib,importlib.util,json,os,select,subprocess,sys,tempfile
from pathlib import Path

def audit(event,args):
 if event in ('socket.connect','socket.getaddrinfo'):raise AssertionError('Network denied')
sys.addaudithook(audit)
p=argparse.ArgumentParser();p.add_argument('--checkout',type=Path,required=True);p.add_argument('--request',type=Path);p.add_argument('--child',choices=['repair_first','writer','repair_second']);a=p.parse_args();sys.path.insert(0,str(a.checkout.resolve()))
from apps.msp_marketplace_reports import archive as ar,generation_store as gs,current_repair as cr,versioned_archive as va
spec=importlib.util.spec_from_file_location('fixtures',a.checkout/'tests/test_msp_marketplace_generations.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
def args(root):return root,'wb_weekly_finance_main','wb_laser_master','2026'
if a.child:
 d=json.loads(a.request.read_text());root=Path(d['root']);params=d['params']
 if a.child=='repair_first':
  def gate(point):
   if point=='after_prepare':print('PREPARED',flush=True);sys.stdin.readline()
  print(json.dumps(cr.repair_current_with_witness(*args(root),**params,fault=gate)));sys.exit(0)
 target=va if a.child=='writer' else cr;original=target._lock
 @contextlib.contextmanager
 def gated(*aa,**kk):
  print('ATTEMPT',flush=True)
  with original(*aa,**kk):print('HELD',flush=True);sys.stdin.readline();yield
 target._lock=gated
 result=va.import_csv_versioned(*args(root),Path(d['source'])) if a.child=='writer' else cr.repair_current_with_witness(*args(root),**params)
 print(json.dumps(result));sys.exit(0)
with tempfile.TemporaryDirectory(prefix='concurrency-',dir=str(Path(__file__).resolve().parent)) as td:
 base=Path(td)
 for second in ['writer','repair_second']:
  root=base/second/'archive';root.parent.mkdir();one=gs.publish_batch(*args(root),f.wb_files('10'));two=gs.publish_batch(*args(root),f.wb_files('20'),expected_generation=one['generation']);scope=gs._scope(*args(root));old=b'{original corrupt bytes}';(scope/'CURRENT.json').write_bytes(old)
  params=dict(generation=two['generation'],expected_digest=two['manifest_sha256'],expected_current_sha256=ar._sha(old),witness_reference='synthetic-concurrency-witness',acknowledged=True)
  source=root.parent/'input.csv';source.write_text('\ufeffreportId;rrdId;reportType;amount\n12;12;1;30\n',encoding='utf-8');request=root.parent/'request.json';request.write_text(json.dumps(dict(root=str(root),params=params,source=str(source))))
  def start(mode):return subprocess.Popen([sys.executable,'-B',str(Path(__file__).resolve()),'--checkout',str(a.checkout),'--child',mode,'--request',str(request)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
  first=start('repair_first');assert first.stdout.readline().strip()=='PREPARED';other=start(second);assert other.stdout.readline().strip()=='ATTEMPT';assert not select.select([other.stdout],[],[],0.2)[0]
  first.stdin.write('go\n');first.stdin.flush();out,err=first.communicate(timeout=30);assert first.returncode==0,(out,err)
  assert other.stdout.readline().strip()=='HELD';other.stdin.write('go\n');other.stdin.flush();out,err=other.communicate(timeout=30);assert other.returncode==0,(out,err)
  active=gs.read_active(*args(root));record=json.loads(next((scope/'restore-journal').glob('*.json')).read_text());assert base64.b64decode(record['previous_b64'])==old
  if second=='writer':
   assert active['generation']!=two['generation'];before=(scope/'CURRENT.json').read_bytes();blocked=False
   try:cr.repair_current_with_witness(*args(root),**params)
   except gs.GenerationError:blocked=True
   assert blocked and (scope/'CURRENT.json').read_bytes()==before
  else:assert active['generation']==two['generation'] and json.loads(out)['changed_in_attempt'] is False
  print(json.dumps({'check':'REPAIR_CONCURRENCY','other':second,'blocked_until_repair_release':True,'preimage_preserved':True,'status':'PASS'}),flush=True)
 print(json.dumps({'check':'COMPLETE','cases':2}),flush=True)
