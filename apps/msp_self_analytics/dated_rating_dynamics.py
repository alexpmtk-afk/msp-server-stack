"""Strict retrospective MPSTATS rating dynamics from verified dated aggregate series.

No IO and no MCP-field guesses. An upstream *verified* adapter must prove exact
provider time semantics. Rated 4-5 stars = total rated - rated 1-3 stars.
Textual positive reviews = reviews with text - negative reviews with text.
Daily additions and cumulative NET differences are never interchangeable.
Cumulative removals/moderation preclude claims about newly posted reviews.
Never infer a reviewer's identity or attribute changes to a registry event.
"""
from __future__ import annotations

from datetime import date, timedelta
from math import isfinite

REQUIRED=("ratings_total","ratings_negative","ratings_with_text",
          "ratings_negative_with_text")
KINDS=("DAILY_NEW_COUNTS","CUMULATIVE_SNAPSHOTS")
SOURCE="MPSTATS_VERIFIED_DATED_RATING_AGGREGATES"


def _as_date(value):
    if not isinstance(value,str):
        raise ValueError("DATE_REQUIRED")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("DATE_INVALID") from exc


def _value(entry):
    if not isinstance(entry,dict) or not all(x in entry for x in REQUIRED):
        raise ValueError("ALL_FOUR_RATING_COUNTERS_REQUIRED")
    vals={}
    for name in REQUIRED:
        v=entry[name]
        if type(v) is not int or v<0:
            raise ValueError("RATING_COUNTER_MUST_BE_NONNEGATIVE_INTEGER")
        vals[name]=v
    if (vals["ratings_negative"]>vals["ratings_total"]
            or vals["ratings_with_text"]>vals["ratings_total"]
            or vals["ratings_negative_with_text"]>min(
                vals["ratings_negative"],vals["ratings_with_text"])):
        raise ValueError("INCONSISTENT_RATING_COUNTS")
    vals["ratings_positive_4_5"]=vals["ratings_total"]-vals["ratings_negative"]
    vals["reviews_with_text_positive_4_5"]=(
        vals["ratings_with_text"]-vals["ratings_negative_with_text"])
    if vals["reviews_with_text_positive_4_5"]>vals["ratings_positive_4_5"]:
        raise ValueError("POSITIVE_TEXT_GREATER_THAN_POSITIVE_RATINGS")
    return vals


def _unknown(reason,source_kind=None):
    return {"status":"UNKNOWN","reason":reason,"source_kind":source_kind,
            "positive_ratings_4_5":None,"positive_reviews_with_text_4_5":None,"positive_ratings_without_text_4_5":None,
            "distinct_other_buyers_verified":False,"effect_proven":False}


def _analyze_rating_window(source,*,date_from,date_to,allow_signed_net=False):
    """Count positive 4-5 ratings AFTER event only with source-proved dates.

    For DAILY_NEW_COUNTS, every after-window date must be present exactly once.
    For CUMULATIVE_SNAPSHOTS, require snapshots on day before after_start and
    after_end. That result is explicitly NET count change, not new events.
    Unsupported source or missing days never implies zero positives.
    """
    first,last=map(_as_date,(date_from,date_to))
    if last<first or (last-first).days>=90:
        raise ValueError("RATING_WINDOW_INVALID")
    if not isinstance(source,dict):
        return _unknown("DATED_SOURCE_NOT_AVAILABLE")
    if (source.get("status")!="VERIFIED_DATED_SOURCE"
            or source.get("source_kind")!=SOURCE
            or not isinstance(source.get("source_ref"),str)
            or not source.get("source_ref").strip()
            or source.get("date_granularity")!="DAY"
            or source.get("rating_scale")!="FIVE_STAR"
            or source.get("negative_stars")!=[1,2,3]):
        return _unknown("SOURCE_CONTRACT_NOT_VERIFIED")
    kind=source.get("series_kind")
    if kind not in KINDS:return _unknown("SERIES_KIND_UNVERIFIED")
    rows=source.get("rows")
    if not isinstance(rows,list) or len(rows)>1000:
        return _unknown("DATED_ROWS_UNAVAILABLE_OR_LIMIT")
    points={}
    try:
        for row in rows:
            if not isinstance(row,dict):return _unknown("MALFORMED_DAILY_ITEM",kind)
            d=_as_date(row.get("date"))
            if d in points:return _unknown("DUPLICATE_DATED_ITEM",kind)
            points[d]=_value(row)
    except ValueError as e:
        return _unknown(str(e),kind)
    if kind=="DAILY_NEW_COUNTS":
        current=first
        positive=positive_text=0
        while current<=last:
            vals=points.get(current)
            if vals is None:
                return _unknown("MISSING_CALENDAR_DATE",kind)
            positive+=vals["ratings_positive_4_5"]
            positive_text+=vals["reviews_with_text_positive_4_5"]
            current+=timedelta(days=1)
        return {
            "status":"DAILY_POSITIVE_COUNTS_OBSERVED",
            "date_from":first.isoformat(),"date_to":last.isoformat(),
            "completed_days":(last-first).days+1,
            "source_kind":kind,"positive_ratings_4_5":positive,
            "positive_reviews_with_text_4_5":positive_text,
            "positive_ratings_without_text_4_5":positive-positive_text,
            "net_change_only":False,
            "distinct_other_buyers_verified":False,"effect_proven":False,
            "provider_counts_not_independent_publication_proof":True,
        }
    baseline=points.get(first-timedelta(days=1))
    end=points.get(last)
    if baseline is None or end is None:
        return _unknown("BASELINE_OR_END_SNAPSHOT_MISSING",kind)
    dtotal=end["ratings_total"]-baseline["ratings_total"]
    dnegative=end["ratings_negative"]-baseline["ratings_negative"]
    dtext=end["ratings_with_text"]-baseline["ratings_with_text"]
    dnegative_text=end["ratings_negative_with_text"]-baseline["ratings_negative_with_text"]
    diffs=(dtotal,dnegative,dtext,dnegative_text)
    if not allow_signed_net and any(v<0 for v in diffs):
        return _unknown("CUMULATIVE_COUNTER_DECREASE_OR_MODERATION",kind)
    dpos=dtotal-dnegative
    dpositive_text=dtext-dnegative_text
    if not allow_signed_net and (dpos<0 or dpositive_text<0 or dpositive_text>dpos):
        return _unknown("CUMULATIVE_SUBCOUNTER_CHANGES_INCONSISTENT",kind)
    return {
        "status":"NET_RATING_COUNT_CHANGE_ONLY",
        "date_from":first.isoformat(),"date_to":last.isoformat(),
        "completed_days":(last-first).days+1,
        "source_kind":kind,"positive_ratings_4_5":dpos,
        "positive_reviews_with_text_4_5":dpositive_text,
        "positive_ratings_without_text_4_5":dpos-dpositive_text,
        "net_change_only":True,
        "distinct_other_buyers_verified":False,"effect_proven":False,
        "provider_counts_not_independent_publication_proof":True,
    }


