"""Readonly WB feed by exact verified cabinet/SKU/window; no synthetic order links."""
import json,subprocess
BLOCKS={'novok':3,'ultra':1,'lm':2,'laser':2}
def fetch_own_wb_orders(*,sku,store,d1,d2,run=None):
 if store not in BLOCKS:return {'status':'UNKNOWN_CABINET_MAPPING'}
 run=run or subprocess.run;rows=[];total=None
 for page in range(1,101):
  args={'blockid':BLOCKS[store],'nmId':int(sku),'date_from':d1,'date_to':d2,'page_size':50,'page':page}
  try:
   p=run(['/home/hermes/.local/bin/hermes-qrsite','api','wb_orders','--params',json.dumps(args)],capture_output=True,text=True,timeout=90)
   body=json.loads(p.stdout)
   if p.returncode or not body.get('success'):return {'status':'SOURCE_UNAVAILABLE'}
   data=body['data'];current=data['results']
   if total is None:total=data['count']
   if data['count']!=total:return {'status':'SOURCE_CHANGED_DURING_PAGINATION'}
   for r in current:
    if str(r.get('nmId'))!=str(sku) or r.get('blockid')!=BLOCKS[store] or not d1<=str(r.get('orderCreatedAt',''))[:10]<=d2:return {'status':'SOURCE_SCOPE_MISMATCH'}
   rows.extend(current)
   if not data.get('next'):
    ids=[r.get('orderId') for r in rows]
    if len(rows)!=total or len(set(ids))!=len(ids):return {'status':'PAGINATION_OR_IDENTITY_NOT_VERIFIED'}
    return {'status':'OBSERVED_OWN_WB_FEED','observed_units':len(rows),'pagination_complete':True,'source_load_coverage_verified':False,'scope':{'store':store,'blockid':BLOCKS[store],'sku':str(sku),'d1':d1,'d2':d2},'order_dates':[str(r['orderCreatedAt'])[:10] for r in rows],'current_statuses':[r.get('orderStatus') for r in rows],'independent_external_orders':None,'self_purchase_linkage':'NOT_ESTABLISHED_BY_ORDER_ID'}
  except Exception:return {'status':'SOURCE_UNAVAILABLE'}
 return {'status':'PAGINATION_LIMIT_REACHED'}

def format_own_orders_ru(before,after):
 if not all(x.get('status')=='OBSERVED_OWN_WB_FEED' for x in [before,after]):return 'Собственная лента WB: UNKNOWN — сверка не завершена. MPSTATS не заменяет фактические заказы.'
 return ('Собственная лента WB (заказанные единицы, не оплаченная/органическая выручка): '+str(before['observed_units'])+' → '+str(after['observed_units'])+'. Даты ДО: '+(', '.join(before['order_dates']) or 'записей нет')+'. Пагинация завершена, полнота исходной загрузки не доказана. Самовыкуп — отдельно; связь конкретной строки WB с реестром по ID не установлена. Если MPSTATS показывает заказы при отсутствии строк WB, это неподтверждённое расхождение источников, а не доказанный внешний спрос. Подтверждённые собственные заказы исключаются из независимого спроса; без доказанной связи по ID не вычитать их автоматически из чужих оценок.')
