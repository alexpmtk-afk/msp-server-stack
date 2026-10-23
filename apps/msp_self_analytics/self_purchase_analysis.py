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
except ModuleNotFoundError:
    from checkpoint_workflow import assemble_checkpoint_analysis
    from price_event_context import price_event_context
    from checkpoint_report_ru import format_checkpoint_history_ru
    from decision_indicators import variable_unit_contribution


def build_observational_case(
    rows, historical_observations, *,
    as_of, price_events=None, price_source_status="UNAVAILABLE",
    verified_unit_costs=None, requested_days=90,
    max_checkpoints=12, max_provider_reads=24,
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
            "price_impact_uncertainty":strength,
            "financial_return_status":"UNKNOWN_CAUSAL_INCREMENT",
            "verified_control_group_status":"NOT_VERIFIED",
            "operational_conclusion":"OBSERVE_AND_REVIEW_ONLY",
            "source_quality_flags":item.get("source_quality_flags",[]),
        })
    narrative=format_checkpoint_history_ru(history)
    if prices["status"]=="UNKNOWN_PRICE_HISTORY":
        narrative+="\nЖурнал цен: надёжное датированное сопоставление пока недоступно."
    else:
        for p in prices["checkpoints"]:
            for event in p.get("after_window_price_events") or []:
                old, new = event.get("old_seller_price_rub"), event.get("new_seller_price_rub")
                price = (old + " → " + new + " ₽") if old is not None and new is not None else "цены неизвестны"
                narrative += ("\nЦена ПОСЛЕ отзыва " + event["event_date"] + ": " + price + "; журнал МСП.")
            if p.get("confounding_price_events"):
                narrative+=(
                    "\nКонтроль "+str(p["checkpoint_number"])+
                    ": в журнале обнаружены изменения цены в рассматриваемой истории; "
                    "их влияние не определено.")
        narrative+=(
            "\nПустые записи журнала не доказывают неизменную цену, "
            "скидки или условия продажи на площадке.")
    if finance["status"]=="FACT_DERIVED":
        narrative+=(
            "\nПеременный вклад единицы товара подтверждён финансовыми данными, "
            "но дополнительная прибыль от исторических отзывов всё равно не доказана.")
    else:
        narrative+="\nФинансовые данные неполны; фактическую окупаемость определить нельзя."
    return {
        "status":"OBSERVATIONAL_REPORT_READY"
                 if history["status"]=="COMPLETE_DESCRIPTIVE"
                 else "OBSERVATIONAL_REPORT_PARTIAL",
        "history":history,
        "price_history":prices,
        "verified_unit_contribution":finance,
        "checkpoint_interpretations":interpretation,
        "business_effect_proven":False,
        "reported_purchase_count_is_sum_of_rows":True,
        "self_purchase_plan_is_not_sum_of_quantity":True,
        "marketplace_actions_allowed":False,
        "human_readable_ru":narrative,
    }
