"""Dated stars, not inferred stars from aggregate counters. Read-only sources."""
from datetime import datetime
import re
from zoneinfo import ZoneInfo

from apps.msp_self_analytics.wb_public_review_source import collect_public_wb


def enrich_public_fallback(history, reader, *, max_reads=24):
    """Try the known public WB feed when MCP has no records in the window.

    Sources stay separate: anonymous MCP rows cannot safely be unioned with IDs.
    Existing registered-event statistics are not silently replaced.
    """
    if history['marketplace'] != 'wb':
        return
    sample=history.get('received_review_sample')
    if sample and sample['records_received_in_period']:
        return
    detail={'status':'SOURCE_UNAVAILABLE','complete_publication_history':False}
    history['public_wb_detail']=detail
    if reader.calls >= max_reads:
        detail['status']='CALL_BUDGET'
        return
    try:
        sku=history['sku']
        full,state=reader.call('wb_sku',{'sku':int(sku),'report':'full',
            'd1':history['date_from'],'d2':history['date_to']})
        if state not in ('PASS_STRUCTURED','PASS_JSON') or not isinstance(full,dict) or str(full.get('id'))!=sku:
            return
        photos=(full.get('photo') or {}).get('list') or []
        host=None
        suffix=f'/vol{int(sku)//100000}/part{int(sku)//1000}/{sku}/images/'
        for photo in photos:
            url=photo.get('f') if isinstance(photo,dict) else None
            match=re.fullmatch(r'(https://basket-[0-9]+\.wbbasket\.ru)'+re.escape(suffix)+r'[^?#]+',url or '')
            if match:
                host=match.group(1)
                break
        if not host:
            detail['status']='VERIFIED_CARD_URL_UNAVAILABLE'
            return
        card=f'{host}/vol{int(sku)//100000}/part{int(sku)//1000}/{sku}/info/ru/card.json'
        public=collect_public_wb(sku=sku,card_url=card)
        records=[]
        for row in public['records']:
            if str(row.get('sku'))!=sku:
                continue
            day=datetime.fromisoformat(row['published_at_utc']).astimezone(ZoneInfo('Europe/Moscow')).date().isoformat()
            records.append({**row,'date':day})
        detail.update(status='PARTIAL_FEED_RECEIVED',source=public.get('source'),
            source_url=public.get('source_url'),received_at_utc=public.get('observed_at_utc'),
            source_record_count=len(records),
            latest_record_date=max((r['date'] for r in records),default=None),
            period_records=[r for r in records if history['date_from']<=r['date']<=history['date_to']],
            date_timezone='Europe/Moscow')
    except (OSError,ValueError,TypeError,KeyError,AttributeError,RuntimeError):
        # Exception messages may contain private transport/authentication URLs.
        detail['status']='SOURCE_UNAVAILABLE'
    finally:
        history['mpstats_calls']=reader.calls


def format_dated_detail_ru(history, *, own_review_dates=()):
    """Print all available dates, including ratings without review text."""
    own=set(own_review_dates)
    lines=['ОЦЕНКИ С ДАТАМИ — только найденные записи, не полная история.']
    rows=[r for w in history['windows'] for r in w['review_records']]
    sources=[('MPSTATS',rows)]
    diagnostic=history.get('review_feed_diagnostics') or {}
    lines.append('Лента MPSTATS: получено исходных строк '+str(diagnostic.get('received_rows') if diagnostic.get('received_rows') is not None else 'неизвестно')+
        '; последняя дата отдельной записи: '+str(diagnostic.get('latest_record_date') or 'неизвестна')+'.')
    public=history.get('public_wb_detail')
    if public:
        statuses={'PARTIAL_FEED_RECEIVED':'получена неполная выборка','CALL_BUDGET':'пропущена из-за лимита чтений',
            'SOURCE_UNAVAILABLE':'источник недоступен','VERIFIED_CARD_URL_UNAVAILABLE':'не получен проверенный адрес карточки'}
        lines.append('Прямая лента WB: '+statuses.get(public['status'],'результат не подтверждён')+
            '; последняя дата отдельной записи: '+str(public.get('latest_record_date') or 'неизвестна')+'.')
        if public['status']=='PARTIAL_FEED_RECEIVED':
            sources.append(('Прямая лента WB (даты по Москве)',public['period_records']))
    for title,records in sources:
        lines.append(title+':')
        if not records:
            lines.append('В заданном периоде отдельные записи не получены; число реально поставленных оценок неизвестно.')
            continue
        lines.append('Дата | Оценка | Учёт')
        for row in sorted(records,key=lambda r:(r['date'],r['valuation'])):
            label='отложена: собственная дата, автор не установлен' if row['date'] in own else 'авторство не установлено'
            lines.append(f"{row['date']} | {row['valuation']}★ | {label}")
        usable=[r for r in records if r['date'] not in own]
        stars={s:sum(r['valuation']==s for r in usable) for s in range(1,6)}
        mean=sum(r['valuation'] for r in usable)/len(usable) if usable else None
        lines.append('Вне собственных дат: '+', '.join(f'{s}★ — {n}' for s,n in stars.items())+
            '; средняя найденных: '+(str(round(mean,3)) if mean is not None else 'не определена')+'.')
    lines.append('Даты изменения общего счётчика не являются датами отдельных оценок; неизвестные звёзды не восстанавливаются из рейтинга.')
    return '\n'.join(lines)
