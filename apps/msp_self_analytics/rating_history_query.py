"""Read-only date queries over marketplace-specific MPSTATS observations.

The registered-event formulas remain in dated_rating_dynamics and are not
reimplemented here. This source query does not infer publication or causality.
"""
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
import re

from apps.msp_self_analytics.marketplace_rating_sources import (
    PASS, inspect_marketplace_history, source_adapter, _sku,
)


def _date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("INVALID_ISO_DATE")
    return date.fromisoformat(value)


def date_chunks(d1, d2):
    first, last = _date(d1), _date(d2)
    if first > last:
        raise ValueError("REVERSED_DATE_RANGE")
    while first <= last:
        end = min(last, first + timedelta(days=89))
        yield first.isoformat(), end.isoformat()
        first = end + timedelta(days=1)


def summarize_history(*, marketplace, sku, d1, d2, comments, period):
    """Expose exact endpoints and sample statistics, never missing-day fill."""
    adapter = source_adapter(marketplace)
    _sku(sku)
    chunks = list(date_chunks(d1, d2))
    normalized = adapter.normalize(comments, period)
    rows = normalized['period'] or []
    by_date, conflicts = {}, set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        day = row.get('data')
        try:
            _date(day)
        except (TypeError, ValueError):
            continue
        if day in by_date:
            conflicts.add(day)
        by_date[day] = row
    daily = []
    for day, row in sorted(by_date.items()):
        if not d1 <= day <= d2 or day in conflicts or row.get('daynum') == 0:
            continue
        rating, counter = row.get('rating'), row.get('comments')
        daily.append({
            'date': day,
            'rating': rating if type(rating) in (int, float) and 1 <= rating <= 5 else None,
            'provider_commentsvaluation': row.get('commentsvaluation') if marketplace == 'wb' else None,
            'provider_comments_counter': counter if type(counter) is int and counter >= 0 else None,
        })
    windows = [inspect_marketplace_history(
        marketplace=marketplace, sku=sku, d1=a, d2=b,
        comments=comments, period=period)['window'] for a, b in chunks]
    # The common adapter validates/deduplicates stable review IDs. Reuse it for
    # each non-overlapping chunk; never deduplicate anonymous same-day reviews.
    known = all(w['positive_text_record_count'] is not None for w in windows)
    records = [r for w in windows for r in w['review_records']] if known else None
    sample = None
    if records is not None:
        sample = {
            'records_received_in_period': len(records),
            'positive_4_5_records': sum(r['valuation'] >= 4 for r in records),
            'text_records': sum(r['has_text'] for r in records),
            'positive_text_records': sum(r['valuation'] >= 4 and r['has_text'] for r in records),
            'mean_received_rating': sum(r['valuation'] for r in records) / len(records) if records else None,
            'star_distribution': {str(s): sum(r['valuation'] == s for r in records) for s in range(1, 6)},
            'identities_verified': all('id' in r for r in records) if records else False,
            'scope': 'RECEIVED_RECORDS_NOT_ALL_PUBLICATIONS',
        }
    exact = {r['date']: r for r in daily}
    rating_rows = [r for r in daily if r['rating'] is not None]
    expected = (_date(d2) - _date(d1)).days + 1
    first, last = exact.get(d1), exact.get(d2)
    result = {
        'marketplace': marketplace, 'sku': sku, 'date_from': d1, 'date_to': d2,
        'source': 'MPSTATS ' + adapter.TOOL,
        'rating_metric': 'WB_RAW_RATING_MAY_BE_ROUNDED_SEE_COMMENTSVALUATION' if marketplace == 'wb' else 'OZON_RAW_RATING',
        'mode': 'HISTORICAL_SOURCE_QUERY_NOT_REGISTERED_EVENT_ANALYSIS',
        'source_date_timezone': 'PROVIDER_DATE_TIMEZONE_NOT_CONFIRMED',
        'calendar_days': expected, 'observed_days': len(daily),
        'rating_observed_days': len(rating_rows),
        'rating_daily_coverage_complete': len(rating_rows) == expected,
        'exact_start_snapshot': first, 'exact_end_snapshot': last,
        'first_available_snapshot': daily[0] if daily else None,
        'last_available_snapshot': daily[-1] if daily else None,
        'mean_observed_daily_rating': sum(r['rating'] for r in rating_rows) / len(rating_rows) if rating_rows else None,
        'rating_change': last['rating'] - first['rating'] if first and last and first['rating'] is not None and last['rating'] is not None else None,
        'received_review_sample': sample,
        'total_ratings': None, 'total_text_reviews': None,
        'new_positive_ratings': None, 'new_positive_text_reviews': None,
        'complete_publication_history': False, 'causal_effect_proven': False,
        'quality_flags': normalized['quality_flags'],
        'duplicate_dates': sorted(conflicts), 'daily': daily, 'windows': windows,
        'limitations': [
            'COMMENTS_COUNTER_NOT_VERIFIED_AS_SEPARATE_RATING_AND_TEXT_TOTALS',
            'CURRENT_REVIEW_SAMPLE_IS_NOT_PAST_STATE_INCLUDING_DELETED_OR_EDITED_REVIEWS',
            'SAMPLE_MEAN_AND_DAILY_RATING_MEAN_ARE_NOT_MARKETPLACE_RATING_FORMULA',
            'DATE_ONLY_SOURCE_CANNOT_ANSWER_INTRADAY_INTERVALS',
        ],
    }
    if isinstance(comments, dict) and type(comments.get('last_request')) in (int, float):
        result['comments_cache_updated_utc'] = datetime.fromtimestamp(comments['last_request'], timezone.utc).isoformat()
    return result


