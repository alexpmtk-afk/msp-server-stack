"""Strict observational evidence from read-only external MPSTATS WB tools.

wb_sku(report=keywords) returns data.words and data.dates. The historical
client_price series is provider-labelled only: NOT verified buyer transaction
price and NOT evidence of seller price corrections. Shelf "visibility_count"
means host-card-days, NOT human impressions. No spend/ROI/causal claims.
No network requests, database writes or marketplace operations.
"""
from __future__ import annotations
from datetime import date
from math import isfinite
import re

_DATE=re.compile(r"\d{4}-\d{2}-\d{2}\Z")


def _day(value):
    if not isinstance(value,str) or not _DATE.fullmatch(value):return None
    try:return date.fromisoformat(value)
    except ValueError:return None


def _positive(value):
    if type(value) not in (int,float) or not isfinite(value) or value<=0:return None
    return value


def analyze_keyword_history(payload, *, d1:str, d2:str) -> dict:
    """Keep measured days and gaps; never interpolate unobserved prices."""
    first,last=_day(d1),_day(d2)
    if first is None or last is None or last<first:
        raise ValueError("INVALID_DATE_WINDOW")
    total=(last-first).days+1
    result={
        "status":"UNVERIFIED_KEYWORD_RESPONSE",
        "source":"MPSTATS_WB_SKU_KEYWORDS",
        "window":{"d1":d1,"d2":d2,"days":total},
        "returned_word_rows":None,
        "provider_reported_total_words":None,
        "all_word_rows_received":False,
        "word_day_entries":None,
        "word_distinct_days":None,
        "daily_observed_days":None,
        "daily_client_price_positive_days":None,
        "daily_client_price_coverage_percent":None,
        "observed_client_price_levels":None,
        "observed_price_transitions":[],
        "unobserved_calendar_days":None,
        "client_price_type":"UNVERIFIED_MPSTATS_HISTORICAL_CLIENT_PRICE",
        "verified_buyer_paid_price":False,
        "seller_price_corrections_inferred":False,
        "unknown_days_not_zero":True,
        "advertising_spend_verified":False,
        "effect_attribution_allowed":False,
    }
    if not isinstance(payload,dict):return result
    body=payload.get("data")
    if not isinstance(body,dict):return result
    words=body.get("words")
    daily=body.get("dates")
    if not isinstance(words,list) or not isinstance(daily,dict):return result
    word_total=payload.get("total")
    result["provider_reported_total_words"]=word_total if type(word_total) is int and word_total>=0 else None
    result["returned_word_rows"]=len(words)
    result["all_word_rows_received"]=(result["provider_reported_total_words"] is not None
                                     and len(words)==result["provider_reported_total_words"])
    unique=set()
    points=0
    for row in words:
        if not isinstance(row,dict):continue
        dates=row.get("dates")
        if not isinstance(dates,dict):continue
        for stamp,val in dates.items():
            day=_day(stamp)
            if day is None or not first<=day<=last or not isinstance(val,dict):continue
            points+=1
            unique.add(stamp)
    result["word_day_entries"]=points
    result["word_distinct_days"]=len(unique)
    observed=set(); prices=[]
    for stamp,row in daily.items():
        day=_day(stamp)
        if day is None or not first<=day<=last or not isinstance(row,dict):continue
        observed.add(stamp)
        price=_positive(row.get("client_price"))
        if price is not None:prices.append((day,price))
    prices.sort()
    result["daily_observed_days"]=len(observed)
    result["daily_client_price_positive_days"]=len(prices)
    result["daily_client_price_coverage_percent"]=round(100*len(prices)/total,2)
    result["unobserved_calendar_days"]=total-len(observed)
    result["observed_client_price_levels"]=len({v for _,v in prices})
    transitions=[]
    for (previous_date,previous),(new_date,new) in zip(prices,prices[1:]):
        if previous==new:continue
        transitions.append({
            "previous_observed_date":previous_date.isoformat(),
            "new_observed_date":new_date.isoformat(),
            "previous_client_price":previous,
            "new_client_price":new,
            "observed_price_delta":new-previous,
            "calendar_days_between_observations":(new_date-previous_date).days,
            "actual_seller_edit_date_verified":False,
        })
    result["observed_price_transitions"]=transitions
    # A partial keyword page is not a fully verified history, even when
    # the daily prices that arrived have valid dates and values.
    result["status"]=("OBSERVED_SPARSE_PROVIDER_HISTORY"
                      if result["all_word_rows_received"]
                      else "PARTIAL_KEYWORD_PAGINATION")
    return result


