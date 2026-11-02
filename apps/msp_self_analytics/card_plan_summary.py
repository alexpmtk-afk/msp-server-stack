"""Read-only plan/fact header shared by every ordinary WB/Ozon report path."""
import sqlite3
from pathlib import Path
from apps.msp_self_analytics.sku_request import load_existing_series


def load_card_plan_summary(database, *, marketplace, store, sku):
    try:
        completed=load_existing_series(database,marketplace=marketplace,store=store,sku=sku)
    except ValueError as exc:
        if str(exc)!='SKU_HAS_NO_RECORDED_PURCHASES':raise
        completed=[]
    planned=[]
    c=sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro',uri=True)
    try:
        tables={r[0] for r in c.execute("select name from sqlite_master where type='table'")}
        if 'self_purchase_plan' in tables:
            if 'self_purchase_plan_metrics' in tables:
                query='''select p.quantity,m.planned_review_count from self_purchase_plan p
                  left join self_purchase_plan_metrics m on m.source_row=p.source_row
                    and m.marketplace=p.marketplace and m.store=p.store and m.marketplace_sku=p.marketplace_sku
                  where p.is_current=1 and p.marketplace=? and p.store=? and p.marketplace_sku=?'''
            else:
                query='''select quantity,NULL from self_purchase_plan
                  where is_current=1 and marketplace=? and store=? and marketplace_sku=?'''
            planned=[{'quantity':r[0],'planned_review_count':r[1]}
                     for r in c.execute(query,(marketplace,store,sku))]
    finally:c.close()
    result={'recorded_purchase_rows':len(completed),'planned_rows_without_purchase':len(planned),
            'recorded_review_rows':sum(bool(r.get('review_date')) for r in completed)}
    for source,key in [('quantity','purchase'),('planned_review_count','review')]:
        values={r.get(source) for r in completed+planned if r.get(source) is not None}
        result[key+'_target']=next(iter(values)) if len(values)==1 else None
        result[key+'_target_conflicts']=sorted(values) if len(values)>1 else []
    return result


def format_card_plan_summary_ru(summary):
    def target(key):
        v=summary[key+'_target']
        if v is not None:return str(v)
        return 'противоречив' if summary[key+'_target_conflicts'] else 'не указан'
    return ('ПЛАН И ФАКТ\nПлан выкупов: '+target('purchase')+'; план отзывов: '+target('review')+'.\n'
            'Зарегистрировано выкупов: '+str(summary['recorded_purchase_rows'])+
            '; датированных записей отзывов: '+str(summary['recorded_review_rows'])+
            '; плановых строк без факта выкупа: '+str(summary['planned_rows_without_purchase'])+'.\n'
            'Повторения планов не суммируются. Планы и записи реестра не доказывают публичную публикацию оценок.')
