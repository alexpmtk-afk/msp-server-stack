"""Observed MPSTATS comments/period fields, never a fabricated complete star history."""
from datetime import date,datetime,timezone,timedelta
from math import isfinite

def review_source_evidence(*,sku,event_date,after_start,after_end,comments=None,period=None,comments_status='UNAVAILABLE',period_status='UNAVAILABLE',lk_status='NOT_VERIFIED',before_start=None,before_end=None,marketplace='wb'):
 t,first,last=map(date.fromisoformat,(event_date,after_start,after_end))
 if first<=t or last<first or (last-first).days>=90:raise ValueError('Invalid completed after-window')
 out={'marketplace':marketplace,'sku':str(sku),'event_date':event_date,'after_start':after_start,'after_end':after_end,'new_positive_ratings':None,'new_positive_text_reviews':None,'rating_change':None,'observed_positive_text_entries':None,'comments_status':comments_status,'period_status':period_status,'lk_status':lk_status,'complete_publication_history':False,'independent_reviewers_verified':False,'causal_effect_proven':False,'observations':[]}
 if isinstance(comments,dict) and isinstance(comments.get('comments'),list):
  entries=[];all_records=[]
  seen_ids={}
  duplicate_ids=0
  conflicting_ids=0
  rows_without_stable_id=0
  for row in comments['comments']:
   if not isinstance(row,dict):continue
   identifier=next((str(row[key]) for key in ('id','review_id','feedback_id','feedbackId','uuid') if row.get(key) not in (None,'')),None)
   if identifier is None:
    rows_without_stable_id+=1
   else:
    # Collapse only identical stable IDs, never independent records sharing
    # a calendar date. Conflicting payloads mark the count ambiguous.
    record=(str(row.get('date')),row.get('valuation'),bool(str(row.get('text') or '').strip()))
    if identifier in seen_ids:
     duplicate_ids+=1
     if seen_ids[identifier]!=record:conflicting_ids+=1
     continue
    seen_ids[identifier]=record
   try:d=date.fromisoformat(row.get('date','')[:10])
   except (ValueError,TypeError):continue
   value=row.get('valuation')
   if first<=d<=last and type(value) in (int,float) and value in (1,2,3,4,5):
    record={'date':d.isoformat(),'valuation':value,'has_text':isinstance(row.get('text'),str) and bool(row['text'].strip())}
    if identifier is not None:record['id']=identifier
    all_records.append(record)
   if first<=d<=last and type(value) in (int,float) and value in (4,5) and isinstance(row.get('text'),str) and row['text'].strip():
    entries.append({'date':d.isoformat(),'valuation':value,'has_text':True})
  out['observed_review_records']=all_records if not conflicting_ids else []
  out['duplicate_review_ids']=duplicate_ids
  out['conflicting_review_ids']=conflicting_ids
  out['rows_without_stable_id']=rows_without_stable_id
  # Distinct publications are NEVER certified when ID/coverage is missing.
  out['observed_positive_text_entries']=len(entries) if not conflicting_ids else None
  out['observed_entries']=entries if not conflicting_ids else []
  if conflicting_ids:out['observations'].append('CONFLICTING_DUPLICATE_REVIEW_IDS_COUNT_UNAVAILABLE')
  if rows_without_stable_id:out['observations'].append('REVIEW_IDENTITIES_UNVERIFIED')
  stamp=comments.get('last_request')
  if type(stamp) in (int,float) and isfinite(stamp):
   out['comments_cache_updated_utc']=datetime.fromtimestamp(stamp,timezone.utc).isoformat()
  out['observations'].append('COMMENTS_HAS_NO_TOTAL_OR_HISTORICAL_COMPLETENESS_CONTRACT')
 if isinstance(period,list):
  points={};dups=[];padded=[]
  for row in period:
   if not isinstance(row,dict):continue
   day=row.get('data')
   try:date.fromisoformat(day)
   except (ValueError,TypeError):continue
   if day in points:dups.append(day)
   if row.get('daynum')==0:padded.append(day);continue
   points[day]=row
  out['duplicate_dates']=dups;out['placeholder_dates']=padded
  if dups:out['observations'].append('DUPLICATE_PERIOD_DATES_SUPPRESS_RATING_AND_COUNTER_DELTA')
  # Only expose endpoints as raw provider observations, not a verified star counter.
  baseline=points.get(event_date);end=points.get(after_end)
  if baseline and end:
   a,b=baseline.get('comments'),end.get('comments')
   if type(a) is int and type(b) is int and a>=0 and b>=0 and not dups:
    out['provider_comments_counter']={'before_date':event_date,'before':a,'after_date':after_end,'after':b,'observed_difference':b-a,'semantics':'OBSERVED_COUNTER_DIFFERENCE_NOT_PROVEN_NEW_PUBLICATIONS'}
  ratings=[{'date':d,'rating':p['rating']} for d,p in sorted(points.items()) if first.isoformat()<=d<=last.isoformat() and type(p.get('rating')) in (int,float) and 1<=p['rating']<=5]
  if ratings and not dups:out['valid_rating_observations']={'first':ratings[0],'last':ratings[-1]}
  if baseline and end and not dups and all(type(x) in (int,float) and not isinstance(x,bool) and 1<=x<=5 for x in [baseline.get('rating'),end.get('rating')]):out['rating_change']=end['rating']-baseline['rating']
  out['observations'].append('NO_FOUR_VERIFIED_TOTAL_NEGATIVE_TEXT_NEGATIVE_TEXT_COUNTERS')
 if before_start is not None or before_end is not None:
  b1,b2=map(date.fromisoformat,(before_start,before_end))
  if not b1<=b2<t or (b2-b1)!=(last-first):raise ValueError('Invalid equal before-window')
  out['before']=_window_observations(period,comments,before_start,before_end)
  out['after']=_window_observations(period,comments,after_start,after_end)
  x,y=out['before']['rating_end'],out['after']['rating_end']
  out['rating_change']=(y['rating']-x['rating']) if x and y else None
  out['rating_comparison']='EXACT_WINDOW_END_SNAPSHOTS' if x and y else 'UNKNOWN_ENDPOINT_RATING'
 return out

