import argparse,sys,tempfile,csv,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--checkout',type=Path,required=True);a=p.parse_args();sys.path.insert(0,str(a.checkout.resolve()))
def audit(event,args):
 if event in ('socket.connect','socket.getaddrinfo'):raise AssertionError('Network denied')
sys.addaudithook(audit)
from apps.msp_marketplace_reports.versioned_archive import import_csv_versioned
with tempfile.TemporaryDirectory(dir=str(Path(__file__).resolve().parent)) as td:
 base=Path(td)
 for mode in ['root_symlink','lock_dir_symlink','lock_file_symlink']:
  case=base/mode;case.mkdir();outside=case/'outside';outside.mkdir();root=case/'archive';source=case/'source.csv';source.write_text('\ufeffreportId;rrdId;reportType;amount\n1;1;1;10\n',encoding='utf-8');lockname='wb_laser_master__wb_weekly_finance_main.lock'
  if mode=='root_symlink':root.symlink_to(outside,target_is_directory=True)
  elif mode=='lock_dir_symlink':root.mkdir();(root/'.locks').symlink_to(outside,target_is_directory=True)
  else:
   (root/'.locks').mkdir(parents=True);(root/'.locks'/lockname).symlink_to(outside/'injected.lock')
  result=None;error=None
  try:result=import_csv_versioned(root,'wb_weekly_finance_main','wb_laser_master','2026',source)
  except Exception as e:error=type(e).__name__+':'+str(e)
  print(json.dumps({'case':mode,'status':result['status'] if result else None,'error':error,'outside_files':[str(x.relative_to(outside)) for x in outside.rglob('*') if x.is_file()]}),flush=True)
