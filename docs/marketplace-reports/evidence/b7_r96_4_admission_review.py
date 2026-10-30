"""Independent FD/no-follow admission tests. Synthetic files; network denied."""
import argparse,json,os,sys,tempfile
from pathlib import Path
from unittest.mock import patch

def audit(event,args):
 if event in ('socket.connect','socket.getaddrinfo'):raise AssertionError('Network prohibited')
sys.addaudithook(audit)
p=argparse.ArgumentParser();p.add_argument('--checkout',type=Path,required=True);a=p.parse_args();sys.path.insert(0,str(a.checkout.resolve()))
from apps.msp_marketplace_reports import archive as ar,versioned_archive as va
assert Path(ar.__file__).resolve().is_relative_to(a.checkout.resolve())
def emit(check,**kw):print(json.dumps(dict(check=check,**kw),sort_keys=True),flush=True)
lockname='wb_laser_master__wb_weekly_finance_main.lock'
with tempfile.TemporaryDirectory(prefix='admission-',dir=str(Path(__file__).resolve().parent)) as td:
 base=Path(td);n=0
 def case():
  global n
  n+=1;b=base/str(n);b.mkdir();source=b/'source.csv';source.write_text('\ufeffreportId;rrdId;reportType;amount\n1;1;1;10\n',encoding='utf-8');outside=b/'outside';outside.mkdir();return b,b/'archive',outside,source
 def call(fn,root,source):return fn(root,'wb_weekly_finance_main','wb_laser_master','2026',source)
 modes=['root_link','root_dangling','ancestor_link','nested_ancestor_link','locks_link','locks_dangling','file_link','file_dangling','hardlink','fifo','lock_is_dir','locks_is_file','root_is_file','missing_parent','traversal','filesystem_root']
 total=0
 for label,fn in [('legacy',ar.import_csv),('versioned',va.import_csv_versioned)]:
  passed=[]
  for mode in modes:
   b,root,outside,source=case();target=outside/'target.lock';target.write_bytes(b'UNCHANGED')
   if mode=='root_link':root.symlink_to(outside,target_is_directory=True)
   elif mode=='root_dangling':root.symlink_to(outside/'missing',target_is_directory=True)
   elif mode=='ancestor_link':(b/'alias').symlink_to(outside,target_is_directory=True);root=b/'alias'/'archive'
   elif mode=='nested_ancestor_link':(b/'nested').mkdir();(b/'nested/alias').symlink_to(outside,target_is_directory=True);root=b/'nested/alias/archive'
   elif mode=='root_is_file':root.write_bytes(b'file')
   elif mode=='missing_parent':root=b/'missing/archive'
   elif mode=='traversal':root=b/'missing/../archive'
   elif mode=='filesystem_root':root=Path('/')
   else:
    root.mkdir()
    if mode in ('locks_link','locks_dangling'):(root/'.locks').symlink_to(outside if mode=='locks_link' else outside/'missing',target_is_directory=True)
    elif mode=='locks_is_file':(root/'.locks').write_bytes(b'notdir')
    else:
     (root/'.locks').mkdir();lock=root/'.locks'/lockname
     if mode=='file_link':lock.symlink_to(target)
     elif mode=='file_dangling':lock.symlink_to(outside/'missing.lock')
     elif mode=='hardlink':os.link(target,lock)
     elif mode=='fifo':os.mkfifo(lock)
     elif mode=='lock_is_dir':lock.mkdir()
   before={str(p.relative_to(outside)):p.read_bytes() for p in outside.rglob('*') if p.is_file()};rejected=False;fd_before=len(os.listdir('/proc/self/fd'))
   try:call(fn,root,source)
   except (ValueError,OSError):rejected=True
   assert rejected,(label,mode)
   assert before=={str(p.relative_to(outside)):p.read_bytes() for p in outside.rglob('*') if p.is_file()},(label,mode)
   assert len(os.listdir('/proc/self/fd'))==fd_before,(label,mode,'fd leak')
   if mode=='missing_parent':assert not (b/'missing').exists()
   passed.append(mode);total+=1
  emit('STATIC_PATH_NEGATIVES',importer=label,passed=len(passed),modes=passed)
 # Existing regular lock inode re-used by each public importer.
 reuse=0
 for label,fn in [('legacy',ar.import_csv),('versioned',va.import_csv_versioned)]:
  b,root,outside,source=case();(root/'.locks').mkdir(parents=True);lock=root/'.locks'/lockname;lock.write_bytes(b'LOCK_SENTINEL');ino=lock.stat().st_ino
  first=call(fn,root,source);second=call(fn,root,source);assert not second['changed'] and lock.read_bytes()==b'LOCK_SENTINEL' and lock.stat().st_ino==ino
  emit('REGULAR_LOCK_REUSE',importer=label,status='PASS');reuse+=1
 # Inject EACCES into each admission os.open call: no financial publication,
 # no FD leak. Train helper only, then invoke both real importers.
 b,root,outside,source=case();(root/'.locks').mkdir(parents=True);real=os.open;trace=[]
 def record(*aa,**kk):trace.append((aa,kk));return real(*aa,**kk)
 with patch.object(os,'open',record):
  with ar._lock(root,'wb_laser_master','wb_weekly_finance_main'):pass
 errors=0
 for label,fn in [('legacy',ar.import_csv),('versioned',va.import_csv_versioned)]:
  for nth in range(len(trace)):
   b,root,outside,source=case();(root/'.locks').mkdir(parents=True);seen=[0];fd_before=len(os.listdir('/proc/self/fd'))
   def fail(*aa,**kk):
    i=seen[0];seen[0]+=1
    if i==nth:raise PermissionError(13,'synthetic admission open failure')
    return real(*aa,**kk)
   caught=False
   try:
    with patch.object(os,'open',fail):call(fn,root,source)
   except (OSError,ValueError):caught=True
   assert caught and not (root/'.b7-generations').exists() and not (root/'База данных').exists()
   assert len(os.listdir('/proc/self/fd'))==fd_before and not list(outside.iterdir());errors+=1
 emit('OPEN_FAILURES',open_points=len(trace),importers=2,passed=errors)
 # Directory creation failures: root or .locks, both public entrypoints.
 mkdir_cases=0
 for label,fn in [('legacy',ar.import_csv),('versioned',va.import_csv_versioned)]:
  for which in ['archive','.locks']:
   b,root,outside,source=case()
   if which=='.locks':root.mkdir()
   real_mkdir=os.mkdir;fd_before=len(os.listdir('/proc/self/fd'))
   def deny(path,*aa,**kk):
    if str(path)==which:raise PermissionError(13,'synthetic mkdir failure')
    return real_mkdir(path,*aa,**kk)
   caught=False
   try:
    with patch.object(os,'mkdir',deny):call(fn,root,source)
   except (OSError,ValueError):caught=True
   assert caught and not (root/'База данных').exists() and not (root/'.b7-generations').exists() and len(os.listdir('/proc/self/fd'))==fd_before;mkdir_cases+=1
 emit('MKDIR_FAILURES',passed=mkdir_cases)
 # Concurrent replacement immediately before no-follow directory/file open.
 race_cases=0
 for label,fn in [('legacy',ar.import_csv),('versioned',va.import_csv_versioned)]:
  for which in ['ancestor','root','.locks','lockfile']:
   b,root,outside,source=case();parent=b/'nested';parent.mkdir();root=parent/'archive';(root/'.locks').mkdir(parents=True);seen=[False];real_open=os.open
   def racing(name,flags,*aa,**kk):
    trigger={'ancestor':'nested','root':'archive','.locks':'.locks','lockfile':lockname}[which]
    if str(name)==trigger and not seen[0]:
     seen[0]=True;victim=parent if which=='ancestor' else root if which=='root' else root/'.locks' if which=='.locks' else root/'.locks'/lockname
     if victim.exists():victim.rename(victim.with_name(victim.name+'.saved'))
     victim.symlink_to(outside/'target.lock' if which=='lockfile' else outside,target_is_directory=which!='lockfile')
    return real_open(name,flags,*aa,**kk)
   caught=False
   try:
    with patch.object(os,'open',racing):call(fn,root,source)
   except (OSError,ValueError):caught=True
   assert seen[0] and caught and not list(outside.iterdir()),(label,which)
   race_cases+=1
 emit('SWAP_BEFORE_OPEN',passed=race_cases)
 # Swap textual .locks after its FD was opened: creation remains in pinned
 # original directory (renamed inside root), never in symlink destination.
 b,root,outside,source=case();(root/'.locks').mkdir(parents=True);real_open=os.open;changed=[False]
 def swap_after_dirfd(name,flags,*aa,**kk):
  if str(name)==lockname and not changed[0]:
   changed[0]=True;(root/'.locks').rename(root/'.locks.saved');(root/'.locks').symlink_to(outside,target_is_directory=True)
  return real_open(name,flags,*aa,**kk)
 with patch.object(os,'open',swap_after_dirfd):
  with ar._lock(root,'wb_laser_master','wb_weekly_finance_main'):pass
 assert changed[0] and (root/'.locks.saved'/lockname).is_file() and not list(outside.iterdir())
 emit('PINNED_LOCK_DIRECTORY',status='PASS',outside_files=0)
 emit('COMPLETE',static_cases=total,reuse_cases=reuse,open_failure_cases=errors,mkdir_cases=mkdir_cases,swap_cases=race_cases,pinned_dir_cases=1)
