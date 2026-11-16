"""Deterministic completion summaries; no secrets, transport or file writes."""
import datetime
WB=('wb_dmitrieva','wb_laser_master','wb_novokshenov')
OZ=('ozon_dmitrieva','ozon_laser_master','ozon_novokshenov')
NAMES={'dmitrieva':'ИП Дмитриева','laser_master':'Лазер-мастер','novokshenov':'ИП Новокшенов'}
TERMINAL={'VERIFIED','WAITING_NEXT_RUN','WAITING_NEXT_DAY','HOLD'}
def name(cab):return ('Wildberries' if cab.startswith('wb_') else 'Ozon')+' — '+NAMES[cab.split('_',1)[1]]
def covered(index,day):
 return any(r.get('period')=='weekly' and r.get('report_type') in (1,2) and r['from']<=day<=r['to'] for r in index.get('reports',{}).values())
def assess_cycle(cycle,known,cabinets,day,kind,indices=None):
 if not isinstance(cycle,dict) or cycle.get('manual') or cycle.get('bootstrap'):return None
 matching=[j for j in cycle.get('jobs',[]) if (j.get('period','daily')==kind)]
 if any(j.get('status') not in TERMINAL for j in matching):return None
 result=[];keys=set()
 for j in matching:
  if j['cabinet'] not in cabinets:raise ValueError('foreign cabinet in cycle')
  # Include yesterday and any unfinished older tails, not successful old dates.
  start=j.get('day',j.get('from'));end=j.get('day',j.get('to'))
  if kind=='daily' and start!=day and j['status']=='VERIFIED':continue
  missing=[p for p in j.get('result',{}).get('parts',[]) if p.get('status')=='WAITING_DATA' and p.get('type') in (1,2)]
  result.append(dict(cabinet=j['cabinet'],start=start,end=end,status=j['status'],attempts=j.get('attempts',0),missing_types=[p['type'] for p in missing],published_missing=any(bool(p.get('report_ids')) for p in missing)))
  keys.add((j['cabinet'],start,end))
 end=day
 start=(datetime.date.fromisoformat(day)-datetime.timedelta(days=6)).isoformat() if kind=='weekly' else day
 for cab in cabinets:
  if (cab,start,end) in keys:continue
  key=cab+'|'+day if cab.startswith('ozon_') else '|'.join((cab,kind,start,end))
  prior=known.get(key,{})
  verified=prior.get('status')=='VERIFIED'
  if not verified and kind=='daily' and cab.startswith('wb_'):verified=covered((indices or {}).get(cab,{}),day)
  result.append(dict(cabinet=cab,start=start,end=end,status='VERIFIED' if verified else 'UNCONFIRMED',attempts=0))
 return result
def weekly(wb_cycle,wb_known,end):
 items=assess_cycle(wb_cycle,wb_known,WB,end,'weekly')
 return None if items is None else dict(kind='weekly',day=end,items=items)
