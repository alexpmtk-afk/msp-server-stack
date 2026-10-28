"""Separate marketplace readers feeding the existing shared rating calculations.

No authentication, writes, or counter-field guesses live here. The injected
reader owns the aggregate 24-call budget, including quota inspection.
"""
from datetime import date, timedelta
import json
import re

try:
    from apps.msp_self_analytics import wb_rating_source, ozon_rating_source
    from apps.msp_self_analytics.review_source_adapter import review_source_evidence, _window_observations
    from apps.msp_self_analytics.dated_rating_dynamics import compare_dated_rating_periods
except ModuleNotFoundError:
    import wb_rating_source, ozon_rating_source
    from review_source_adapter import review_source_evidence, _window_observations
    from dated_rating_dynamics import compare_dated_rating_periods

ADAPTERS={'wb':wb_rating_source,'oz':ozon_rating_source}
PASS={'PASS_JSON','PASS_STRUCTURED'}


def source_adapter(marketplace):
    if marketplace not in ADAPTERS:
        raise ValueError('UNSUPPORTED_RATING_MARKETPLACE')
    return ADAPTERS[marketplace]


def _sku(value):
    if not isinstance(value,str) or not re.fullmatch(r'[0-9]{1,20}',value):
        raise ValueError('INVALID_MARKETPLACE_SKU')
    return int(value)


def collect_rating_evidence(reader,*,marketplace,sku,checkpoints,max_reads=24):
    """Fetch only this marketplace, then reuse the existing formulas for both sides."""
    adapter=source_adapter(marketplace);numeric=_sku(sku)
    if type(max_reads) is not int or not 1<=max_reads<=24:
        raise ValueError('INVALID_READ_BUDGET')
    if not isinstance(checkpoints,list) or len(checkpoints)>12:
        raise ValueError('CHECKPOINT_LIMIT_EXCEEDED')
    active=[cp for cp in checkpoints if cp.get('windows')]
    for cp in active:
        w=cp['windows']
        compare_dated_rating_periods(None,event_date=cp['review_date'],
            before_start=w['before']['d1'],before_end=w['before']['d2'],
            after_start=w['after']['d1'],after_end=w['after']['d2'])
    def read(args):
        if reader.calls>=max_reads:return None,'CALL_BUDGET'
        return reader.call(adapter.TOOL,{'sku':numeric,**args})
    comments,cs=read({'report':'comments'}) if active else (None,'NO_COMPLETED_WINDOWS')
    if cs not in PASS:comments=None
    evidence={};sources={};cache={}
    for cp in active:
        w=cp['windows'];combined=[];prior_tokens=set();states=[]
        for side in ('before','after'):
            start=(date.fromisoformat(w[side]['d1'])-timedelta(days=1)).isoformat()
            key=(start,w[side]['d2'])
            if key not in cache:cache[key]=read({'report':'by_period','d1':key[0],'d2':key[1]})
            rows,state=cache[key];states.append(state)
            if state not in PASS or not isinstance(rows,list):continue
            # Remove identical cross-response overlap, not duplicate provider
            # rows within one response. Conflicting dates stay visible.
            tokens={json.dumps(row,sort_keys=True,ensure_ascii=False) for row in rows}
            combined.extend(row for row in rows if json.dumps(row,sort_keys=True,ensure_ascii=False) not in prior_tokens)
            prior_tokens.update(tokens)
        normalized=adapter.normalize(comments,combined)
        number=cp['checkpoint_number']
        unavailable={'status':'UNAVAILABLE','reason':'FOUR_COUNTERS_NOT_VERIFIED_FOR_'+marketplace.upper()}
        sources[number]=unavailable
        e=review_source_evidence(sku=sku,event_date=cp['review_date'],
            before_start=w['before']['d1'],before_end=w['before']['d2'],
            after_start=w['after']['d1'],after_end=w['after']['d2'],
            comments=normalized['comments'],period=normalized['period'],
            comments_status=cs,period_status=';'.join(states),
            lk_status='Источник кабинета не принят для этой площадки',marketplace=marketplace)
        e['source_quality_flags']=normalized['quality_flags']
        e['strict_rating_comparison']=compare_dated_rating_periods(unavailable,
            event_date=cp['review_date'],before_start=w['before']['d1'],before_end=w['before']['d2'],
            after_start=w['after']['d1'],after_end=w['after']['d2'])
        evidence[number]=e
    return {'marketplace':marketplace,'tool':adapter.TOOL,'evidence':evidence,
            'dated_rating_sources':sources,'mpstats_calls':reader.calls,
            'four_counters_verified':False,'complete_publication_history':False}


def inspect_marketplace_history(*,marketplace,sku,d1,d2,comments,period):
    """Source acceptance without inventing a missing registered review date.

    This is NOT a self-purchase event analysis. It exposes the same shared
    window observation logic for exact historical dates supplied by an audit.
    """
    adapter=source_adapter(marketplace);_sku(sku)
    first,last=map(date.fromisoformat,(d1,d2))
    if last<first or (last-first).days>=90:raise ValueError('INVALID_HISTORY_WINDOW')
    normalized=adapter.normalize(comments,period)
    window=_window_observations(normalized['period'],normalized['comments'],d1,d2)
    return {'mode':'SOURCE_HISTORY_INSPECTION_NOT_REGISTERED_EVENT','marketplace':marketplace,
            'sku':sku,'source_ref':'MPSTATS '+adapter.TOOL,'window':window,
            'source_quality_flags':normalized['quality_flags'],
            'four_counters_verified':False,'complete_publication_history':False,
            'independent_buyers_verified':False,'causal_effect_proven':False}