def format_review_source_evidence_ru(e):
 lines=['ИСТОРИЯ ОЦЕНОК И ОТЗЫВОВ ПОСЛЕ ДАТЫ В РЕЕСТРЕ']
 n=e.get('observed_positive_text_entries')
 if n is not None:
  lines.append('MPSTATS comments: получено записей с текстом и оценкой 4–5★ в окне: '+str(n)+'. Это число полученных записей, не полное число новых отзывов.')
  for x in e.get('observed_entries',[]):lines.append('Наблюдаемая запись: '+x['date']+', '+str(x['valuation'])+'★, с текстом. Независимость автора и связь с зарегистрированным самовыкупом не установлены.')
 if e.get('comments_cache_updated_utc'):lines.append('Последнее обновление кэша comments: '+e['comments_cache_updated_utc']+'. Запрос d1/d2 не ограничивает этот метод.')
 counter=e.get('provider_comments_counter')
 if counter:lines.append('by_period.comments: наблюдаемый счётчик '+str(counter['before'])+' → '+str(counter['after'])+' ('+counter['before_date']+' → '+counter['after_date']+'). Разность '+str(counter['observed_difference'])+' не равна доказанному числу новых публикаций.')
 ratings=e.get('valid_rating_observations')
 if ratings:lines.append('Наблюдаемый рейтинг: '+str(ratings['first']['rating'])+' на '+ratings['first']['date']+'; '+str(ratings['last']['rating'])+' на '+ratings['last']['date']+'.')
 if e.get('rating_change') is None:lines.append('Изменение общего рейтинга: UNKNOWN — нет двух валидных сопоставимых оценок; 0 не трактуется как рейтинг 0★.')
 lines.append('Точное число новых оценок 4–5★, положительных текстовых отзывов и оценок без текста: UNKNOWN. Средняя оценка и общий счётчик не восстанавливают распределение по звёздам.')
 lines.append('Дневная таблица личного кабинета: '+e.get('lk_status','UNKNOWN')+'. Полнота истории и независимость авторов не доказаны; найденная запись может относиться к исходному собственному выкупу.')
 return '\n'.join(lines)