def query_history(reader, *, marketplace, sku, d1, d2, as_of, max_reads=24):
    """Bounded reads, exact windows, separate receipts. Quota read counts too."""
    adapter = source_adapter(marketplace)
    numeric = _sku(sku)
    chunks = list(date_chunks(d1, d2))
    if _date(d2) >= _date(as_of):
        raise ValueError('ONLY_COMPLETED_DAYS')
    if type(max_reads) is not int or not 1 <= max_reads <= 24:
        raise ValueError('INVALID_READ_BUDGET')
    if len(chunks) + 1 + reader.calls > max_reads:
        raise ValueError('CALL_BUDGET_RANGE_TOO_LARGE_SPLIT_QUERY')
    receipts = []
    def read(args):
        payload, state = reader.call(adapter.TOOL, {'sku': numeric, **args})
        digest = sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        receipts.append({'tool': adapter.TOOL, 'args': {'sku': numeric, **args},
                         'state': state, 'received_at_utc': datetime.now(timezone.utc).isoformat(),
                         'payload_sha256': digest})
        return payload if state in PASS else None
    comments = read({'report': 'comments'})
    rows = []
    for a, b in chunks:
        baseline = (_date(a) - timedelta(days=1)).isoformat()
        response = read({'report': 'by_period', 'd1': baseline, 'd2': b})
        if isinstance(response, list):
            # Each chunk's predecessor is the prior chunk's last day. Reuse the
            # first snapshot, avoiding fake duplicate conflicts across chunks.
            rows.extend(r for r in response if not isinstance(r, dict) or
                        (isinstance(r.get('data'), str) and
                         (a <= r['data'] <= b or (a == d1 and r['data'] == baseline))))
    result = summarize_history(marketplace=marketplace, sku=sku, d1=d1, d2=d2,
                               comments=comments, period=rows)
    result['source_receipts'] = receipts
    result['mpstats_calls'] = reader.calls
    return result


def format_history_ru(result):
    def snap(point):
        if not point:
            return 'нет наблюдения на точную дату'
        rating = str(point['rating']) + '★' if point['rating'] is not None else 'рейтинг неизвестен'
        return f"{point['date']}: {rating}; счётчик comments={point['provider_comments_counter']}"
    lines = [f"{result['marketplace'].upper()} {result['sku']}: {result['date_from']} — {result['date_to']}",
             'Источник: ' + result['source'] + '(by_period/comments).',
             'Начало: ' + snap(result['exact_start_snapshot']),
             'Конец: ' + snap(result['exact_end_snapshot']),
             f"Дней с рейтингом: {result['rating_observed_days']}/{result['calendar_days']}.",
             'Среднее доступных дневных рейтингов: ' + str(result['mean_observed_daily_rating']) + '.',
             'Это не средняя оценка новых отзывов и не формула рейтинга маркетплейса.']
    if result['marketplace'] == 'wb':
        lines.append('WB rating может быть округлён: не считать его точным дробным рейтингом. '
                     'Отдельное поле commentsvaluation на границах: ' +
                     str((result['exact_start_snapshot'] or {}).get('provider_commentsvaluation')) + ' → ' +
                     str((result['exact_end_snapshot'] or {}).get('provider_commentsvaluation')) + '.')
    sample = result['received_review_sample']
    if sample is None:
        lines.append('Выборка отзывов недоступна или конфликтует по ID.')
    else:
        lines.append(f"В полученной выборке за период: {sample['records_received_in_period']} записей, "
                     f"из них 4–5★: {sample['positive_4_5_records']}, с текстом: {sample['text_records']}, "
                     f"4–5★ с текстом: {sample['positive_text_records']}; средняя: {sample['mean_received_rating']}.")
    lines.append('Полное число оценок и текстовых отзывов отдельно: неизвестно. '
                 'Выборка неполная; разность comments не доказывает число новых публикаций. '
                 'Дата выкупа не доказывает дату публикации отзыва или причинный эффект.')
    return '\n'.join(lines)


