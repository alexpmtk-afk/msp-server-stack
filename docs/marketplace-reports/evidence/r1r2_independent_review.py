"""Independent R1/R2 fixtures; no provider API, sockets denied, scratch only."""
import argparse,csv,json,socket,tempfile
from pathlib import Path
from unittest.mock import patch
import b5_independent_review as common

def snap(root):
 return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
def emit(check,**result):print(json.dumps({'check':check,**result},sort_keys=True))
def meta_for(file):return file.with_name(file.name+'.meta.json')
def rehash(module,file):
 meta=meta_for(file);d=json.loads(meta.read_text());raw=file.read_bytes();d['sha256']=module._sha(raw);d['bytes']=len(raw);d['rows']=len(module._rows(raw,('report_year','report_month','row_number'))[1]);meta.write_text(json.dumps(d))
def run(before,after):
 with tempfile.TemporaryDirectory(prefix='r1r2-review-',dir=str(Path(__file__).parent)) as td:
  base=Path(td);index=0
  def setup(m):
   nonlocal index
   index+=1;root=base/str(index);root.mkdir();result=common.run_import(m,root,'ozon_final_realization','2026-01');return root,Path(result['path']),Path(result['annual_path'])
  for label,m in [('before',before),('after',after)]:
   root,month,annual=setup(m);meta=meta_for(month);d=json.loads(meta.read_text());d['schema']=2;meta.write_text(json.dumps(d));old=snap(root/'archive');blocked=False
   try:common.run_import(m,root,'ozon_final_realization','2026-02')
   except ValueError:blocked=True
   emit('R1_EXACT',version=label,blocked=blocked,files_unchanged=snap(root/'archive')==old,verify_ok=m.verify(root/'archive')['ok'])
   root,month,annual=setup(m);annual.write_bytes(annual.read_bytes().replace(b';10',b';99'));old=snap(root/'archive');blocked=False
   try:common.run_import(m,root,'ozon_final_realization','2026-01',amount='20')
   except ValueError:blocked=True
   emit('R2_EXACT',version=label,blocked=blocked,files_unchanged=snap(root/'archive')==old)
  failures=[];passed=0
  mutations={k:val for k,val in [('schema',2),('status','BAD'),('dataset','wrong'),('cabinet','wrong'),('period','2025-12'),('sha256','x'),('rows',999),('bytes',999)]}
  mutations.update({'missing_'+k:None for k in ['schema','status','dataset','cabinet','period','sha256','rows','bytes']})
  mutations.update({k:None for k in ['data','bad_json','null','list','csv_only','meta_only']})
  for target in ['monthly','annual']:
   for mode in ['replace','new_month','noop']:
    for field,value in mutations.items():
     root,month,annual=setup(after);file=month if target=='monthly' else annual;meta=meta_for(file)
     if field=='data':file.write_bytes(file.read_bytes().replace(b';10',b';99'))
     elif field=='bad_json':meta.write_text('{')
     elif field=='null':meta.write_text('null')
     elif field=='list':meta.write_text('[]')
     elif field=='csv_only':meta.unlink()
     elif field=='meta_only':file.unlink()
     else:
      d=json.loads(meta.read_text())
      if field.startswith('missing_'):d.pop(field[8:])
      else:d[field]=value
      meta.write_text(json.dumps(d))
     old=snap(root/'archive');blocked=False
     try:common.run_import(after,root,'ozon_final_realization','2026-02' if mode=='new_month' else '2026-01',amount='10' if mode=='noop' else '20')
     except (ValueError,TypeError):blocked=True
     if blocked and snap(root/'archive')==old:passed+=1
     else:failures.append([target,mode,field,blocked])
  emit('GROUP_CORRUPTION_MATRIX',cases=passed+len(failures),passed=passed,failures=failures)
  conditions=[]
  for kind in ['missing_both_month','missing_both_annual','divergent_annual_valid_pair','divergent_month_valid_pair','row_period_wrong_valid_pair','bad_month_name']:
   root,month,annual=setup(after)
   if kind=='missing_both_month':month.unlink();meta_for(month).unlink()
   elif kind=='missing_both_annual':annual.unlink();meta_for(annual).unlink()
   elif kind=='divergent_annual_valid_pair':annual.write_bytes(annual.read_bytes().replace(b';10',b';99'));rehash(after,annual)
   elif kind=='divergent_month_valid_pair':month.write_bytes(month.read_bytes().replace(b';10',b';99'));rehash(after,month)
   elif kind=='row_period_wrong_valid_pair':month.write_bytes(month.read_bytes().replace(b'2026-01',b'2026-02'));rehash(after,month)
   else:month.rename(month.with_name(month.name.replace('2026-01','2026-13')));meta_for(month).rename(meta_for(month).with_name(meta_for(month).name.replace('2026-01','2026-13')))
   old=snap(root/'archive');blocked=False
   try:common.run_import(after,root,'ozon_final_realization','2026-02')
   except ValueError:blocked=True
   conditions.append({'kind':kind,'blocked':blocked,'files_unchanged':snap(root/'archive')==old})
  emit('GROUP_CONSISTENCY',results=conditions)
  root=base/'normal';root.mkdir();history=[]
  for period,extra in [('2026-01','first'),('2026-02','second'),('2026-03','first')]:
   src=root/'normal.csv';fields=['report_year','report_month','row_number','amount',extra]
   with src.open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fields,delimiter=';');w.writeheader();w.writerow(dict(report_year='2026',report_month=period,row_number='1',amount='10',**{extra:'value'}))
   history.append(after.import_csv(root/'archive','ozon_final_realization','ozon_laser_master',period,src))
  repeat_snapshot=snap(root/'archive');repeat=after.import_csv(root/'archive','ozon_final_realization','ozon_laser_master','2026-03',src);same=snap(root/'archive')==repeat_snapshot
  src.write_text(src.read_text(encoding='utf-8-sig').replace(';10;',';20;'),encoding='utf-8-sig');changed=after.import_csv(root/'archive','ozon_final_realization','ozon_laser_master','2026-03',src)
  emit('NORMAL_IMPORT',months=len(history),annual_rows=changed['annual_rows'],repeat_changed=repeat['changed'],repeat_all_files_unchanged=same,correction_changed=changed['changed'],verify_ok=after.verify(root/'archive')['ok'],backup_files=len(list((root/'archive'/'.backups').rglob('*.bak'))))
  for point in ['monthly_manifest','annual_before_publish','annual_manifest']:
   root,month,annual=setup(after);original_write=after._safe_write;original_publish=after._publish
   def fail_write(path,data):
    if path.name.endswith('.meta.json') and ((point=='monthly_manifest' and path.parent.name=='monthly_source') or (point=='annual_manifest' and path.parent.name=='annual')):raise OSError('synthetic crash')
    return original_write(path,data)
   def fail_publish(root,path,*args):
    if point=='annual_before_publish' and path.parent.name=='annual':raise OSError('synthetic crash')
    return original_publish(root,path,*args)
   with patch.object(after,'_safe_write',fail_write),patch.object(after,'_publish',fail_publish):
    try:common.run_import(after,root,'ozon_final_realization','2026-01',amount='20')
    except OSError:pass
   interrupted=snap(root/'archive');blocked=False
   try:common.run_import(after,root,'ozon_final_realization','2026-01',amount='20')
   except ValueError:blocked=True
   emit('B7_FAILPOINT',point=point,retry_blocked=blocked,retry_files_unchanged=snap(root/'archive')==interrupted,verify_ok=after.verify(root/'archive')['ok'])
  for module_label,module in [('before',before),('after',after)]:
   for field,value in [('schema',True),('rows',True),('bytes','float')]:
    root,month,annual=setup(module);meta=meta_for(month);d=json.loads(meta.read_text());d[field]=float(d[field]) if value=='float' else value;meta.write_text(json.dumps(d));blocked=False
    try:common.run_import(module,root,'ozon_final_realization','2026-02')
    except ValueError:blocked=True
    emit('STRICT_METADATA_TYPES',version=module_label,field=field,blocked=blocked,verify_ok=module.verify(root/'archive')['ok'])
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--before',type=Path,required=True);ap.add_argument('--after',type=Path,required=True);args=ap.parse_args()
 with patch.object(socket.socket,'connect',common.denied),patch.object(socket.socket,'connect_ex',common.denied):run(common.load(args.before,'before_r1r2'),common.load(args.after,'after_r1r2'))