def _window_observations(period,comments,d1,d2):
 """Exact window endpoints, partial observations kept distinct from new counts."""
 first,last=map(date.fromisoformat,(d1,d2)); points={};duplicates=set()
 for row in period if isinstance(period,list) else []:
  if not isinstance(row,dict):continue
  day=row.get('data')
  try:date.fromisoformat(day)
  except (TypeError,ValueError):continue
  if day in points:duplicates.add(day)
  points[day]=row
 valid={d:r for d,r in points.items() if d not in duplicates and r.get('daynum')!=0}
 days=(last-first).days+1
 observed=[d for d in valid if d1<=d<=d2]
 def rating(d):
  v=valid.get(d,{}).get('rating')
  return {'date':d,'rating':v} if type(v) in (int,float) and isfinite(v) and 1<=v<=5 else None
 start=rating(d1);end=rating(d2)
 previous=(first-timedelta(days=1)).isoformat()
 a,b=valid.get(previous,{}).get('comments'),valid.get(d2,{}).get('comments')
 net=b-a if type(a) is int and type(b) is int and min(a,b)>=0 else None
 # Reuse the conservative text-record adapter; no recursive before/after arguments.
 entries=review_source_evidence(sku='window',event_date=previous,after_start=d1,after_end=d2,comments=comments)
 ratings=[rating(d) for d in sorted(observed) if rating(d)]
 return {'date_from':d1,'date_to':d2,'completed_days':days,'observed_days':len(observed),
         'daily_coverage_complete':len(observed)==days,'rating_start':start,'rating_end':end,
         'first_valid_rating':ratings[0] if ratings else None,'last_valid_rating':ratings[-1] if ratings else None,
         'counter_baseline_date':previous,'counter_end_date':d2,'counter_net_change':net,
         'counter_semantics':'OBSERVED_COUNTER_DIFFERENCE_NOT_PROVEN_NEW_PUBLICATIONS',
         'positive_text_records':entries.get('observed_entries',[]),
         'review_records':entries.get('observed_review_records',[]),
         'positive_text_record_count':entries.get('observed_positive_text_entries'),
         'new_positive_ratings':None,'new_positive_text_reviews':None,
         'negative_ratings':None,'complete_publication_history':False,'duplicate_dates':sorted(duplicates)}


_legacy_format_review_source_evidence_ru=format_review_source_evidence_ru

def format_review_source_evidence_ru(e):
 if 'before' not in e:return _legacy_format_review_source_evidence_ru(e)
 lines=['ОЦЕНКИ И ОТЗЫВЫ','Дата зарегистрированного собственного отзыва/оценки по реестру: '+e['event_date']+'. Это собственное событие, не независимый покупатель.']
 lines.extend(_comparison_table_ru(e))
 for side,label in [('before','ДО'),('after','ПОСЛЕ')]:
  w=e[side]
  lines.append(label+': '+w['date_from']+' — '+w['date_to']+'; '+str(w['completed_days'])+' завершённых дней.')
  r=w['rating_end']
  lines.append('Рейтинг на конец периода: '+(str(r['rating'])+'★ на '+r['date'] if r else 'UNKNOWN — нет валидного снимка на точную конечную дату; rating=0 не является 0★')+'; источник: MPSTATS wb_sku(by_period).')
  if not r and w['last_valid_rating']:
   r=w['last_valid_rating'];lines.append('Последнее доступное наблюдение внутри периода (не конечный снимок): '+str(r['rating'])+'★ на '+r['date']+'.')
  n=w['positive_text_record_count']
  lines.append('Получено положительных текстовых записей 4–5★: '+(str(n)+' (не полное число публикаций)' if n is not None else 'UNKNOWN — comments не получен')+'; источник: wb_sku(comments).')
  for item in w.get('review_records',w['positive_text_records']):
   lines.append('Наблюдаемая запись: '+item['date']+', '+str(item['valuation'])+'★; '+('с текстом' if item['has_text'] else 'без текста')+('; ID: '+item['id'] if item.get('id') is not None else '; ID не предоставлен')+'; смещение от даты реестра '+str((date.fromisoformat(item['date'])-date.fromisoformat(e['event_date'])).days)+' дней. Происхождение и связь с событием не установлены.')
  if w['counter_net_change'] is not None:lines.append('Чистое изменение наблюдаемого by_period.comments: '+str(w['counter_net_change'])+' ('+w['counter_baseline_date']+' → '+w['counter_end_date']+'); не число новых публикаций и не число 4–5★.')
  lines.append('Покрытие дневных наблюдений by_period: '+str(w['observed_days'])+'/'+str(w['completed_days'])+'; полнота истории публикаций не подтверждена.')
 if e.get('rating_change') is not None:lines.append('Изменение рейтинга между точными концами ДО/ПОСЛЕ: '+str(e['rating_change'])+' балла; наблюдение, не причинный эффект.')
 else:lines.append('Изменение рейтинга ДО/ПОСЛЕ: UNKNOWN — нет двух валидных конечных снимков.')
 if e.get('strict_rating_comparison',{}).get('status') not in ('COMPARABLE_DAILY_COUNTS','COMPARABLE_NET_CHANGES'):
  lines.append('Полное количество новых положительных оценок не установлено. UNKNOWN — нет всех четырёх проверенных исторических рядов за оба периода. Средний рейтинг и общий счётчик их не заменяют.')
 lines.append('Источники comments/by_period: '+('часть запросов пропущена из-за лимита MPSTATS' if 'CALL_BUDGET' in e.get('comments_status','')+';'+e.get('period_status','') else 'результаты чтения и ограничения отражены выше')+'.')
 lines.append('Дневная таблица кабинета: '+e.get('lk_status','NOT_VERIFIED')+'. Неизвестные значения не равны нулю.')
 if e.get('comments_cache_updated_utc'):lines.append('Кэш comments обновлён: '+e['comments_cache_updated_utc']+'; полнота до конца окна не доказана.')
 lines.append('Независимость покупателей и причинный эффект не подтверждены. Тексты отзывов в отчёт не включаются.')
 if e.get('marketplace','wb')=='wb':
  lines.append('WB: здесь сравнивается исходное поле rating MPSTATS, которое может быть округлено. Это не подтверждённый точный дробный рейтинг; отдельное commentsvaluation проверяется в запросе истории.')
 return '\n'.join(lines).replace('wb_sku','ozon_sku' if e.get('marketplace')=='oz' else 'wb_sku')