def review_date_summary(history, *, review_date, own_review_ids=(), own_review_dates=()):
    """Stars-only view around registry review_date; never use purchase_date.

    Unknown ownership on a registered own-review day is quarantined rather than
    subtracting an arbitrary five-star record. Published card snapshots remain
    unchanged: the marketplace's weighted rating cannot be 'cleaned' by minus 5.
    """
    event = _date(review_date)
    if not _date(history['date_from']) < event <= _date(history['date_to']):
        raise ValueError('REVIEW_DATE_OUTSIDE_QUERY')
    own_dates = {_date(d).isoformat() for d in own_review_dates} | {review_date}
    own_ids = set(own_review_ids)
    if any(not isinstance(i, str) or not i for i in own_ids):
        raise ValueError('INVALID_OWN_REVIEW_ID')
    known = history['received_review_sample'] is not None
    buckets = {'before': [], 'after': [], 'own_identified': [], 'own_date_unresolved': []}
    if known:
        for window in history['windows']:
            for raw in window['review_records']:
                row = {k: raw[k] for k in ('date', 'valuation', 'id') if k in raw}
                if row.get('id') in own_ids:
                    buckets['own_identified'].append(row)
                elif row['date'] in own_dates:
                    buckets['own_date_unresolved'].append(row)
                elif row['date'] < review_date:
                    buckets['before'].append(row)
                else:
                    buckets['after'].append(row)
    def sample(rows):
        if not known:
            return None
        return {'received_count': len(rows),
                'stars': {str(s): sum(r['valuation'] == s for r in rows) for s in range(1, 6)},
                'mean_received_rating': sum(r['valuation'] for r in rows)/len(rows) if rows else None,
                'records': rows, 'complete_population_count': None}
    previous = (event - timedelta(days=1)).isoformat()
    points = {r['date']: r for r in history['daily']}
    return {
        'marketplace': history['marketplace'],
        'date_from': history['date_from'], 'date_to': history['date_to'],
        'registry_review_date': review_date,
        'own_rating_declared_by_owner': 5,
        'before_card_snapshot': points.get(previous),
        'latest_available_card_snapshot': history['last_available_snapshot'],
        'before_received_ratings': sample(buckets['before']),
        'after_received_ratings': sample(buckets['after']),
        'identified_own_reviews_excluded': sample(buckets['own_identified']),
        'own_date_records_not_attributed': sample(buckets['own_date_unresolved']),
        'complete_publication_history': False,
        'remaining_records_proven_independent': False,
        'card_rating_excludes_own_review': False,
        'text_required': False,
        'rule': 'EXACT_OWN_IDS_EXCLUDED_OTHER_RECORDS_ON_OWN_DATES_QUARANTINED',
    }


def format_review_date_summary_ru(result):
    lines = ['Дата собственного отзыва по реестру: ' + result['registry_review_date'] + '.',
             'Собственная оценка по указанию владельца: 5★; учитывается отдельно.']
    for key, label in [('before_card_snapshot', 'Рейтинг накануне'),
                       ('latest_available_card_snapshot', 'Последний доступный рейтинг')]:
        point = result[key]
        if not point:
            lines.append(label + ': нет наблюдения на нужную дату.')
            continue
        value = str(point['rating']) + '★' if point['rating'] is not None else 'неизвестен'
        lines.append(label + ': ' + value + ', дата — ' + point['date'] + '.')
        if result['marketplace'] == 'wb':
            lines.append('У Вайлдберриз это значение может быть округлено; отдельное дробное значение источника — ' +
                         str(point.get('provider_commentsvaluation')) + '.')
    lines.append('Период выборки: ' + result['date_from'] + ' — ' + result['date_to'] + '.')
    for key, label in [('before_received_ratings', 'До даты'), ('after_received_ratings', 'После даты')]:
        sample = result[key]
        if sample is None:
            lines.append(label + ': сведения об отдельных оценках недоступны.')
            continue
        stars = ', '.join(str(s) + '★ — ' + str(sample['stars'][str(s)]) for s in range(1, 6))
        mean = str(round(sample['mean_received_rating'], 3)) if sample['mean_received_rating'] is not None else 'не определена'
        lines.append(label + ': найдено ' + str(sample['received_count']) + ' оценок; ' + stars + '; средняя — ' + mean + '.')
    unresolved = result['own_date_records_not_attributed']
    if unresolved and unresolved['received_count']:
        lines.append('Записи в дни собственных отзывов отложены отдельно: ' + str(unresolved['received_count']) +
                     '. Без точного сопоставления нельзя выбрать среди них собственную пятёрку.')
    lines.append('Это статистика найденных записей, не гарантированно всех оценок. '
                 'Рейтинг на карточке показывается как есть: собственная оценка может участвовать в нём.')
    return '\n'.join(lines)
