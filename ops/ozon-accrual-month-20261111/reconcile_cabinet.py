"""Read-only independent cabinet XLSX vs retained API detailed components."""
from pathlib import Path
import json,csv,zipfile,xml.etree.ElementTree as E,collections,hashlib
from decimal import Decimal
from datetime import datetime,timedelta
SOURCE=Path('/home/hermes/workspace/ozon-report-semantics-20261111/incoming/Отчет по начислениям_01.01.2026-31.01.2026.xlsx')
ROOT=Path('/opt/mcp/data/msp-marketplace-reports/ozon-accrual-month-pilot-20261111')
OUT=Path(__file__).parent
ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
sha=lambda b:hashlib.sha256(b).hexdigest()
with zipfile.ZipFile(SOURCE) as z:
 strings=[]
 if 'xl/sharedStrings.xml' in z.namelist():strings=[''.join(x.itertext()) for x in E.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si',ns)]
 root=E.fromstring(z.read('xl/worksheets/sheet1.xml'));values=[]
 for row in root.findall('m:sheetData/m:row',ns):
  cells=[]
  for c in row.findall('m:c',ns):
   assert c.find('m:f',ns) is None,'unexpected formula requires cache review'
   v=c.find('m:v',ns);v=v.text if v is not None else None
   if c.get('t')=='s':v=strings[int(v)] if v is not None else None
   elif c.get('t')=='inlineStr':v=''.join(c.find('m:is',ns).itertext())
   if c.get('r'):
    letters=''.join(x for x in c.get('r') if x.isalpha());idx=0
    for char in letters:idx=idx*26+ord(char)-64
    while len(cells)<idx-1:cells.append(None)
   cells.append(v)
  values.append(cells)
assert values[0]==['Период: 01.01.2026-31.01.2026']
header=values[1];assert len(header)==16 and len(header)==len(set(header))
rows=[]
for i,v in enumerate(values[2:],3):
 assert len(v)==len(header)
 r=dict(zip(header,v));r['_xlsx_row']=i
 r['_day']=(datetime(1899,12,30)+timedelta(days=int(r['Дата начисления']))).date().isoformat()
 assert '2026-01-01'<=r['_day']<='2026-01-31'
 rows.append(r)
api=[]
with (ROOT/'month.csv').open(encoding='utf-8-sig',newline='') as f:
 for r in csv.DictReader(f,delimiter=';'):api.append(json.loads(r['_raw_json']))
# Explicit UI aliases observed in this source pair; not inferred universally by sign.
alias={
'Эквайринг':1,'Обработка отменённых и невостребованных товаров':6,'Обработка возвратов Ozon':9,
'Обработка отправления Drop-off (СЦ)':16,'Ozon Рассрочка':22,'Доставка до места выдачи':29,
'Логистика':32,'Обработка возвратов, отмен и невыкупов партнёрами':45,'Размещение на складе':46,
'Бонусы продавца':48,'Подписка Premium':52,'Корректировка стоимости услуг':57,'Обратная логистика':59,
'Перечисление за доставку от покупателя':62,'Агентское вознаграждение Ozon Агрегатор realFBS':63,
'Услуги Партнёров Ozon на схеме realFBS':64,'Подготовка товара к вывозу: Валид':71,
'Вывоз товара со склада силами Ozon: Доставка до ПВЗ':71,'Звёздные товары':74,'Временное размещение товара партнерами':79}
sale_alias={'Выручка':'sale_price','Возврат выручки':'sale_price','Программы партнёров':'coinvestment','Баллы за скидки':'bonus','Вознаграждение за продажу':'sale_commission','Возврат вознаграждения':'sale_commission'}
def role(label):
 if label in sale_alias:return 'commission.'+sale_alias[label]
 if label.startswith('Обработка операционных ошибок продавца:'):return 'fee.14'
 return 'fee.'+str(alias[label])
excel=collections.Counter();component=collections.Counter();excelzero=collections.Counter();apizero=collections.Counter();dailyexcel=collections.defaultdict(Decimal);dailyapi=collections.defaultdict(Decimal);source_roles={};quantities=collections.Counter()
for r in rows:
 label=r['Тип начисления'];key=(r['_day'],r['ID начисления'] or '',r['SKU'] or '',role(label));amount=Decimal(r['Сумма итого, руб.'])
 excel[(*key,amount)]+=1;dailyexcel[r['_day']]+=amount;source_roles[label]=role(label)
 if not amount:excelzero[role(label)]+=1

def emit(row,sku,kind,amount):
 money=Decimal(amount['amount']);assert amount['currency']=='RUB'
 key=(row['date'],row.get('unit_number') or '',str(sku) if sku is not None else '',kind,money)
 component[key]+=1
 if not money:apizero[kind]+=1
for r in api:
 dailyapi[r['date']]+=Decimal(r['total_amount']['amount'])
 for prod in (r.get('posting') or {}).get('products',[]):
  c=prod.get('commission');sku=prod.get('sku')
  if c:
   quantities[str(prod.get('quantity'))]+=1
   for k in ['sale_price','coinvestment','bonus','sale_commission']:
    if c.get(k) is not None:emit(r,sku,'commission.'+k,c[k])
  for fee in (prod.get('delivery') or {}).get('services',[]):emit(r,sku,'fee.'+str(fee['type_id']),fee['accrued'])
 for group in (r.get('item_fees') or {}).get('fees',[]):
  for fee in group.get('fees',[]):emit(r,group.get('sku'),'fee.'+str(fee['type_id']),fee['accrued'])
 if r.get('non_item_fee'):
  fee=r['non_item_fee'];emit(r,None,'fee.'+str(fee['type_id']),fee['accrued'])
 for fee in (r.get('container_fees') or {}).get('fees',[]):emit(r,None,'fee.'+str(fee['type_id']),fee['accrued'])
# Compare every component, including zero amounts; nonzero diagnostics are secondary.
nonzero_excel=collections.Counter({k:n for k,n in excel.items() if k[-1]!=0})
nonzero_api=collections.Counter({k:n for k,n in component.items() if k[-1]!=0})
missing=nonzero_excel-nonzero_api;extra=nonzero_api-nonzero_excel
print('GRAIN_COUNTS',len(rows),len(api),'FLAT_COMPONENTS',sum(component.values()))
print('NONZERO_MISSING',sum(missing.values()),'EXTRA',sum(extra.values()))
print('MISSING_EXAMPLES',repr(list(missing.items())[:8]));print('EXTRA_EXAMPLES',repr(list(extra.items())[:8]))
print('ZERO_EXCEL',dict(excelzero),'ZERO_API',dict(apizero))
print('QUANTITIES',dict(quantities))
print('DAILY_MATCH',dict(dailyexcel)==dict(dailyapi));print('ALL_COMPONENTS_MATCH',excel==component)
result={'status':'PASS' if excel==component and dict(dailyexcel)==dict(dailyapi) else 'MISMATCH_REQUIRES_ANALYSIS','source_file':str(SOURCE),'source_sha256':sha(SOURCE.read_bytes()),'cabinet':'ozon_dmitrieva','period':'2026-01','excel_rows':len(rows),'api_grouped_rows':len(api),'api_flat_components':sum(component.values()),'excel_distinct_labels':len(source_roles),'nonzero_excel_components':sum(nonzero_excel.values()),'nonzero_api_components':sum(nonzero_api.values()),'unmatched_nonzero_excel':sum(missing.values()),'unmatched_nonzero_api':sum(extra.values()),'daily_sums_match':dict(dailyexcel)==dict(dailyapi),'month_total_excel':str(sum(dailyexcel.values(),Decimal(0))),'month_total_api':str(sum(dailyapi.values(),Decimal(0))),'currency':'RUB','zero_amount_components_api':dict(apizero),'all_components_including_zero_match':excel==component,'zero_excel_rows':dict(excelzero),'commission_product_quantity_counts':dict(quantities),'role_aliases':source_roles,'comparison_key':'date + API unit_number/XLSX ID начисления + SKU + component role + signed exact Decimal amount, multiplicity preserved','scope_limit':'Only this cabinet-month; all zero components compared and matched; quantities other than1 not observed for commission components. UI subtype detail (e.g. DefectRate reasons) not necessarily present in API; keep source labels as observed aliases, not invented future subtype classifications.','original_source_modified':False,'provider_calls':0}
(OUT/'cabinet-reconciliation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