def analyze_dated_positive_ratings(source,*,event_date,after_start,after_end):
    """Backward-compatible AFTER gate; legacy moderation rejection preserved."""
    t,first,last=map(_as_date,(event_date,after_start,after_end))
    if first<=t or last<first or last>t+timedelta(days=90):
        raise ValueError("AFTER_WINDOW_INVALID")
    return _analyze_rating_window(source,date_from=after_start,date_to=after_end)


def compare_dated_rating_periods(source,*,event_date,before_start,before_end,
                                 after_start,after_end):
    """One VERIFIED source/series kind for equal windows; never mix daily and net.

    The registered event is excluded. The caller supplies the established
    first-series baseline and next-event-censored completed windows.
    Cumulative deltas may be negative: deletions are net changes, not new events.
    Canonical names here are an INTERNAL contract, not invented MCP fields.
    """
    t,b1,b2,a1,a2=map(_as_date,(event_date,before_start,before_end,after_start,after_end))
    if not b1<=b2<t<a1<=a2 or (b2-b1)!=(a2-a1) or (a2-a1).days>=90:
        raise ValueError("EQUAL_COMPLETED_WINDOWS_REQUIRED")
    before=_analyze_rating_window(source,date_from=before_start,date_to=before_end,allow_signed_net=True)
    after=_analyze_rating_window(source,date_from=after_start,date_to=after_end,allow_signed_net=True)
    ready={'DAILY_POSITIVE_COUNTS_OBSERVED','NET_RATING_COUNT_CHANGE_ONLY'}
    comparable=(before['status'] in ready and after['status']==before['status'])
    fields=('positive_ratings_4_5','positive_reviews_with_text_4_5','positive_ratings_without_text_4_5')
    return {'status':'COMPARABLE_DAILY_COUNTS' if comparable and not before['net_change_only'] else
                     'COMPARABLE_NET_CHANGES' if comparable else 'PARTIAL_OR_UNKNOWN',
            'before':before,'after':after,
            'change':{f:after[f]-before[f] if comparable else None for f in fields},
            'source_ref':source.get('source_ref') if isinstance(source,dict) else None,
            'independent_buyers_verified':False,'causal_effect_proven':False}


def format_dated_positive_ratings_ru(result):
    if not isinstance(result,dict):
        raise ValueError("RESULT_REQUIRED")
    state=result.get("status")
    if state=="DAILY_POSITIVE_COUNTS_OBSERVED":
        return (
            "После зарегистрированной даты отзыва MPSTATS: "
            f'{result["positive_ratings_4_5"]} положительных оценок 4–5★, '
            f'{result["positive_reviews_with_text_4_5"]} из них с текстом '
            "за полностью наблюдаемые даты. "
            "Не установлено, какие оценки относятся к независимым покупателям; "
            "это не доказательство эффекта исходного отзыва."
        )
    if state=="NET_RATING_COUNT_CHANGE_ONLY":
        return (
            "После зарегистрированной даты отзыва MPSTATS: чистое изменение "
            f'числа положительных оценок 4–5★ = {result["positive_ratings_4_5"]}, '
            f'с текстовыми отзывами = {result["positive_reviews_with_text_4_5"]}. '
            "Это разница накопительных счётчиков, а не точное число "
            "новых опубликованных оценок; удаления/модерация могут влиять."
        )
    return (
        "Новые положительные оценки после зарегистрированной даты отзыва: "
        "неизвестно — нет подтверждённого полного датированного ряда MPSTATS."
    )
