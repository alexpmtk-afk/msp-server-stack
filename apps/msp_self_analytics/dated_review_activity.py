"""Strict source-gated daily review activity as a partial, nonfinancial signal.

In the MPSTATS seller-card daily table, 'new reviews per day' and
'average rating per day' may be present without the distribution of 1–5
stars. They are not evidence for an exact count of 4–5-star reviews.
This module does not guess an MCP response schema or perform IO.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation


SOURCE="MPSTATS_VERIFIED_DAILY_REVIEW_ACTIVITY"


def _date(s):
    if not isinstance(s,str):
        raise ValueError("INVALID_DATE")
    try:
        return date.fromisoformat(s)
    except ValueError as e:
        raise ValueError("INVALID_DATE") from e


def _unknown(reason):
    return {"status":"UNKNOWN","reason":reason,"total_new_reviews":None,
            "weighted_average_rating":None,"positive_4_5_reviews":None,
            "independent_reviewers_verified":False,"causal_effect_proven":False}


def analyze_daily_review_activity(source,*,event_date,after_start,after_end):
    """Require every full date after the event; never infer positive share."""
    t,first,last=map(_date,(event_date,after_start,after_end))
    if first<=t or last<first or last>t+timedelta(days=90):
        raise ValueError("AFTER_WINDOW_INVALID")
    if not isinstance(source,dict):
        return _unknown("SOURCE_UNAVAILABLE")
    if (source.get("status")!="VERIFIED_DATED_SOURCE"
            or source.get("source_kind")!=SOURCE
            or not isinstance(source.get("source_ref"),str)
            or not source.get("source_ref").strip()
            or source.get("series_kind")!="DAILY_NEW_REVIEW_COUNTS"
            or source.get("date_granularity")!="DAY"
            or source.get("rating_scale")!="FIVE_STAR"):
        return _unknown("SOURCE_SEMANTICS_NOT_VERIFIED")
    rows=source.get("rows")
    if not isinstance(rows,list) or len(rows)>1000:
        return _unknown("DATED_ROWS_UNAVAILABLE")
    points={}
    for row in rows:
        if not isinstance(row,dict):
            return _unknown("MALFORMED_ROW")
        try:
            d=_date(row.get("date"))
        except ValueError:
            return _unknown("INVALID_ROW_DATE")
        if d in points:
            return _unknown("DUPLICATE_DATE")
        n=row.get("new_reviews")
        if type(n) is not int or n<0:
            return _unknown("INVALID_NEW_REVIEWS_COUNTER")
        mean=row.get("average_rating")
        if n==0:
            if mean not in (None,0,"0"):
                return _unknown("AVERAGE_WITHOUT_REVIEWS")
            points[d]=(0,None)
        else:
            if type(mean) not in (int,float,str,Decimal):
                return _unknown("AVERAGE_RATING_UNAVAILABLE")
            try:
                stars=Decimal(str(mean))
            except (InvalidOperation,ValueError):
                return _unknown("AVERAGE_RATING_INVALID")
            if not stars.is_finite() or not Decimal(1)<=stars<=Decimal(5):
                return _unknown("AVERAGE_RATING_OUT_OF_SCALE")
            points[d]=(n,stars)
    total=0
    weighted=Decimal(0)
    d=first
    while d<=last:
        if d not in points:
            return _unknown("MISSING_CALENDAR_DATE")
        n,avg=points[d]
        total+=n
        if avg is not None:
            weighted+=n*avg
        d+=timedelta(days=1)
    return {
        "status":"DAILY_REVIEW_ACTIVITY_OBSERVED",
        "date_from":first.isoformat(),"date_to":last.isoformat(),
        "complete_days":(last-first).days+1,
        "total_new_reviews":total,
        "weighted_average_rating":str((weighted/total).quantize(Decimal("0.01")))
                                   if total>0 else None,
        "positive_4_5_reviews":None,
        "positive_distribution_available":False,
        "independent_reviewers_verified":False,
        "causal_effect_proven":False,
        "provider_activity_not_publication_proof":True,
    }


def format_daily_review_activity_ru(result):
    if not isinstance(result,dict):
        raise ValueError("ACTIVITY_RESULT_REQUIRED")
    if result.get("status")!="DAILY_REVIEW_ACTIVITY_OBSERVED":
        return ("Число новых отзывов по дням: неизвестно — подтверждённый "
                "датированный ряд источника недоступен.")
    count=result["total_new_reviews"]
    rating=result["weighted_average_rating"]
    suffix=("; средняя оценка по дневным данным MPSTATS ≈ "+
            rating.replace(".",",")+"★") if rating is not None else ""
    return (
        f"Новые отзывы по дневной аналитике MPSTATS: {count}{suffix}. "
        "Точное число положительных отзывов 4–5★ из общего числа неизвестно: "
        "дневная средняя оценка не раскрывает распределение по звёздам. "
        "Независимое происхождение публикаций и причинный эффект не подтверждены."
    )
