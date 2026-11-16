"""Read-only semantic lookup; no credentials, provider calls or archive writes."""
import argparse,json,re,sys,unicodedata,importlib.util
from decimal import Decimal,InvalidOperation
from pathlib import Path
BASE=Path(__file__).resolve().parent

def norm(value):
 return re.sub(r'[^\w%]+',' ',unicodedata.normalize('NFKC',value).casefold().replace('ё','е')).strip()
def strict_pairs(pairs):
 out={}
 for key,value in pairs:
  if key in out:raise ValueError('Duplicate JSON key: '+key)
  out[key]=value
 return out
def load():return json.loads((BASE/'ontology.json').read_text())
def reader():
 spec=importlib.util.spec_from_file_location('wb_local_reports',BASE/'local_reports.py')
 module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
def field(kb,query):
 q=norm(query);items=kb['fields'];exact=[f for f in items if any(q==norm(v) for v in [f['id'],*f['ui_labels'],*f['api_keys']])]
 if exact:return exact
 tokens=q.split()
 return [f for f in items if tokens and all(t in norm(json.dumps(f,ensure_ascii=False)) for t in tokens)]
def route(kb,query):
 q=norm(query);hits=[i for i in kb['intents'] if q==i['id'] or any(norm(t) in q for t in i['terms'])]
 return {'query':query,'matched':bool(hits),'intents':hits,'scope_required':['cabinet','reporting_period','report_type','metric','date_role'],'datasets':kb['datasets'],'guide':str(BASE/'GUIDE.md'),'fields_command':'field <точное название столбца>','source_policy':'Read source/version caveats; UI labels do not establish unverified API bindings.'}
def calculate(kb,ident,values,currency):
 f=next(x for x in kb['formulas'] if x['id']==ident)
 if not isinstance(values,dict) or set(values)!=set(f['inputs']):raise ValueError('Exact formula inputs required; unknown/missing components are not zero')
 if not currency.strip():raise ValueError('Currency required')
 if any(isinstance(x,(bool,list,dict,type(None),float)) for x in values.values()):raise ValueError('Use exact decimal strings or integers, never floats/bools/null')
 v={k:Decimal(str(x)) for k,x in values.items()}
 if not all(x.is_finite() for x in v.values()):raise ValueError('Amounts must be finite')
 if ident in ('net_sales','net_goods_payout'):
  if any(x<0 for x in v.values()):raise ValueError('Sales/returns inputs are unsigned separate totals; reconcile signs explicitly')
  result=v['sales']-v['returns']
 elif ident=='kvv_final':result=v['base_rate']-v['platform_discount_rate']
 elif ident=='item_payout_check':
  if v['price']<0 or v['payment_fee']<0:raise ValueError('Expected unsigned price/payment fee')
  result=v['price']*(Decimal(1)-v['commission_rate']/Decimal(100))-v['payment_fee']
 else:result=v['goods_net']-v['delivery']-v['storage']-v['processing']-v['penalties']-v['loyalty_fee_net']-v['loyalty_points_net']-v['deductions_signed']+v['loyalty_compensation']
 return {'formula':ident,'value':str(result),'currency':None if ident=='kvv_final' else currency,'unit':'percentage_points' if ident=='kvv_final' else 'currency_amount','rounding':'not applied; verify report-specific rounding','status':'ARITHMETIC_ONLY_NOT_REPORT_RECONCILIATION','rules':f['rules']}
def validate(kb):
 ids=[x['id'] for x in kb['fields']];assert len(ids)==len(set(ids))
 forms={x['id'] for x in kb['formulas']};known=set(ids);labels={}
 for f in kb['fields']:
  assert f['meaning'] and f['aggregation']
  for label in f['ui_labels']:
   n=norm(label);assert n not in labels or labels[n]==f['id'],label;labels[n]=f['id']
  assert f['api_binding'] in ('CONFIRMED_INSTALLED_CONTRACT','CONFIRMED_OFFICIAL_SCHEMA_AND_LOCAL_COLUMNS','CONFIRMED_OFFICIAL_SCHEMA_NOT_PRESENT_LOCALLY') or not f['api_keys']
  if f.get('local_column'):assert f['api_keys']==[f['local_column']]
 for i in kb['intents']:assert set(i['fields'])<=known and set(i['formulas'])<=forms
 assert (BASE/'GUIDE.md').is_file()
 return {'status':'PASS','fields':len(ids),'intents':len(kb['intents']),'formulas':len(forms),'network_calls':0,'archive_writes':0}
