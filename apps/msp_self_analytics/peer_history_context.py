"""Read-only descriptive MPSTATS history for *unverified* marketplace peers.

Never turn algorithmic "similar" listings into a matched control group.
This module makes no network calls or writes and reports no identifying SKU,
product name, price, ad spend, incremental revenue, ROI or review causality.
"""
from __future__ import annotations

from datetime import date, timedelta
from math import isfinite


def _window_pair(report):
    windows=report.get("date_windows")
    if not isinstance(windows,dict):raise ValueError("WINDOWS_REQUIRED")
    a,b=windows.get("before"),windows.get("after")
    if not isinstance(a,dict) or not isinstance(b,dict):
        raise ValueError("WINDOWS_REQUIRED")
    try:
        x1,x2=date.fromisoformat(a["d1"]),date.fromisoformat(a["d2"])
        y1,y2=date.fromisoformat(b["d1"]),date.fromisoformat(b["d2"])
    except (KeyError,TypeError,ValueError) as exc:
        raise ValueError("INVALID_WINDOWS") from exc
    n1,n2=(x2-x1).days+1,(y2-y1).days+1
    if not 1<=n1<=90 or n1!=n2 or y1!=x2+timedelta(days=2):
        raise ValueError("WINDOWS_NOT_EQUAL_OR_REVIEW_DAY_NOT_EXCLUDED")
    if report.get("window_days")!=n1 or report.get("review_day_excluded") is not True:
        raise ValueError("WINDOW_INTEGRITY_NOT_CONFIRMED")
    return n1,{"before":a,"after":b}


def _measure(value, days):
    if not isinstance(value,dict) or value.get("quality")!="OBSERVATIONAL_MPSTATS":
        return None
    if value.get("state") not in ("PASS_STRUCTURED","PASS_JSON"):
        return None
    count,stock=value.get("estimated_orders"),value.get("days_in_stock")
    if type(count) not in (int,float) or not isfinite(count) or count<0:
        return None
    if type(stock) not in (int,float) or not isfinite(stock) or not 0<stock<=days:
        return None
    return {"estimated_orders":count,"days_in_stock":stock,
            "orders_per_stock_day":count/stock,"small_sample":count<10}


def _pair(row,days):
    if not isinstance(row,dict):return {"status":"UNKNOWN_WINDOW_DATA"}
    before,after=_measure(row.get("before"),days),_measure(row.get("after"),days)
    if before is None or after is None:return {"status":"UNKNOWN_WINDOW_DATA"}
    base=before["orders_per_stock_day"]
    return {"status":"PROVIDER_ESTIMATE_DESCRIPTIVE",
            "before":before,"after":after,
            "rate_change_percent":100*(after["orders_per_stock_day"]/base-1) if base>0 else None,
            "small_sample":before["small_sample"] or after["small_sample"],
            "causal_change_proven":False}


def summarize_peer_history(report):
    """Accept only complete equal-window observations, never approve comparators."""
    if not isinstance(report,dict):raise ValueError("REPORT_REQUIRED")
    days,windows=_window_pair(report)
    if report.get("verified_comparators")!=0 or report.get("eligible_causal_controls")!=0:
        raise ValueError("VERIFIED_CONTROL_NOT_ESTABLISHED_BY_THIS_MODULE")
    rows=report.get("candidates")
    if not isinstance(rows,list) or len(rows)>8:raise ValueError("CANDIDATES_INVALID")
    candidates=[]
    for n,c in enumerate(rows,1):
        if not isinstance(c,dict) or c.get("verified_comparator") is not False or c.get("used_as_causal_control") is not False:
            raise ValueError("CANDIDATE_VERIFICATION_UNSUPPORTED")
        observed=_pair(c,days)
        candidates.append({"candidate_number":n,"source_relation":c.get("source_relation"),
                           "metrics":observed,"comparable_product_verified":False})
    own=_pair(report.get("own"),days)
    usable=sum(c["metrics"]["status"]=="PROVIDER_ESTIMATE_DESCRIPTIVE" for c in candidates)
    return {"status":"EXPLORATORY_CANDIDATE_CONTEXT_ONLY" if usable and own["status"]=="PROVIDER_ESTIMATE_DESCRIPTIVE"
            else "PARTIAL_CONTEXT_UNKNOWN",
            "window_days":days,"windows":windows,
            "own":own,"candidate_count":len(candidates),"candidate_histories_with_data":usable,
            "candidates":candidates,"verified_comparators":0,
            "qualified_control_group":False,"causal_review_effect_proven":False,
            "economics_from_peer_change_allowed":False,
            "mpstats_values_are_estimates":True}


def format_peer_history_ru(context):
    """Short Russian narrative with evidence labels and no extrapolated ROI."""
    if not isinstance(context,dict):raise ValueError("CONTEXT_REQUIRED")
    def rate(x):return f'{x["orders_per_stock_day"]:.3f}'.replace(".",",")
    def summary(x):
        if x.get("status")!="PROVIDER_ESTIMATE_DESCRIPTIVE":
            return "за два периода подтверждённой статистики нет."
        a,b=x["before"],x["after"]
        units=lambda v: f"{v:g}".replace(".",",")
        change=x["rate_change_percent"]
        percent=("процент не рассчитывается от нуля" if change is None
                 else f"{change:+.1f}%".replace(".",","))
        msg=(f'оценочные заказы {units(a["estimated_orders"])} → {units(b["estimated_orders"])}; '
             f'на день наличия {rate(a)} → {rate(b)} ({percent}).')
        if x["small_sample"]:
            msg+=" Малая выборка (<10 заказов хотя бы в одном периоде)."
        return msg
    lines=["ПРЕДВАРИТЕЛЬНЫЙ РЫНОЧНЫЙ КОНТЕКСТ MPSTATS, не контрольная группа.",
           "Сравнение одинаковых завершённых периодов по "+
           str(context.get("window_days","?"))+" дней ДО и ПОСЛЕ даты отзыва.",
           "Собственный товар: "+summary(context.get("own") or {})]
    for row in context.get("candidates") or []:
        lines.append("Предварительный кандидат №"+str(row["candidate_number"])+": "+
                     summary(row["metrics"]))
    lines.append(
        "Сопоставимость товаров не подтверждена. "
        "Показатели MPSTATS оценочные; их изменения не доказывают влияние "
        "отзыва или самовыкупа, органические оплаченные продажи и окупаемость.")
    return "\n".join(lines)