def _legacy_render(report):
 day=datetime.date.fromisoformat(report['day']);kind=report['kind'];items=report['items']
 if kind not in ('daily','weekly') or not items:raise ValueError('summary scope')
 allowed=WB+OZ if kind=='daily' else WB
 seen=set()
 for row in items:
  if row['cabinet'] not in allowed or row['status'] not in TERMINAL|{'UNCONFIRMED'}:raise ValueError('summary row')
  a=datetime.date.fromisoformat(row['start']);b=datetime.date.fromisoformat(row['end'])
  if a>b or b>day or (kind=='daily' and a!=b):raise ValueError('summary dates')
  k=(row['cabinet'],row['start'],row['end'])
  if k in seen:raise ValueError('duplicate summary row')
  seen.add(k)
 if any((cab,report['day'],report['day']) not in seen for cab in allowed) and kind=='daily':raise ValueError('incomplete daily cabinet summary')
 if kind=='weekly':
  begin=(day-datetime.timedelta(days=6)).isoformat()
  if day.weekday()!=6 or any((cab,begin,report['day']) not in seen for cab in WB):raise ValueError('weekly scope')
 failed=[r for r in items if r['status']!='VERIFIED']
 title=('Ежедневные отчёты за '+day.strftime('%d.%m.%Y')) if kind=='daily' else ('Недельные отчёты Wildberries за '+(day-datetime.timedelta(days=6)).strftime('%d.%m')+'–'+day.strftime('%d.%m.%Y'))
 if not failed:
  return '✅ '+title+'\nВсе отчёты загружены и проверены. '+('WB и Ozon, все три юридических лица.' if kind=='daily' else 'Все три юридических лица. Покрытые дневные данные заменены недельными. Остальные дневные данные, исходники и журналы сохранены.')
 verified=[name(r['cabinet']) for r in items if r['status']=='VERIFIED' and r['end']==report['day']]
 lines=['⚠️ '+title,'Загружены: '+(', '.join(verified) if verified else 'нет подтверждённых загрузок')+'.','Не загружены:']
 for row in failed:
  reason=('отчёт не получен после '+str(row['attempts'])+' проверок') if row['status'] in ('WAITING_NEXT_RUN','WAITING_NEXT_DAY') else ('техническая неопределённость, нужна сверка' if row['status']=='HOLD' else 'нет подтверждения загрузки')
  if row.get('published_missing') and row.get('missing_types'):
   reason+='; не скачан опубликованный отчёт: '+', '.join('основной' if t==1 else 'выкупы' for t in row['missing_types'])
  dates=row['start']+(' — '+row['end'] if row['end']!=row['start'] else '')
  lines.append('• '+name(row['cabinet'])+' за '+dates+': '+reason+'.')
 if kind=='weekly':lines.append('Дневные данные непокрытых периодов сохранены.')
 else:lines.append('Готовые данные сохранены. Пропуски ожидают следующего запуска или ручной загрузки.')
 text='\n'.join(lines)
 if len(text.encode('utf-16-le'))//2>3900:raise ValueError('summary too long; no silent truncation')
 return text

# Daily notices V2; weekly assessment and rendering above remain unchanged.
DAILY_STATES=TERMINAL|{'UNCONFIRMED','WAITING_DATA','PENDING','IN_FLIGHT'}
def legal(cab):return NAMES[cab.split('_',1)[1]]
def render_daily(report):
 day=datetime.date.fromisoformat(report['day']);items=report['items'];seen=set()
 for row in items:
  a=datetime.date.fromisoformat(row['start']);b=datetime.date.fromisoformat(row['end']);key=(row['cabinet'],row['start'],row['end'])
  if row['cabinet'] not in WB+OZ or row['status'] not in DAILY_STATES or a!=b or b>day or key in seen:raise ValueError('daily summary scope')
  if type(row.get('attempts',0)) is not int or row.get('attempts',0)<0:raise ValueError('daily attempt count')
  seen.add(key)
 if any((cab,report['day'],report['day']) not in seen for cab in WB+OZ):raise ValueError('incomplete daily cabinet summary')
 failed=[r for r in items if r['status']!='VERIFIED']
 heading='Ежедневные отчёты за '+day.strftime('%d.%m.%Y')
 if report.get('update_id'):heading='Обновление: '+heading[0].lower()+heading[1:]
 lines=[('⚠️ ' if failed else '✅ ')+heading,'','Загружены:']
 for title,cabinets in (('Wildberries',WB),('Ozon',OZ)):
  ready=[r for c in cabinets for r in items if r['cabinet']==c and r['status']=='VERIFIED' and r['end']==report['day']]
  lines+=['',title]
  if not ready:lines.append('• Пока нет подтверждённых загрузок')
  for r in ready:
   suffix=' — данные получены в недельном отчёте; дневной отдельно не докачивался' if r.get('covered_weekly') else ''
   lines.append('• '+legal(r['cabinet'])+suffix)
 if failed:
  lines+=['','Не загружены:']
  for r in failed:
   n=r.get('attempts',0);stamp=r.get('last_checked_at');when=''
   if stamp:
    t=datetime.datetime.fromisoformat(stamp)
    if t.tzinfo is None:raise ValueError('check timestamp timezone')
    from zoneinfo import ZoneInfo
    when='; последняя проверка завершена '+t.astimezone(ZoneInfo('Europe/Moscow')).strftime('%d.%m в %H:%M')+' МСК'
   prefix='• '+name(r['cabinet'])+' за '+datetime.date.fromisoformat(r['end']).strftime('%d.%m.%Y')+': '
   if r['status'] in ('WAITING_NEXT_RUN','WAITING_NEXT_DAY'):
    reason='данные не загружены после '+str(n)+' проверок'+when+'. Проверки на сегодня завершены.'
   elif r['status']=='HOLD':
    detail='маркетплейс ограничил лимит запросов (HTTP 429)' if r.get('http_status')==429 else ('ошибка доступа (HTTP '+str(r['http_status'])+')' if r.get('http_status') in (401,403) else 'техническая ошибка')
    reason=detail+'; выполнено проверок: '+str(n)+when+'. Повторы остановлены до сверки; это не отсутствие отчёта.'
   elif r['status']=='WAITING_DATA':
    reason='данные пока не получены; выполнено проверок: '+str(n)+when+'.'
    if r.get('next_due'):
     from zoneinfo import ZoneInfo
     reason+=' Следующая проверка не ранее '+datetime.datetime.fromtimestamp(r['next_due'],ZoneInfo('Europe/Moscow')).strftime('%H:%M')+' МСК.'
   else:reason='загрузка ещё не подтверждена; выполняется проверка.'
   if r.get('published_missing'):reason+=' Не скачан опубликованный отчёт: '+', '.join('основной' if t==1 else 'выкупы' for t in r.get('missing_types',[]))+'.'
   lines.append(prefix+reason)
 else:lines+=['','Все данные за указанную дату получены и проверены.']
 text='\n'.join(lines)
 if len(text.encode('utf-16-le'))//2>3900:raise ValueError('daily summary too long; no silent truncation')
 return text

