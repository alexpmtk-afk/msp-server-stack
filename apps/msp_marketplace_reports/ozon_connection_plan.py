"""Separate offline Ozon connection contract, recovered from existing source.

Method versions supported by official Ozon release notices; exact current
schemas/limits still require acceptance. Never sets method approval env/gates.
"""
from datetime import date
from .archive import CABINETS
from .providers import Request,OZON_FINAL,OZON_FBO,OZON_FBS,OZON_ACCRUAL


def connection_plan(cabinet,as_of,*,year=2026):
    if cabinet not in CABINETS['ozon'] or type(as_of) is not date or type(year) is not int or year!=2026 or as_of.year<year:
        raise ValueError('explicit Ozon cabinet/year/date required')
    last=as_of.month-1 if as_of.year==year else 12
    final=[Request('ozon',OZON_FINAL,{'year':year,'month':m}) for m in range(1,last+1)]
    current=[]
    if as_of.year==year:
        start=as_of.replace(day=1)
        from .providers import _moscow_bounds
        since,until=_moscow_bounds(start,as_of)
        for path in (OZON_FBO,OZON_FBS):
            current.append(Request('ozon',path,{'filter':{'since':since,'to':until},'limit':100,'cursor':'',
                                               'with':{'analytics_data':True,'financial_data':True,'legal_info':True}}))
        for d in range(1,as_of.day+1):
            current.append(Request('ozon',OZON_ACCRUAL,{'date':as_of.replace(day=d).isoformat(),'last_id':''}))
    return {'cabinet':cabinet,'year':year,'final':final,'current':current,
            'financial_report_dataset':'ozon_final_realization','orders_are_final':False,
            'api_enabled':False,'approval_env_not_set':'MSP_REPORTS_OZON_FINANCE_METHODS_VERIFIED',
            'schema_acceptance':'REQUIRED_BEFORE_API','quota_owner':'Client-Id',
            'pagination':{OZON_FINAL:'none_per_existing_source',OZON_FBO:'cursor',OZON_FBS:'cursor',OZON_ACCRUAL:'last_id'},
            'late_corrections':'revalidate_every_closed_month_in_bounded_rotation_replace_month_rebuild_annual'}
