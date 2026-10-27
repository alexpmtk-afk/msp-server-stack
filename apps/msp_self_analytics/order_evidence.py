"""Pure provenance guard; does not fabricate orders or infer own-order linkage."""
def assess_window(*, observed_units, own_linked_units, pagination_complete=False, coverage_verified=False, unmatched_own_events=False, provider_estimate=None):
 for v in (observed_units,own_linked_units):
  if type(v) is not int or v<0:raise ValueError('Nonnegative observed counts required')
 if own_linked_units>observed_units:raise ValueError('Own units exceed observed units')
 external=observed_units-own_linked_units if pagination_complete and coverage_verified and not unmatched_own_events else None
 return {'observed_units':observed_units,'own_linked_units':own_linked_units,'independent_external_units':external,'organic_units':None,'source_discrepancy':provider_estimate is not None and provider_estimate!=observed_units,'external_demand_change_percent':None,'coverage_verified':coverage_verified,'pagination_complete':pagination_complete}

def report_guard_ru(report):
 evidence=report.get('order_evidence') if isinstance(report,dict) else None
 if not isinstance(evidence,dict):return 'Сверка внешнего спроса: UNKNOWN — собственные заказы WB и исключение самовыкупов в этом отчёте не подтверждены. Самовыкупы учитывать отдельно. Динамика MPSTATS не является динамикой независимых заказов.'
 return 'Сверка внешнего спроса: '+str(evidence.get('status','UNKNOWN'))+'. Самовыкупы отдельно; расхождения WB/MPSTATS раскрывать. Полная пагинация не гарантирует полноты загрузки; остаток заказов не означает органический спрос.'
