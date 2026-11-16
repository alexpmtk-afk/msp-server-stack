import os,contextlib,fcntl,hashlib,io,json,os,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent))
sys.path.insert(0,os.environ.get('IMPORT_TEST_PAYLOAD',str(Path(__file__).parent)))
import publish as p,import_root as u
from test_import import rows,catalog
class Transactions(unittest.TestCase):
 def fixture(self,t):
  top=Path(t);stage=top/'stage';stage.mkdir();base=top/'state';base.mkdir();(base/'cycles').mkdir();(base/'controller.lock').touch();finance=top/'finance.lock';finance.touch()
  a=catalog();archive=top/'archive';folder=a.root(p.CAB,archive);(folder/'generations').mkdir(parents=True);(folder/'documents').mkdir();a.store_index(dict(schema=1,cabinet=p.CAB,baseline_seeded=True,reports={}),archive);a.publish(a.load_index(p.CAB,archive),archive)
  baseline=json.loads((Path(__file__).parent/'baseline.json').read_text());capture=top/'capture.json';capture.write_bytes(a.doc(dict(status=200,request_cursor=0,rows=rows())));terminal=top/'page-01.json';terminal.write_bytes(a.doc(dict(status=204,rows=None,request_cursor=92)));baseline.update(capture=str(capture),capture_sha256=u.sha(capture.read_bytes()));(stage/'baseline.json').write_bytes(a.doc(baseline));(stage/'MANIFEST.json').write_text('{}')
  job=dict(key='cab|daily|date',cabinet=p.CAB,period='daily',**{'from':p.DAY,'to':p.DAY},attempts=3,max_attempts=3,status='WAITING_NEXT_RUN',next_due=123);cycle=dict(key='initial',cycle_id='fixture-cycle',status='WAITING_NEXT_RUN',jobs=[job]);cyclepath=base/'cycles/initial.json';cyclepath.write_bytes(a.doc(cycle));(base/'jobs.json').write_text('{}');(base/'installation.json').write_bytes(a.doc(dict(root_release=baseline['release'],report_availability_policy='WB_ANY_REPORT_V2_20261113')))
  public=base/'public.json';pubcycle=base/'cycle.public.json';public.write_bytes(a.doc(cycle));pubcycle.write_bytes(a.doc(cycle))
  def replace(path,value,*args):path.write_bytes(a.doc(value))
  def settle(j,result,now):j.update(status=result['status'],result=result)
  def verified_index(cab):
   for typ in (1,2):
    for _ in a.iter_view(a.snapshot(cab,typ,None,archive,allow_empty=True)):pass
   return a.load_index(cab,archive)
  def publish_cycle(cycle):replace(public,cycle);replace(pubcycle,cycle)
  def save(path,raw,*args):path.write_bytes(raw)
  c=types.SimpleNamespace(UNIT='fixture-unit',PUBLIC=public,catalog=types.SimpleNamespace(doc=a.doc,root=lambda cab: a.root(cab,archive)),r=types.SimpleNamespace(SERVICE='fixture-sender',save=save),replace=replace,public_path=lambda _:pubcycle,verified_index=verified_index,plan=types.SimpleNamespace(settle=settle,status=lambda cyc:'VERIFIED'),persist=lambda cyc:replace(cyclepath,cyc),publish_cycle=publish_cycle)
  original=u.load_module
  def load(name,path):return c if name=='accepted_controller_import' else p
  calls=[]
  def child(args,**kwargs):
   calls.append(args)
   # Both real flock descriptors must still be held during publication.
   for lock in (base/'controller.lock',finance):
    with lock.open('rb') as f:
     try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
     except BlockingIOError:pass
     else:raise AssertionError('missing import lock')
   return json.dumps(p.publish(rows(),a,archive,baseline['capture_sha256']))
  return stage,base,finance,cyclepath,calls,load,child,terminal
 def run_fixture(self,t,bad_terminal=False):
  stage,base,finance,path,calls,load,child,terminal=self.fixture(t)
  if bad_terminal:terminal.write_text('{}')
  with patch.object(u,'STAGE',stage),patch.object(u,'BASE',base),patch.object(u,'RECEIPT',base/'receipt.json'),patch.object(u,'FINANCE',finance),patch.object(u.os,'geteuid',return_value=0),patch.object(u,'trust'),patch.object(u,'load_module',side_effect=load),patch.object(u,'show',return_value=dict(ActiveState='inactive',DropInPaths='',PrivateNetwork='yes')),patch.object(u.subprocess,'check_output',side_effect=child),contextlib.redirect_stdout(io.StringIO()):
   if bad_terminal:
    with self.assertRaises(ValueError):u.main()
    self.assertFalse(calls);self.assertFalse((base/'receipt.json').exists());return
   u.main();first=json.loads(path.read_text());self.assertEqual(first['jobs'][0]['attempts'],3);self.assertEqual(first['jobs'][0]['status'],'VERIFIED');u.main();self.assertEqual(json.loads(path.read_text()),first);self.assertEqual(json.loads((base/'receipt.json').read_text())['status'],'IMPORTED_AND_VERIFIED');self.assertTrue((base/'nov9-import-backup').is_dir())
 def test_transaction_and_repeat_preserve_attempts_with_real_locks(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:self.run_fixture(t)
 def test_missing_terminal_causes_no_import_or_settlement(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as t:self.run_fixture(t,True)
if __name__=='__main__':unittest.main()