def render(report):
 return render_daily(report) if report.get('kind')=='daily' else _legacy_render(report)

def daily_items(cycle,known,cabinets,day,indices):
 if not isinstance(cycle,dict) or cycle.get('manual') or cycle.get('bootstrap'):return None
 result=[];seen=set()
 for j in cycle.get('jobs',[]):
  if j.get('period','daily')!='daily':continue
  cab=j['cabinet'];start=j.get('day',j.get('from'));end=j.get('day',j.get('to'))
  if cab not in cabinets:raise ValueError('foreign cabinet')
  if start!=day and j['status']=='VERIFIED':continue
  known_key=cab+'|'+start if cab.startswith('ozon_') else '|'.join((cab,'daily',start,end))
  prior=known.get(known_key,{})
  state=j['status'];weekly=False
  if state!='VERIFIED' and prior.get('status')=='VERIFIED':state='VERIFIED'
  if cab.startswith('wb_') and state!='VERIFIED' and covered(indices.get(cab,{}),start):state='VERIFIED';weekly=True
  if state in ('PENDING','IN_FLIGHT'):return None
  missing=[p for p in j.get('result',{}).get('parts',[]) if p.get('status')=='WAITING_DATA' and p.get('type') in (1,2)]
  item=dict(cabinet=cab,start=start,end=end,status=state,attempts=j.get('attempts',0),covered_weekly=weekly,missing_types=[p['type'] for p in missing],published_missing=any(bool(p.get('report_ids')) for p in missing))
  for key in ('last_checked_at','next_due','http_status'):
   if key in j:item[key]=j[key]
  result.append(item);seen.add((cab,start,end))
 for cab in cabinets:
  if (cab,day,day) in seen:continue
  key=cab+'|'+day if cab.startswith('ozon_') else '|'.join((cab,'daily',day,day))
  verified=known.get(key,{}).get('status')=='VERIFIED';weekly=not verified and cab.startswith('wb_') and covered(indices.get(cab,{}),day)
  result.append(dict(cabinet=cab,start=day,end=day,status='VERIFIED' if verified or weekly else 'UNCONFIRMED',attempts=0,covered_weekly=weekly))
 return result

def daily(wb_cycle,oz_cycle,wb_known,oz_known,day,indices=None):
 wb=daily_items(wb_cycle,wb_known,WB,day,indices or {});oz=daily_items(oz_cycle,oz_known,OZ,day,{})
 return None if wb is None or oz is None else dict(kind='daily',day=day,items=wb+oz)

def signature(report):
 import hashlib,json
 # Changes in attempt count/timestamp alone are not a notification event.
 # WAITING -> terminal failure or ready, HOLD -> weekly coverage are events.
 rows=sorted((r['cabinet'],r['start'],r['end'],r['status'],bool(r.get('covered_weekly')),bool(r.get('published_missing')),tuple(r.get('missing_types',[]))) for r in report['items'])
 return hashlib.sha256(json.dumps(rows,separators=(',',':')).encode()).hexdigest()[:24]
