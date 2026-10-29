"""Additional independent repair recheck; synthetic archive and blocked network."""
import argparse,base64,importlib.util,json,os,sys,tempfile
from pathlib import Path
from unittest.mock import patch

def audit(event,args):
 if event in ('socket.connect','socket.getaddrinfo'):raise AssertionError('Network denied')
sys.addaudithook(audit)
p=argparse.ArgumentParser();p.add_argument('--checkout',type=Path,required=True);a=p.parse_args();sys.path.insert(0,str(a.checkout.resolve()))
from apps.msp_marketplace_reports import archive as ar,generation_store as gs,current_repair as cr
assert Path(cr.__file__).resolve().is_relative_to(a.checkout.resolve())
spec=importlib.util.spec_from_file_location('fixtures',a.checkout/'tests/test_msp_marketplace_generations.py');f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)
def snap(path):return {str(x.relative_to(path)):x.read_bytes() for x in path.rglob('*') if x.is_file()}
def emit(**kw):print(json.dumps(kw,sort_keys=True),flush=True)
with tempfile.TemporaryDirectory(prefix='extra-',dir=Path(__file__).parent) as td:
 base=Path(td);count=0
 def setup(kind='wb',missing=False,phase='VERIFIED'):
  global count
  count+=1;root=base/str(count)/'archive';root.parent.mkdir();args=(root,'wb_weekly_finance_main','wb_laser_master','2026') if kind=='wb' else (root,'ozon_final_realization','ozon_laser_master','2026')
  batch=lambda v:f.wb_files(v) if kind=='wb' else f.ozon_final_files(january=v,february='7')
  one=gs.publish_batch(*args,batch('10'));two=gs.publish_batch(*args,batch('20'),expected_generation=one['generation']);scope=gs._scope(*args);pointer=scope/'CURRENT.json';old=None if missing else b'\x00\xffdamaged CURRENT\n'
  if missing:pointer.unlink()
  else:pointer.write_bytes(old)
  params=dict(generation=two['generation'],expected_digest=two['manifest_sha256'],expected_current_sha256=ar._sha(old) if old is not None else None,witness_reference='synthetic-recheck',acknowledged=True)
  if phase=='PREPARED':
   try:cr.repair_current_with_witness(*args,**params,fault=lambda x:(_ for _ in ()).throw(OSError('prepare stop')) if x=='after_prepare' else None)
   except cr.RestoreUncertainError:pass
  else:assert cr.repair_current_with_witness(*args,**params)['status']=='CURRENT_VERIFIED'
  journal=next((scope/'restore-journal').glob('*.json'));return args,params,scope,journal,old
 total=0
 # Every repeated file/directory/ancestor sync failure must stay uncertain,
 # preserve VERIFIED journal bytes and original preimage, and allow later retry.
 for kind in ['wb','ozon']:
  for missing in [False,True]:
   for mode in ['file','journal_dir_early','journal_dir_final','scope','open_file','wrong_file_type','symlink_swap']:
    args,params,scope,journal,old=setup(kind,missing);before=snap(scope);raw=journal.read_bytes();original_resync=cr._resync_verified_journal;real_fsync=os.fsync;real_open=os.open;active=[False];fired=[0];dirhits=[0]
    def fail_fsync(fd):
     name=os.readlink('/proc/self/fd/'+str(fd))
     if active[0] and name==str(journal.parent):dirhits[0]+=1
     target=mode=='file' and name==str(journal) or mode=='journal_dir_early' and name==str(journal.parent) or mode=='scope' and name==str(scope) or mode=='journal_dir_final' and name==str(journal.parent) and dirhits[0]==2
     if active[0] and target:fired[0]+=1;raise OSError(5,'repeated fsync EIO')
     return real_fsync(fd)
    def fail_open(path,flags,*aa,**kk):
     if active[0] and str(path)==str(journal):
      assert flags & os.O_NOFOLLOW
      if mode=='open_file':fired[0]+=1;raise OSError(13,'open denied')
      if mode=='wrong_file_type':fired[0]+=1;return real_open(journal.parent,os.O_RDONLY)
     return real_open(path,flags,*aa,**kk)
    def resync(*aa):
     active[0]=True
     try:return original_resync(*aa)
     finally:active[0]=False
    if mode=='symlink_swap':
     outside=scope.parent/'outside';outside.write_bytes(b'OUTSIDE SENTINEL');backup=journal.with_suffix('.hold');original_ensure=cr._ensure_scope_durable
     def ensure(path):
      original_ensure(path)
      if active[0]:journal.rename(backup);journal.symlink_to(outside);fired[0]+=1
     with patch.object(cr,'_resync_verified_journal',resync),patch.object(cr,'_ensure_scope_durable',ensure):
      try:cr.repair_current_with_witness(*args,**params)
      except cr.RestoreUncertainError:pass
      else:raise AssertionError('followed replaced symlink')
     assert outside.read_bytes()==b'OUTSIDE SENTINEL';journal.unlink();backup.rename(journal)
    else:
     for attempt in range(2):
      dirhits[0]=0
      with patch.object(cr,'_resync_verified_journal',resync),patch.object(os,'fsync',fail_fsync),patch.object(os,'open',fail_open):
       try:cr.repair_current_with_witness(*args,**params)
       except cr.RestoreUncertainError:pass
       else:raise AssertionError((kind,missing,mode,'false success'))
      assert snap(scope)==before
     assert fired[0]==2,(mode,fired)
    trace=[]
    def trace_sync(fd):trace.append(os.readlink('/proc/self/fd/'+str(fd)));return real_fsync(fd)
    with patch.object(os,'fsync',trace_sync):result=cr.repair_current_with_witness(*args,**params)
    assert result['status']=='CURRENT_VERIFIED' and str(journal) in trace and str(journal.parent) in trace
    assert snap(scope)==before and journal.read_bytes()==raw
    record=json.loads(raw);assert (None if record['previous_b64'] is None else base64.b64decode(record['previous_b64']))==old
    total+=1;emit(check='RETRY_FAILURE',kind=kind,missing=missing,mode=mode,status='PASS')
 # Other transaction journals must get the same strict schema checks before mutation.
 for phase in ['PREPARED','VERIFIED']:
  for value in [True,1.0,False,'1',None,[],{},2,0,-1]:
   args,params,scope,journal,old=setup(phase=phase);other=journal.parent/('f'*32+'.json');other.write_text(json.dumps({'schema':value,'state':'VERIFIED'}));before=snap(scope)
   try:cr.repair_current_with_witness(*args,**params)
   except gs.GenerationError as ex:assert 'schema' in str(ex)
   else:raise AssertionError(('foreign schema accepted',phase,value))
   assert snap(scope)==before;total+=1;emit(check='FOREIGN_SCHEMA',phase=phase,value=value,status='PASS')
 emit(check='COMPLETE',cases=total)