def _comparison_table_ru(e):
 pair=e.get('strict_rating_comparison') or {}
 def value(side,field):
  v=pair.get(side,{}).get(field)
  if v is None:return 'неизвестно'
  return str(v)+(' (чистое изменение)' if pair[side].get('net_change_only') else '')
 def change(field):
  v=pair.get('change',{}).get(field)
  return str(v) if v is not None else 'неизвестно'
 def text(side):
  v=value(side,'positive_reviews_with_text_4_5')
  if v!='неизвестно':return v
  n=e[side].get('positive_text_record_count')
  return str(n)+' полученных записей; история неполная' if n is not None else 'неизвестно'
 def rating(side):
  r=e[side].get('rating_end')
  return str(r['rating'])+'★ ('+r['date']+')' if r else 'неизвестно'
 def coverage(side):
  state=pair.get(side,{}).get('status')
  if state=='DAILY_POSITIVE_COUNTS_OBSERVED':return 'полный проверенный дневной ряд оценок'
  if state=='NET_RATING_COUNT_CHANGE_ONLY':return 'проверены граничные снимки; публикации неизвестны'
  return 'частичная; публикации неизвестны' if e[side].get('observed_days') or e[side].get('positive_text_record_count') is not None else 'неизвестна'
 lines=['| Показатель | ДО | ПОСЛЕ | Изменение |','|---|---|---|---|',
 '| Положительные оценки 4–5★ | '+value('before','positive_ratings_4_5')+' | '+value('after','positive_ratings_4_5')+' | '+change('positive_ratings_4_5')+' |',
 '| Положительные отзывы с текстом | '+text('before')+' | '+text('after')+' | '+change('positive_reviews_with_text_4_5')+' |',
 '| Положительные оценки без текста | '+value('before','positive_ratings_without_text_4_5')+' | '+value('after','positive_ratings_without_text_4_5')+' | '+change('positive_ratings_without_text_4_5')+' |',
 '| Общий рейтинг | '+rating('before')+' | '+rating('after')+' | '+(str(e['rating_change']) if e.get('rating_change') is not None else 'неизвестно')+' |',
 '| Полнота истории | '+coverage('before')+' | '+coverage('after')+' | — |']
 if pair.get('source_ref'):lines.append('Источник четырёх рядов: '+pair['source_ref']+'.')
 if pair.get('status')=='COMPARABLE_NET_CHANGES':lines.append('Сравниваются чистые изменения накопительных счётчиков, не число новых публикаций.')
 if pair.get('change',{}).get('positive_ratings_4_5') is not None:
  lines.append('Разница ПОСЛЕ минус ДО: положительные оценки '+str(pair['change']['positive_ratings_4_5'])+', положительные тексты '+str(pair['change']['positive_reviews_with_text_4_5'])+'. Происхождение оценок и влияние на заказы не установлены.')
 lines.append('Оценки, тексты и рейтинг — разные показатели. Количество независимых покупателей и влияние на заказы не установлены.')
 return lines
