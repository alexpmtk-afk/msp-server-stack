"""Non-monetary, historical observation gates for existing MСП checkpoints.

All observations are descriptive: MPSTATS estimated orders are not independently
verified paid/organic sales, dated published review history is not established,
and no gain may be attributed to a registered self-purchase or review.
No IO, no marketplace/SQLite interactions and no inferred review actions.
"""
from __future__ import annotations
from math import isfinite

try:
    from apps.msp_self_analytics.dated_rating_dynamics import (
        analyze_dated_positive_ratings, format_dated_positive_ratings_ru)
except ModuleNotFoundError:
    from dated_rating_dynamics import (
        analyze_dated_positive_ratings, format_dated_positive_ratings_ru)
try:
    from apps.msp_self_analytics.dated_review_activity import (
        analyze_daily_review_activity, format_daily_review_activity_ru)
except ModuleNotFoundError:
    from dated_review_activity import (
        analyze_daily_review_activity, format_daily_review_activity_ru)


def _numeric(value):
    return type(value) in (int,float) and isfinite(value)


def summarize_nonfinancial_outcome(
    history, price_history, *, dated_rating_sources=None,
    dated_review_activity_sources=None,
):
    if not isinstance(history,dict) or not isinstance(history.get("checkpoints"),list):
        raise ValueError("HISTORY_REQUIRED")
    if not isinstance(price_history,dict):
        raise ValueError("PRICE_HISTORY_REQUIRED")
    prices={cp.get("checkpoint_number"):cp
            for cp in price_history.get("checkpoints",[])
            if isinstance(cp,dict)}
    if dated_rating_sources is not None and not isinstance(dated_rating_sources,dict):
        raise ValueError("DATED_RATING_SOURCES_MAPPING_REQUIRED")
    dated_rating_sources=dated_rating_sources or {}
    if (dated_review_activity_sources is not None
            and not isinstance(dated_review_activity_sources,dict)):
        raise ValueError("DATED_REVIEW_ACTIVITY_MAPPING_REQUIRED")
    dated_review_activity_sources=dated_review_activity_sources or {}
    outcomes=[]
    for cp in history["checkpoints"]:
        number=cp.get("checkpoint_number")
        status="UNKNOWN_SOURCE_OR_WINDOW"
        relative_change=None
        small_sample=None
        normalized=cp.get("stock_normalized_orders")
        if isinstance(normalized,dict) and normalized.get("status") in ("READY_DESCRIPTIVE","READY_LOW_SAMPLE"):
            before=normalized.get("orders_per_in_stock_day_before")
            after=normalized.get("orders_per_in_stock_day_after")
            if (_numeric(before) and before>=0 and _numeric(after) and after>=0):
                status=("OBSERVED_RATE_UP" if after>before else
                        "OBSERVED_RATE_DOWN" if after<before else
                        "OBSERVED_RATE_UNCHANGED")
                relative_change=normalized.get("rate_percent_change")
                small_sample=bool(normalized.get("small_observed_sample"))
                if not _numeric(relative_change):
                    relative_change=None
        price=prices.get(number)
        if price is None or price_history.get("status")=="UNKNOWN_PRICE_HISTORY":
            price_context="PRICE_HISTORY_UNKNOWN"
        elif price.get("after_window_price_events"):
            price_context="SELLER_PRICE_EDITS_IN_AFTER_WINDOW"
        else:
            price_context="NO_EDIT_RECORDED_BUT_BUYER_PRICE_UNKNOWN"
        # Only an upstream independently validated dated provider adapter
        # may populate this optional map. Without it the count stays UNKNOWN.
        rating_evidence=None
        window=cp.get("windows")
        if (number in dated_rating_sources and isinstance(window,dict)
                and isinstance(window.get("after"),dict)):
            period=window["after"]
            rating_evidence=analyze_dated_positive_ratings(
                dated_rating_sources[number],event_date=cp["review_date"],
                after_start=period["d1"],after_end=period["d2"])
        review_activity=None
        if (number in dated_review_activity_sources and isinstance(window,dict)
                and isinstance(window.get("after"),dict)):
            period=window["after"]
            review_activity=analyze_daily_review_activity(
                dated_review_activity_sources[number],
                event_date=cp["review_date"],
                after_start=period["d1"],after_end=period["d2"])
        rating_state=(
            "DAILY_MPSTATS_POSITIVE_RATINGS_OBSERVED"
            if isinstance(rating_evidence,dict)
            and rating_evidence.get("status")=="DAILY_POSITIVE_COUNTS_OBSERVED"
            else "NET_CUMULATIVE_RATINGS_CHANGE_NOT_NEW_PUBLICATIONS"
            if isinstance(rating_evidence,dict)
            and rating_evidence.get("status")=="NET_RATING_COUNT_CHANGE_ONLY"
            else "UNKNOWN_NO_VERIFIED_DATED_SOURCE")
        outcomes.append({
            "checkpoint_number":number,"reported_review_date":cp.get("review_date"),
            "order_signal":status,
            "normalized_rate_change_percent":relative_change,
            "small_estimated_order_sample":small_sample,
            "seller_price_context":price_context,
            "new_positive_public_reviews_status":rating_state,
            "dated_rating_provider_observation":rating_evidence,
            "dated_review_activity_observation":review_activity,
            "new_other_public_reviews_status":"UNKNOWN_NO_VERIFIED_DATED_SOURCE",
            "historical_rating_change_status":"UNKNOWN_NO_VERIFIED_DATED_SOURCE",
            "review_publication_verified":False,
            "organic_paid_order_change_verified":False,
            "advertising_contribution_verified":False,
            "verified_market_control_group":False,
            "causal_effect_proven":False,
            "monetary_roi_status":"DEFERRED_NO_FINANCIAL_INPUTS",
        })
    return {"status":"OBSERVATIONAL_NONFINANCIAL_ONLY",
            "checkpoint_count":len(outcomes),"checkpoints":outcomes,
            "confirmed_historical_positive_review_counts":None,
            "confirmed_historical_positive_review_count_is_zero":False,
            "any_causal_success_proven":False,
            "monetary_finance_requested":False}


