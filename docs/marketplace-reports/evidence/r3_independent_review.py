"""Independent synthetic R3 review. No network, real reports or production writes."""
import argparse,csv,importlib.util,json,socket,sys,tempfile
from pathlib import Path

def load(path,name):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def emit(check,**kw):print(json.dumps(dict(check=check,**kw),sort_keys=True))
def snap(root):return {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
def fixture(base,dataset,period,amount='10',ident='11'):
 if dataset.startswith('wb_'):fields=['reportId','rrdId','amount'];row=[ident,'1',amount];cab='wb_laser_master'
 elif dataset=='ozon_final_realization':fields=['report_year','report_month','row_number','amount'];row=['2026',period,'1',amount];cab='ozon_laser_master'
 else:fields=['accrual_id' if dataset.endswith('accruals') else 'posting_number','amount'];row=[ident,amount];cab='ozon_laser_master'
 src=base/'source.csv'
 with src.open('w',encoding='utf-8-sig',newline='') as f:w=csv.writer(f,delimiter=';');w.writerow(fields);w.writerow(row)
 return cab,src
def imp(m,base,dataset='ozon_final_realization',period='2026-01',**kw):
 cab,src=fixture(base,dataset,period,**kw);return m.import_csv(base/'archive',dataset,cab,period,src)
def setup(m,base,kind):
 dataset=kind if kind in m.DATASETS else 'ozon_final_realization';period='2026' if dataset.startswith('wb') else '2026-01'
 r=imp(m,base,dataset,period);p=Path(r['annual_path'] if kind=='annual' else r['path']);return dataset,period,p,p.with_name(p.name+'.meta.json')
def operate(m,base,kind,op,dataset,period,path):
 if op=='publish':
  raw=path.read_bytes();meta=json.loads(path.with_name(path.name+'.meta.json').read_text());return m._publish(base/'archive',path,raw,1,dataset,'wb_laser_master' if dataset.startswith('wb') else 'ozon_laser_master','2026' if kind=='annual' else period)
 if op=='rebuild':return m._rebuild_ozon_annual(base/'archive','ozon_laser_master','2026')
 if kind in ('dependency','annual'):return imp(m,base,period='2026-02' if op=='new_month' else '2026-01',amount='20')
 return imp(m,base,dataset,period,ident='12' if op=='changed' and dataset.startswith('wb') else '11',amount='20' if op=='changed' else '10')
def run(before,after,work):
 counter=0
 def fresh():
  nonlocal counter
  counter+=1;p=work/str(counter);p.mkdir();return p
 for version,m in [('before',before),('after',after)]:
  for field,value in [('schema',True),('rows',True),('bytes','equivalent_float')]:
   base=fresh();_,_,p,meta=setup(m,base,'dependency');d=json.loads(meta.read_text());d[field]=float(d[field]) if value=='equivalent_float' else value;meta.write_text(json.dumps(d));old=snap(base/'archive');verify_ok=m.verify(base/'archive')['ok'];blocked=False
   try:imp(m,base,period='2026-02')
   except ValueError:blocked=True
   emit('ORIGINAL_R3',version=version,field=field,blocked=blocked,verify_ok=verify_ok,unchanged=snap(base/'archive')==old)
   assert blocked==(version=='after') and verify_ok==(version=='before')
 routes=[]
 for k in after.DATASETS:
  for op in ['noop','changed','publish']:routes.append((k,op))
 routes += [('dependency','new_month'),('dependency','replace'),('dependency','rebuild'),('annual','new_month'),('annual','replace'),('annual','publish')]
 invalid=['true','false','equal_float','fraction','exponent','string','null','list','object','missing','negative','huge','nan','infinity']
 passed=0;failures=[]
 for kind,op in routes:
  for field in ['schema','rows','bytes']:
   for mode in invalid:
    base=fresh();ds,period,p,meta=setup(after,base,kind);d=json.loads(meta.read_text());v=d[field]
    values={'true':True,'false':False,'equal_float':float(v),'fraction':v+0.5,'string':str(v),'null':None,'list':[],'object':{},'negative':-1,'huge':10**50,'nan':float('nan'),'infinity':float('inf')}
    if mode=='missing':del d[field]
    else:d[field]=values.get(mode,v)
    raw=json.dumps(d)
    if mode=='exponent':raw=raw.replace('"'+field+'": '+str(v),'"'+field+'": '+str(v)+'e0')
    meta.write_text(raw);old=snap(base/'archive');audit=after.verify(base/'archive');verify_unchanged=snap(base/'archive')==old;blocked=False;exc=''
    try:operate(after,base,kind,op,ds,period,p)
    except ValueError:blocked=True
    except Exception as e:exc=type(e).__name__
    ok=blocked and not audit['ok'] and verify_unchanged and snap(base/'archive')==old
    if ok:passed+=1
    else:failures.append([kind,op,field,mode,blocked,audit['ok'],exc])
 emit('STRICT_FIELDS_MATRIX',routes=len(routes),cases=passed+len(failures),passed=passed,failures=failures)
 assert not failures
 passed=0;failures=[]
 malformed=['{','null','[]','true','1','"text"','{}','{"schema":1,}','{"schema":01}']
 for kind in [*after.DATASETS,'dependency','annual']:
  for raw in malformed:
   base=fresh();ds,period,p,meta=setup(after,base,kind);meta.write_text(raw);old=snap(base/'archive');a=after.verify(base/'archive');blocked=False
   try:operate(after,base,kind,'new_month' if kind in ('dependency','annual') else 'noop',ds,period,p)
   except ValueError:blocked=True
   ok=blocked and not a['ok'] and snap(base/'archive')==old
   if ok:passed+=1
   else:failures.append([kind,raw])
 emit('MALFORMED_JSON_MATRIX',cases=passed+len(failures),passed=passed,failures=failures);assert not failures
 controls=[]
 for ds in after.DATASETS:
  base=fresh();_,period,p,meta=setup(after,base,ds);old=snap(base/'archive');r=imp(after,base,ds,period);assert not r['changed'] and snap(base/'archive')==old
  imp(after,base,ds,period,ident='12' if ds.startswith('wb') else '11',amount='20');assert after.verify(base/'archive')['ok'];controls.append(ds)
 emit('VALID_CONTROLS',passed=controls)
 # Parser ambiguity and resource exhaustion are tested separately from R3.
 for label,m in [('before',before),('after',after)]:
  for kind in ['duplicate_schema','deep_json']:
   base=fresh();_,_,p,meta=setup(m,base,'ozon_current_orders_fbo');s=meta.read_text()
   meta.write_text(s.replace('"schema": 1','"schema": true, "schema": 1') if kind=='duplicate_schema' else '['*1100+'0'+']'*1100)
   old=snap(base/'archive');ve=None;ie=None;ok=None
   try:ok=m.verify(base/'archive')['ok']
   except Exception as e:ve=type(e).__name__
   try:imp(m,base,'ozon_current_orders_fbo','2026-01')
   except Exception as e:ie=type(e).__name__
   emit('PARSER_BOUNDARY',version=label,case=kind,verify_ok=ok,verify_exception=ve,import_exception=ie,unchanged=snap(base/'archive')==old)
 emit('COMPLETE',fixture_directories=counter)
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--before',type=Path,required=True);ap.add_argument('--after',type=Path,required=True);a=ap.parse_args()
 def audit(event,args):
  if event in ('socket.connect','socket.getaddrinfo'):raise AssertionError('Network prohibited')
 sys.addaudithook(audit)
 with tempfile.TemporaryDirectory(prefix='r3-fixtures-',dir=str(Path(__file__).resolve().parent)) as td:run(load(a.before,'archive_before'),load(a.after,'archive_after'),Path(td))
