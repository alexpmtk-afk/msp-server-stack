"""Concise Russian rendering of historical source-verified series observations.

Safe for private report assembly; no action calls or marketplace writes.
"""
from __future__ import annotations
from math import isfinite


def _count(v, *, unknown="не установлено"):
    return unknown if v is None else str(v)


def _fmt_number(v):
    if not isinstance(v,(int,float)) or isinstance(v,bool) or not isfinite(v):
        return "нет подтверждённых данных"
    rounded=round(v,2)
    return (str(int(rounded)) if rounded==int(rounded) else str(rounded)).replace(".",",")


def _format_date(s):
    if not isinstance(s,str) or len(s)!=10 or s[4]!="-" or s[7]!="-":
        return "нет даты"
    return f"{s[8:10]}.{s[5:7]}.{s[0:4]}"


def format_series_report_ru(report: dict, *, label: str | None = None) -> str:
    """Format one already-built pure series_report, never attribute causality."""
    if not isinstance(report,dict) or not isinstance(report.get("series"),dict):
        raise ValueError("SERIES_REPORT_REQUIRED")
    series=report["series"]
    windows=series.get("windows")
    plan=series.get("planned_total_per_card")
    bought=series.get("recorded_completed_purchase_rows")
    reviews=series.get("recorded_review_date_rows")
    if not isinstance(plan,int) or plan<1 or not isinstance(bought,int) or bought<0:
        title="Серия с противоречивым или неполным планом"
    else:
        title=f"План {plan}; записано выкупов {bought}; дат отзывов {reviews}"
    lines=["ОТЧЁТ ПО ИСТОРИИ КАРТОЧКИ"]
    if label is not None:
        if not isinstance(label,str) or not label.strip():
            raise ValueError("INVALID_LABEL")
        lines.append(f"Товар: {label.strip()}")
    lines.append(title)
    phase=series.get("series_phase")
    if phase=="INTERMEDIATE_SERIES":
        lines.append("Этап: промежуточное наблюдение, серия ещё не завершена.")
    elif phase=="REPORTED_SERIES_COMPLETE_PUBLICATION_UNVERIFIED":
        lines.append("Этап: все плановые строки с датами отзывов учтены; публикация не подтверждена независимо.")
    elif phase=="TARGET_CONFLICT":
        lines.append("Этап: план противоречит сам себе, требуется проверка записей.")
    else:
        lines.append("Этап: "+str(phase or "не установлен")+".")
    if not windows:
        lines.append("Периоды: данных пока недостаточно для сравнения.")
        lines.append("Вывод: изменение продаж или рейтинга не установлено.")
        return "\n".join(lines)
    before=windows["before"]
    after=windows["after"]
    days=windows["effective_days_each"]
    lines.append(
        f"До первого записанного отзыва: {_format_date(before['d1'])}–{_format_date(before['d2'])}."
    )
    lines.append(
        f"После последнего записанного отзыва: {_format_date(after['d1'])}–{_format_date(after['d2'])}."
    )
    lines.append(f"Оба периода по {days} завершённых календарных дней.")
    if not windows["full_requested_window"]:
        lines.append("Период укорочен; это предварительный результат, не полный месячный отчёт.")
    obs=report.get("provider_observations")
    if not isinstance(obs,dict) or not isinstance(obs.get("before"),dict) or not isinstance(obs.get("after"),dict) or not (obs["before"].get("valid") and obs["after"].get("valid")):
        lines.append("MPSTATS: недостаточно сопоставимых данных за оба периода.")
    else:
        b,a=obs["before"],obs["after"]
        lines.append(
            f"Оценочные продажи MPSTATS: {_fmt_number(b.get('sales'))} до и {_fmt_number(a.get('sales'))} после."
        )
        lines.append(
            f"Дни наличия по MPSTATS: {_count(b.get('provider_stock_days'))} до и {_count(a.get('provider_stock_days'))} после."
        )
        normalized=obs.get("sales_per_provider_stock_day_change") or {}
        lines.append(
            "Изменение оценочных продаж на день наличия: "
            +_fmt_number(normalized.get("absolute"))+" единицы в день."
        )
        if b.get("sales")==0:
            lines.append("Относительный прирост в процентах не рассчитывается из нулевой исходной базы.")
    lines.append(
        "История опубликованных оценок и общего рейтинга: "
        +("подтверждена." if report.get("historical_rating_verified") is True
          and report.get("independent_publication_verification") is True
          else "не подтверждена независимыми данными.")
    )
    lines.append("Реальные оплаченные заказы кабинета: "
                 +("проверены." if report.get("real_seller_order_count_verified") is True
                    else "не проверены; MPSTATS показывает оценочные данные."))
    lines.append(
        "Сопоставимые конкуренты: "
        +str(report.get("verified_comparator_count",0))
        +" подтверждено."
    )
    lines.append(
        "Итог: выявлена только наблюдаемая разница между периодами; "
        "влияние зарегистрированных отзывов не доказано."
    )
    return "\n".join(lines)