def compare_shelf_visibility(stats,items,*,d1:str,d2:str) -> dict:
    """Distinct counts: aggregate host-days vs detailed host/date positions."""
    first,last=_day(d1),_day(d2)
    if first is None or last is None or last<first:
        raise ValueError("INVALID_DATE_WINDOW")
    out={
        "status":"UNVERIFIED_SHELF_RESPONSE",
        "source":"MPSTATS_WB_SHELVES",
        "aggregate_visibility_count":None,
        "aggregate_host_cards":None,
        "detail_host_cards":None,
        "detail_host_date_entries":None,
        "detail_observed_days":None,
        "detail_paid_position_entries":None,
        "aggregate_detail_discrepancy":None,
        "aggregate_count_equals_human_impressions":False,
        "paid_marker_equals_seller_ad_spend":False,
        "host_sales_are_own_sku_orders":False,
        "causal_inference_allowed":False,
    }
    if not isinstance(stats,dict) or not isinstance(items,dict):return out
    rows=items.get("data")
    if not isinstance(rows,list):return out
    reported=items.get("total")
    if type(reported) is not int or reported!=len(rows):
        out["status"]="DETAIL_PAGINATION_INCOMPLETE"
        return out
    a=stats.get("visibility_count")
    hosts=stats.get("items")
    out["aggregate_visibility_count"]=a if type(a) is int and a>=0 else None
    out["aggregate_host_cards"]=hosts if type(hosts) is int and hosts>=0 else None
    out["detail_host_cards"]=len(rows)
    total=0;paid=0;days=set()
    for row in rows:
        if not isinstance(row,dict):continue
        positions=row.get("positions")
        if not isinstance(positions,dict):continue
        for stamp,observation in positions.items():
            day=_day(stamp)
            if day is None or not first<=day<=last or not isinstance(observation,dict):continue
            total+=1;days.add(stamp)
            if type(observation.get("ads")) in (int,float) and observation["ads"]==1:paid+=1
    out["detail_host_date_entries"]=total
    out["detail_observed_days"]=len(days)
    out["detail_paid_position_entries"]=paid
    if out["aggregate_visibility_count"] is not None:
        out["aggregate_detail_discrepancy"]=out["aggregate_visibility_count"]-total
    out["status"]=("OBSERVED_AGGREGATE_DETAIL_MISMATCH"
                   if out["aggregate_detail_discrepancy"] not in (None,0)
                   else "OBSERVED_DETAIL_EVIDENCE")
    return out


def format_keyword_price_observations_ru(before:dict,after:dict,*,max_changes:int=12) -> str:
    """Separate external provider client_price observations from seller price edits.

    The *dates* are observation timestamps; a price difference between
    consecutive observed dates is NOT proof the seller edited on either date.
    """
    if type(max_changes) is not int or not 0<=max_changes<=20:
        raise ValueError("INVALID_MAX_CHANGES")
    if not isinstance(before,dict) or not isinstance(after,dict):
        return "MPSTATS: датированная история client_price не подтверждена."
    if any(x.get("status")=="PARTIAL_KEYWORD_PAGINATION" for x in (before,after)):
        return ("MPSTATS: неполная постраничная выдача поисковых данных "
                "(total не подтверждён или не совпадает с числом строк). "
                "Нельзя считать историю client_price полной и сравнивать её как подтверждённую.")
    if any(x.get("status")!="OBSERVED_SPARSE_PROVIDER_HISTORY" for x in (before,after)):
        return "MPSTATS: датированная история client_price недоступна по обоим проверяемым окнам."
    result=[
        "MPSTATS (внешняя аналитика, без рекламного кабинета):",
        "  Дней с наблюдением client_price: "+
        str(before["daily_client_price_positive_days"])+"/"+
        str(before["window"]["days"])+" ДО → "+
        str(after["daily_client_price_positive_days"])+"/"+
        str(after["window"]["days"])+" ПОСЛЕ.",
        "  Различных значений client_price на наблюдаемых днях: "+
        str(before["observed_client_price_levels"])+" ДО → "+
        str(after["observed_client_price_levels"])+" ПОСЛЕ.",
        "  Переходов между различающимися наблюдаемыми значениями: "+
        str(len(before["observed_price_transitions"]))+" ДО → "+
        str(len(after["observed_price_transitions"]))+" ПОСЛЕ.",
    ]
    for event in after["observed_price_transitions"][:max_changes]:
        result.append("  MPSTATS client_price ПОСЛЕ: "+
            event["previous_observed_date"]+" ("+
            str(event["previous_client_price"])+") → "+
            event["new_observed_date"]+" ("+
            str(event["new_client_price"])+"); разница наблюдений "+
            str(event["observed_price_delta"])+
            " (не подтверждённая дата корректировки продавца).")
    extra=len(after["observed_price_transitions"])-max_changes
    if extra>0:
        result.append("  Дополнительно "+str(extra)+" переходов в наблюдениях; "+
            "полный список не показан в кратком отчёте.")
    result.append(
        "  ВНИМАНИЕ: client_price — поле внешней аналитики MPSTATS, "+
        "его точный вид цены и единицы ещё не подтверждены. "+
        "Пропущенные дни не заполнялись. Нельзя приписывать изменения "+
        "заказов самовыкупу или считать переходы client_price "+
        "изменениями цены продавца из журнала МСП.")
    return "\n".join(result)
