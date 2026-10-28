"""Unified historical MSP self-purchase observation with explicit unknowns.

Combines registry review-date checkpoints, dated MPSTATS estimates, the MSP
price-event journal and optionally separately verified financial sources.
No network access, marketplace writes or instructions for creating reviews.
"""
from __future__ import annotations

try:
    from apps.msp_self_analytics.checkpoint_workflow import assemble_checkpoint_analysis
    from apps.msp_self_analytics.price_event_context import price_event_context
    from apps.msp_self_analytics.checkpoint_report_ru import format_checkpoint_history_ru
    from apps.msp_self_analytics.decision_indicators import variable_unit_contribution
    from apps.msp_self_analytics.nonfinancial_outcome import (
        summarize_nonfinancial_outcome, format_nonfinancial_outcome_ru)
except ModuleNotFoundError:
    from checkpoint_workflow import assemble_checkpoint_analysis
    from price_event_context import price_event_context
    from checkpoint_report_ru import format_checkpoint_history_ru
    from decision_indicators import variable_unit_contribution
    from nonfinancial_outcome import (
        summarize_nonfinancial_outcome, format_nonfinancial_outcome_ru)


def build_observational_case(
    rows, historical_observations, *,
    as_of, price_events=None, price_source_status="UNAVAILABLE",
    verified_unit_costs=None, requested_days=90,
    max_checkpoints=12, max_provider_reads=24,
    dated_rating_sources=None, dated_review_activity_sources=None, review_source_evidence=None, own_order_sources=None,
):
    """One cohesive result with traceable missing-evidence gates.

    Historical observations keyed by exact date span YYYY-MM-DD|YYYY-MM-DD
    from typed MPSTATS source, not certified organic/paid seller orders.
    Price events already filtered by marketplace/store/SKU from readonly view.
    Verified unit costs must be itemized from documented finance sources.
    """
    history=assemble_checkpoint_analysis(
        rows, historical_observations, as_of=as_of,
        requested_days=requested_days, max_checkpoints=max_checkpoints,
        max_provider_reads=max_provider_reads)
    own_summaries = []
    if isinstance(own_order_sources, dict):
        for checkpoint_number, pair in own_order_sources.items():
            parts = [pair.get(side) for side in ("before", "after")] if isinstance(pair, dict) else [None, None]
            observed = all(
                isinstance(part, dict)
                and part.get("status") == "OBSERVED_OWN_WB_FEED"
                and part.get("pagination_complete") is True
                for part in parts)
            own_summaries.append({
                "checkpoint_number": checkpoint_number,
                "both_windows_observed": observed,
                "source_load_coverage_verified": (
                    observed and all(part.get("source_load_coverage_verified") is True
                                     for part in parts)),
                "registry_order_id_linkage_verified": False,
            })
    if not own_summaries:
        own_status = "UNKNOWN_NO_OWN_ORDER_SOURCE"
    elif not all(row["both_windows_observed"] for row in own_summaries):
        own_status = "OWN_FEED_PARTIAL_OR_UNAVAILABLE"
    else:
        own_status = "OWN_FEED_OBSERVED_COVERAGE_UNVERIFIED"
    history["order_evidence"] = {
        "status": own_status, "checkpoints": own_summaries,
        "independent_organic_orders_verified": False,
        "own_orders_automatically_subtracted": False,
    }
    prices=price_event_context(history,price_events,
                               source_status=price_source_status)
    finance=variable_unit_contribution(verified_unit_costs)
    interpretation=[]
    by_price={r["checkpoint_number"]:r
              for r in prices.get("checkpoints",[])}
    for item in history["checkpoints"]:
        index=item["checkpoint_number"]
        p=by_price.get(index)
        price_state=p.get("status") if p else "UNKNOWN_PRICE_HISTORY"
        if p and p.get("confounding_price_events"):
            strength="PRICE_CHANGE_CONFOUND_RECORDED"
        elif price_state=="NO_RECORDED_PRICE_EVENTS_IN_PERIOD":
            strength="NO_JOURNAL_EVENT_BUT_MARKET_PRICE_NOT_PROVEN_CONSTANT"
        else:
            strength="PRICE_HISTORY_UNKNOWN"
        interpretation.append({
            "checkpoint_number":index,
            "review_date":item["review_date"],
            "historical_sales_status":item["status"],
            "price_context_status":price_state,
            "price_events_before":p.get("recorded_price_changes_before_window") if p else None,
            "price_events_after":p.get("recorded_price_changes_after_window") if p else None,
            "price_changed_after_review":p.get("post_review_seller_price_changed_in_journal") if p else None,
            "price_impact_uncertainty":strength,
            "financial_return_status":"UNKNOWN_CAUSAL_INCREMENT",
            "verified_control_group_status":"NOT_VERIFIED",
            "operational_conclusion":"OBSERVE_AND_REVIEW_ONLY",
            "source_quality_flags":item.get("source_quality_flags",[]),
        })
    nonfinancial=summarize_nonfinancial_outcome(
        history,prices,dated_rating_sources=dated_rating_sources,
        dated_review_activity_sources=dated_review_activity_sources,
        review_observations=review_source_evidence)
    review_source_evidence={k:dict(v) for k,v in (review_source_evidence or {}).items()}
    for outcome in nonfinancial['checkpoints']:
        number=outcome['checkpoint_number']
        if number in review_source_evidence:
            review_source_evidence[number]['strict_rating_comparison']=outcome['dated_rating_comparison']
    narrative=format_checkpoint_history_ru(history)
    narrative+="\n"+format_nonfinancial_outcome_ru(nonfinancial)
    if review_source_evidence:
        try:
            from apps.msp_self_analytics.review_source_adapter import format_review_source_evidence_ru
        except ModuleNotFoundError:
            from review_source_adapter import format_review_source_evidence_ru
        for value in review_source_evidence.values():
            narrative+="\n"+format_review_source_evidence_ru(value)
    if prices["status"]=="UNKNOWN_PRICE_HISTORY":
        narrative+="\nЖурнал цен: надёжное датированное сопоставление пока недоступно."
    else:
        for p in prices["checkpoints"]:
            number=p["checkpoint_number"]
            before=p.get("before_window_price_events") or []
            between=p.get("between_windows_price_events") or []
            after=p.get("after_window_price_events") or []
            narrative+=(
                "\nКонтроль "+str(number)+": журнал цен МСП — изменений ДО "+
                str(len(before))+", в промежутке "+str(len(between))+
                ", ПОСЛЕ "+str(len(after))+".")
            for label,group in (("ДО",before),("МЕЖДУ ПЕРИОДАМИ",between),
                                ("ПОСЛЕ отзыва",after)):
                for event in group:
                    old=event.get("old_seller_price_rub")
                    new=event.get("new_seller_price_rub")
                    pair=(old+" → "+new+" ₽") if old is not None and new is not None else (
                        "было/стало: значение неизвестно")
                    change=event.get("change_rub")
                    percent=event.get("change_percent")
                    if change is not None:
                        pair+="; изменение "+change.replace(".",",")+" ₽"
                    if percent is not None:
                        pair+=" ("+percent.replace(".",",")+"%)"
                    source=event.get("source_segment") or "не указан"
                    narrative+=(
                        "\nЦена "+label+" "+event["event_date"]+": "+pair+
                        "; источник: журнал МСП ("+source+").")
            if after:
                narrative+=(
                    "\nВ период ПОСЛЕ цена продавца корректировалась; "
                    "это самостоятельный возможный фактор изменения заказов. "
                    "Причинность изменения спроса не установлена.")
        narrative+=(
            "\nВ журнале указана цена продавца после его скидки, "
            "а не подтверждённая конечная цена покупателя. "
            "Пустой журнал не доказывает постоянство цены/СПП.")
    if finance["status"]=="FACT_DERIVED":
        narrative+=(
            "\nПеременный вклад единицы товара подтверждён финансовыми данными, "
            "но дополнительная прибыль от исторических отзывов всё равно не доказана.")
    else:
        narrative+="\nДенежная окупаемость отложена; не является условием готовности нестоимостного отчёта."
    return {
        "status":"OBSERVATIONAL_REPORT_READY"
                 if history["status"]=="COMPLETE_DESCRIPTIVE"
                 else "OBSERVATIONAL_REPORT_PARTIAL",
        "history":history,
        "price_history":prices,
        "verified_unit_contribution":finance,
        "nonfinancial_outcome":nonfinancial,
        "review_source_evidence":review_source_evidence or {},
        "checkpoint_interpretations":interpretation,
        "business_effect_proven":False,
        "reported_purchase_count_is_sum_of_rows":True,
        "self_purchase_plan_is_not_sum_of_quantity":True,
        "marketplace_actions_allowed":False,
        "human_readable_ru":narrative,
    }