def format_nonfinancial_outcome_ru(summary):
    if not isinstance(summary,dict) or not isinstance(summary.get("checkpoints"),list):
        raise ValueError("NONFINANCIAL_SUMMARY_REQUIRED")
    lines=["ПРЕДВАРИТЕЛЬНАЯ НЕСТОИМОСТНАЯ ОЦЕНКА (описательная, без денежной окупаемости)."]
    trend={
        "OBSERVED_RATE_UP":"наблюдался рост оценочных заказов на день наличия",
        "OBSERVED_RATE_DOWN":"наблюдалось снижение оценочных заказов на день наличия",
        "OBSERVED_RATE_UNCHANGED":"интенсивность оценочных заказов не изменилась",
        "UNKNOWN_SOURCE_OR_WINDOW":"достоверных сопоставимых данных за оба окна недостаточно",
    }
    for cp in summary["checkpoints"]:
        result=trend.get(cp["order_signal"],trend["UNKNOWN_SOURCE_OR_WINDOW"])
        line=("Контроль "+str(cp["checkpoint_number"])+": "+result)
        val=cp.get("normalized_rate_change_percent")
        if _numeric(val):
            line+=" ("+f"{val:+.1f}".replace(".",",")+"%)"
        else:
            line+="; процентное изменение не установлено"
        if cp.get("small_estimated_order_sample"):
            line+=". Малая выборка: относительная динамика неустойчива"
        if cp["seller_price_context"]=="SELLER_PRICE_EDITS_IN_AFTER_WINDOW":
            line+=". После даты отзыва зафиксирована корректировка цены продавца"
        elif cp["seller_price_context"]=="PRICE_HISTORY_UNKNOWN":
            line+=". История цен продавца неполна"
        lines.append(line+".")
        if cp.get("dated_review_activity_observation") is not None:
            lines.append("  "+format_daily_review_activity_ru(
                cp["dated_review_activity_observation"]))
        if cp.get("dated_rating_provider_observation") is not None:
            lines.append("  "+format_dated_positive_ratings_ru(
                cp["dated_rating_provider_observation"]))
            lines.append("  Изменение совокупного рейтинга: неизвестно.")
        else:
            lines.append(
                "  Новые положительные оценки/отзывы после даты отзыва: неизвестно "
                "(нет подтверждённой датированной истории публикаций); "
                "изменение совокупного рейтинга: неизвестно.")
    lines.append(
        "Ни положительный результат по заказам, ни чужие предварительные "
        "товары, ни совпадение дат не доказывают результативность "
        "исходного отзыва. Исторические источники не позволяют "
        "отделить подтверждённые органические заказы от остальных.")
    lines.append("Денежный расчёт временно отложен; отсутствие данных не приравнивается к нулю.")
    return "\n".join(lines)
