"""Observed MPSTATS comments/period fields, never a fabricated complete star history."""
from datetime import date,datetime,timezone
from math import isfinite

def review_source_evidence(*,sku,event_date,after_start,after_end,comments=None,period=None,comments_status='UNAVAILABLE',period_status='UNAVAILABLE',lk_status='NOT_VERIFIED'):
 t,first,last=map(date.fromisoformat,(event_date,after_start,after_end))
 if first<=t or last<first or (last-first).days>=90:raise ValueError('Invalid completed after-window')
 out={'sku':str(sku),'event_date':event_date,'after_start':after_start,'after_end':after_end,'new_positive_ratings':None,'new_positive_text_reviews':None,'rating_change':None,'observed_positive_text_entries':None,'comments_status':comments_status,'period_status':period_status,'lk_status':lk_status,'complete_publication_history':False,'independent_reviewers_verified':False,'causal_effect_proven':False,'observations':[]}
 if isinstance(comments,dict) and isinstance(comments.get('comments'),list):
  entries=[]
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
   if first<=d<=last and type(value) in (int,float) and value in (4,5) and isinstance(row.get('text'),str) and row['text'].strip():
    entries.append({'date':d.isoformat(),'valuation':value,'has_text':True})
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
