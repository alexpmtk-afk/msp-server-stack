"""Offline B5 review. All fixture files are synthetic and all sockets denied."""
import argparse,csv,hashlib,importlib.util,json,socket,tempfile
from pathlib import Path
from unittest.mock import patch

def load(path,name):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def emit(check,**result):print(json.dumps({'check':check,**result},sort_keys=True))
def snapshot(root):return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file() and '.locks' not in p.parts}
def fixture(root,dataset,period='2026',amount='10',ident='11'):
 if dataset.startswith('wb_'):
  fields=['reportId','rrdId','amount'];rows=[{'reportId':ident,'rrdId':'1','amount':amount}];cab='wb_laser_master'
 elif dataset=='ozon_final_realization':
  fields=['report_year','report_month','row_number','amount'];rows=[dict(report_year='2026',report_month=period,row_number='1',amount=amount)];cab='ozon_laser_master'
 else:
  key='accrual_id' if dataset.endswith('accruals') else 'posting_number';fields=[key,'amount'];rows=[{key:ident,'amount':amount}];cab='ozon_laser_master'
 src=root/'input.csv'
 with src.open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.DictWriter(f,fields,delimiter=';');w.writeheader();w.writerows(rows)
 return src,cab

def run_import(m,root,dataset,period,**kw):
 src,cab=fixture(root,dataset,period,**kw);return m.import_csv(root/'archive',dataset,cab,period,src)