def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
 for name in ['route','field','formula']:
  a=s.add_parser(name);a.add_argument('query');a.add_argument('--json',action='store_true',help='Output is always structured JSON')
 for name in ['sources','storage','validate','inventory','bindings','schema']:s.add_parser(name)
 a=s.add_parser('summary');a.add_argument('--cabinet',required=True);a.add_argument('--type',choices=['1','2','both'],default='both');a.add_argument('--from',dest='start');a.add_argument('--to',dest='end');a.add_argument('--date-role',choices=['report_operation_date','operation_date','order_date'],default='report_operation_date');a.add_argument('--sku')
 a=s.add_parser('calculate');a.add_argument('formula');a.add_argument('--values',required=True);a.add_argument('--currency',required=True)
 a=s.add_parser('locate');a.add_argument('--cabinet',required=True);a.add_argument('--year',required=True,type=int);a.add_argument('--type',required=True,type=int,choices=[1,2])
 a=p.parse_args(argv);kb=load()
 if a.action=='route':out=route(kb,a.query)
 elif a.action=='field':
  found=field(kb,a.query);out={'query':a.query,'matched':bool(found),'fields':found,'binding_policy':kb['bindings_policy']}
 elif a.action=='formula':out={'matched':any(a.query==x['id'] for x in kb['formulas']),'formulas':[x for x in kb['formulas'] if a.query==x['id']]}
 elif a.action=='sources':out=kb['sources']
 elif a.action=='storage':out=kb['storage']
 elif a.action=='calculate':out=calculate(kb,a.formula,json.loads(a.values,parse_float=Decimal,object_pairs_hook=strict_pairs),a.currency)
 elif a.action=='validate':out=validate(kb)
 elif a.action=='bindings':out=json.loads((BASE/'field-bindings.json').read_text())
 elif a.action=='schema':out=json.loads((BASE/'schema-profile.json').read_text())
 elif a.action=='summary':out=reader().summarize(a.cabinet,(1,2) if a.type=='both' else (int(a.type),),start=a.start,end=a.end,date_role=a.date_role,nm_id=a.sku)
 elif a.action=='inventory':
  receipt=BASE/'archive-inventory.json'
  if not receipt.is_file():receipt=Path('/home/hermes/.local/share/msp/wb-financial-reports/archive-inventory.json')
  out=json.loads(receipt.read_text()) if receipt.is_file() else {'status':'NOT_AUDITED','archive_absence_proven':False}
  out['live_campaigns']=[]
  for cabinet,folder in [('wb_laser_master','msp-finance-history-wb-laser-master-20261106'),('wb_novokshenov','msp-finance-history-wb-novokshenov-20261108'),('wb_dmitrieva','msp-finance-history-wb-dmitrieva-20261109-r1')]:
   path=Path('/home/hermes/.local/state')/folder/'state.json'
   try:
    state=json.loads(path.read_text());last=state.get('last') or {}
    out['live_campaigns'].append({'cabinet':cabinet,'state_path':str(path),'phase':state.get('phase'),'wakes':state.get('wakes'),'request_nonce':last.get('request_nonce'),'last_receipt_status':last.get('status'),'reason':state.get('reason'),'full_history_verified':False})
   except FileNotFoundError:out['live_campaigns'].append({'cabinet':cabinet,'status':'NO_CAMPAIGN_STATE'})
   except PermissionError:out['live_campaigns'].append({'cabinet':cabinet,'status':'ACCESS_DENIED'})
 else:
  if a.cabinet not in kb['cabinet_allowlist'] or not 2020<=a.year<=2100:raise ValueError('Known cabinet and bounded year required')
  dataset=kb['datasets']['weekly_main' if a.type==1 else 'weekly_buyout']['name'];scope=Path(kb['storage']['archive_root'])/'.b7-generations'/dataset/a.cabinet/str(a.year)
  out={'scope':str(scope),'current_pointer':str(scope/'CURRENT.json'),'policy':'Location only, not proof of presence or permission. Resolve/verify CURRENT with installed generation_store reader; never concatenate generations.','business_key':['cabinet','dataset','reportId','rrdId'],'amount_source':'selected generation data.csv; preserve _raw_json'}
  try:
   with (scope/'CURRENT.json').open('rb') as stream:stream.read(1)
   out['pointer_status']='READABLE'
  except FileNotFoundError:out['pointer_status']='NO_POINTER_AT_EXPECTED_LOCATION'
  except PermissionError:out['pointer_status']='ACCESS_DENIED'
  out['archive_absence_proven']=False
  out['inventory_command']='msp-wb-report-guide inventory'
  if out['pointer_status']=='READABLE':
   snap=reader().resolve(a.cabinet,a.type,a.year)
   out['selected_snapshot']=reader().exportable_snapshot(snap)
   out['policy']='Selected CURRENT snapshot descriptor, metadata and CSV checksums verified; rows are fully validated by summary/iter_rows. Historical generations must not be concatenated.'
 print(json.dumps(out,ensure_ascii=False,indent=2));return 0
if __name__=='__main__':
 try:raise SystemExit(main())
 except (ValueError,KeyError,AssertionError,InvalidOperation,StopIteration,OSError) as exc:
  print(json.dumps({'status':'ERROR','error_type':type(exc).__name__,'message':str(exc)},ensure_ascii=False));raise SystemExit(2)