def denied(*a,**kw):raise AssertionError('Network prohibited')
def run(old,new):
 with tempfile.TemporaryDirectory(prefix='b5-independent-',dir=str(Path(__file__).parent)) as td:
  base=Path(td);counter=0
  def work():
   nonlocal counter
   counter+=1;p=base/str(counter);p.mkdir();return p
  for label,m in [('old',old),('new',new)]:
   root=work();res=run_import(m,root,'wb_weekly_finance_main','2026');f=Path(res['path']);f.write_bytes(f.read_bytes().replace(b';10',b';99'));before=snapshot(root/'archive');blocked=False
   try:run_import(m,root,'wb_weekly_finance_main','2026',ident='12',amount='30')
   except ValueError:blocked=True
   emit('ORIGINAL_B5',version=label,blocked=blocked,unchanged=snapshot(root/'archive')==before,verify_ok=m.verify(root/'archive')['ok'])
  cases=[]
  mutations={'data':None,'schema':2,'dataset':'unknown','cabinet':'wrong','period':'2025','status':'BAD','bytes':-1,'rows':-1,'sha256':'bad','invalid_json':None,'null_manifest':None,'list_manifest':None,'csv_only':None,'manifest_only':None}
  mutations.update({'missing_'+k:None for k in ['schema','dataset','cabinet','period','status','bytes','rows','sha256']})
  for dataset in ['wb_weekly_finance_main','wb_weekly_finance_buyout','ozon_current_orders_fbo','ozon_current_orders_fbs','ozon_current_accruals','ozon_final_realization']:
   period='2026' if dataset.startswith('wb_') else '2026-01'
   for field,value in mutations.items():
    root=work();res=run_import(new,root,dataset,period);f=Path(res['path']);meta=f.with_name(f.name+'.meta.json')
    if field=='data':f.write_bytes(f.read_bytes().replace(b';10',b';99'))
    elif field=='invalid_json':meta.write_text('{')
    elif field=='null_manifest':meta.write_text('null')
    elif field=='list_manifest':meta.write_text('[]')
    elif field=='csv_only':meta.unlink()
    elif field=='manifest_only':f.unlink()
    else:
     j=json.loads(meta.read_text());j.pop(field[8:],None) if field.startswith('missing_') else j.update({field:value});meta.write_text(json.dumps(j))
    before=snapshot(root/'archive');blocked=False
    try:run_import(new,root,dataset,period,ident='12',amount='30')
    except ValueError:blocked=True
    cases.append((dataset,field,blocked and snapshot(root/'archive')==before))
  emit('TARGET_CORRUPTION_MATRIX',cases=len(cases),passed=sum(x[2] for x in cases),failures=[x for x in cases if not x[2]])
  results=[]
  for dataset in ['wb_weekly_finance_main','wb_weekly_finance_buyout','ozon_current_orders_fbo','ozon_current_orders_fbs','ozon_current_accruals','ozon_final_realization']:
   root=work();period='2026' if dataset.startswith('wb_') else '2026-01';res=run_import(new,root,dataset,period);f=Path(res['path']);f.write_bytes(f.read_bytes().replace(b';10',b';99'));before=snapshot(root/'archive');blocked=False
   try:run_import(new,root,dataset,period,amount='99')
   except ValueError:blocked=True
   results.append(blocked and snapshot(root/'archive')==before)
  emit('CORRUPT_NOOP',cases=len(results),passed=sum(results))
  for field,value in [('schema',2),('dataset','wrong'),('cabinet','wrong'),('period','2025-12'),('bytes',0)]:
   root=work();res=run_import(new,root,'ozon_final_realization','2026-01');f=Path(res['path']);meta=f.with_name(f.name+'.meta.json');j=json.loads(meta.read_text());j[field]=value;meta.write_text(json.dumps(j));annual=Path(res['annual_path']);before=annual.read_bytes();blocked=False
   try:run_import(new,root,'ozon_final_realization','2026-02')
   except ValueError:blocked=True
   emit('OZON_OTHER_MONTH_MANIFEST',field=field,blocked=blocked,annual_changed=annual.read_bytes()!=before,verify_ok=new.verify(root/'archive')['ok'])
  root=work();res=run_import(new,root,'ozon_final_realization','2026-01');annual=Path(res['annual_path']);annual.write_bytes(annual.read_bytes().replace(b';10',b';99'));month=Path(res['path']);before=month.read_bytes();blocked=False
  try:run_import(new,root,'ozon_final_realization','2026-01',amount='20')
  except ValueError:blocked=True
  emit('CORRUPT_ANNUAL_SIDE_EFFECT',blocked=blocked,month_changed=month.read_bytes()!=before)
  for label,m in [('old',old),('new',new)]:
   root=work();original=m._safe_write
   def fail_manifest(path,data):
    if path.name.endswith('.meta.json'):raise OSError('synthetic manifest failure')
    return original(path,data)
   with patch.object(m,'_safe_write',fail_manifest):
    try:run_import(m,root,'wb_weekly_finance_main','2026')
    except OSError:pass
   blocked=False
   try:run_import(m,root,'wb_weekly_finance_main','2026')
   except ValueError:blocked=True
   emit('B7_CRASH_RETRY',version=label,retry_blocked=blocked,verify_ok=m.verify(root/'archive')['ok'])
  for label,m in [('old',old),('new',new)]:
   root=work();res=run_import(m,root,'ozon_final_realization','2026-01');before=snapshot(root/'archive');original=m._safe_write
   def fail_annual_manifest(path,data):
    if path.parent.name=='annual' and path.name.endswith('.meta.json'):raise OSError('synthetic annual manifest failure')
    return original(path,data)
   with patch.object(m,'_safe_write',fail_annual_manifest):
    try:run_import(m,root,'ozon_final_realization','2026-01',amount='20')
    except OSError:pass
   blocked=False
   try:run_import(m,root,'ozon_final_realization','2026-01',amount='20')
   except ValueError:blocked=True
   emit('B7_OZON_ANNUAL_CRASH_RETRY',version=label,retry_blocked=blocked,verify_ok=m.verify(root/'archive')['ok'])
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--old',type=Path,required=True);ap.add_argument('--new',type=Path,required=True);args=ap.parse_args()
 with patch.object(socket.socket,'connect',denied),patch.object(socket.socket,'connect_ex',denied):run(load(args.old,'old_archive'),load(args.new,'new_archive'))
