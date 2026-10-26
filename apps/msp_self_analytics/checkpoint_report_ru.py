"""Human-readable Russian retrospective per review-date checkpoint report.

Values are MPSTATS estimates, not independently certified actual orders. The
summary is not a causal or profitability claim. Never proposes artificial
orders/reviews or automatically changes marketplace state.
"""
from __future__ import annotations

from math import isfinite


def _date(value):
    if not isinstance(value, str) or len(value) != 10:
        return "нет даты"
    return f"{value[8:10]}.{value[5:7]}.{value[:4]}"


def _number(value):
    if type(value) not in (int, float) or not isfinite(value):
        return "неизвестно"
    out = round(value, 3)
    return (str(int(out)) if out == int(out) else str(out)).replace(".", ",")


def format_checkpoint_history_ru(report: dict, *, label: str | None = None) -> str:
    if not isinstance(report, dict) or not isinstance(report.get("checkpoints"), list):
        raise ValueError("CHECKPOINT_HISTORY_REQUIRED")
    series = report.get("series")
    if not isinstance(series, dict):
        raise ValueError("SERIES_REQUIRED")
    if label is not None and (not isinstance(label, str) or not label.strip()):
        raise ValueError("INVALID_PRODUCT_LABEL")
    lines = ["ИСТОРИЧЕСКИЙ АНАЛИЗ ПО ДАТАМ ОТЗЫВОВ"]
    if label is not None:
        lines.append("Товар: " + label.strip())
    lines.append(
        "План по карточке: " + str(series.get("planned_total_per_card")
                             if series.get("planned_total_per_card") is not None
                             else "противоречив")
        + "; зарегистрировано выкупов: " +
        str(series.get("recorded_completed_purchase_rows", "неизвестно"))
        + "; датированных записей отзывов: " +
        str(series.get("recorded_review_date_rows", "неизвестно")) + ".")
    if not report["checkpoints"]:
        lines.append("Для анализа ПОСЛЕ нет датированных записей отзывов.")
    for cp in report["checkpoints"]:
        lines.append(
            "Контроль " + str(cp["checkpoint_number"]) + " — " +
            _date(cp["review_date"]) + "; накоплено записей отзывов: " +
            str(cp["cumulative_recorded_review_rows"]) + ".")
        w = cp.get("windows")
        if not isinstance(w, dict):
            lines.append("  ПОСЛЕ: нет завершённого периода; результат ожидает данные.")
            continue
        lines.append("  ДО: " + _date(w["before"]["d1"]) + "–" +
                     _date(w["before"]["d2"]) + "; ПОСЛЕ: " +
                     _date(w["after"]["d1"]) + "–" +
                     _date(w["after"]["d2"]) + ".")
        n = cp.get("effective_days_each")
        cap = cp.get("requested_days_each", 90)
        lines.append("  Длительность: " + str(n) + " полных дней ДО и ПОСЛЕ; максимум " + str(cap) + " дней.")
        if not w["full_requested_window"]:
            lines.append("  Равные укороченные окна (не полный " + str(cap) + "-дневный итог).")
        obs = cp.get("provider_observations")
        if (not isinstance(obs, dict) or
                not isinstance(obs.get("before"), dict) or
                not isinstance(obs.get("after"), dict) or
                not obs["before"].get("valid") or
                not obs["after"].get("valid")):
            lines.append("  MPSTATS: нет двух проверенных ответов за точные даты.")
            continue
        before, after = obs["before"], obs["after"]
        lines.append("  Внешняя оценка заказов MPSTATS (поле sales): " +
                     _number(before.get("sales")) + " ДО → " +
                     _number(after.get("sales")) + " ПОСЛЕ.")
        # Expose only validated, paired numeric fields. Provider has renamed
        # external stock-parser sales/revenue to Orders pcs/Orders rub in UI.
        # Do not treat 'purchase' fields as proven return counts.
        details = cp.get("additional_mpstats_metrics") or {}
        fields = details.get("fields") or {}
        money = fields.get("revenue") or {}
        if money.get("state") == "AVAILABLE":
            lines.append("  Сумма оценочных заказов MPSTATS (поле revenue): " +
                         _number(money.get("before")) + " ДО → " +
                         _number(money.get("after")) + " ПОСЛЕ.")
        for key in ("sales_estimated", "revenue_estimated", "purchase",
                    "purchase_after_return"):
            detail = fields.get(key) or {}
            if detail.get("state") == "AVAILABLE":
                lines.append("  Дополнительный показатель MPSTATS " + key + ": " +
                             _number(detail.get("before")) + " ДО → " +
                             _number(detail.get("after")) +
                             " ПОСЛЕ (тип/единицы не приравниваем к продажам или возвратам).")
        lines.append("  Дни наличия по MPSTATS: " +
                     _number(before.get("provider_stock_days")) + " ДО → " +
                     _number(after.get("provider_stock_days")) + " ПОСЛЕ.")
        normalized = cp.get("stock_normalized_orders")
        if isinstance(normalized, dict):
            rate_status = normalized.get("status")
            if rate_status in ("READY_DESCRIPTIVE", "READY_LOW_SAMPLE"):
                lines.append(
                    "  Оценочные заказы на 1 день наличия: "
                    + _number(normalized["orders_per_in_stock_day_before"]) +
                    " ДО → " + _number(normalized["orders_per_in_stock_day_after"]) +
                    " ПОСЛЕ (MPSTATS, не реальные оплаченные продажи).")
                if normalized["rate_percent_change"] is not None:
                    lines.append("  Изменение интенсивности: " +
                                 _number(normalized["rate_percent_change"]) +
                                 "%; НЕ доказательство эффекта отзыва.")
                else:
                    lines.append(
                        "  Изменение интенсивности в процентах: неизвестно "
                        "(нулевая исходная база).")
                lines.append(
                    "  Доля дней с наличием: " +
                    _number(normalized["in_stock_coverage_percent_before"]) +
                    "% ДО → " +
                    _number(normalized["in_stock_coverage_percent_after"]) +
                    "% ПОСЛЕ.")
                if normalized["small_observed_sample"]:
                    lines.append(
                        "  Малая выборка оценочных заказов хотя бы в одном "
                        "периоде (<10); относительная динамика неустойчива.")
            elif rate_status=="ZERO_STOCK_EXPOSURE":
                lines.append("  Заказы на день наличия не вычислены: "
                             "есть период с 0 подтверждённых дней наличия.")
            else:
                lines.append("  Заказы на день наличия неизвестны: "
                             "нет достоверных заказов и/или дней наличия.")
        flags = cp.get("source_quality_flags") or []
        if "STOCK_AVAILABILITY_DIFFERS" in flags:
            lines.append("  Наличие различалось: суммарные продажи напрямую несопоставимы.")
        if "PERCENT_CHANGE_FROM_ZERO_UNDEFINED" in flags:
            lines.append("  Процент роста от нулевой исходной базы не вычисляется.")
        if "OTHER_PRICE_ADVERTISING_DEMAND_CONFOUNDERS_UNVERIFIED" in flags:
            lines.append("  Изменения цены, рекламы и спроса отдельно не исключены.")
    lines.extend([
        "Показатели API sales/revenue относятся к внешней оценке MPSTATS "
        "(в интерфейсе с 2026 года — заказы и их сумма), не подтверждают "
        "фактическую оплату или органическое происхождение заказов.",
        "Отдельное количество возвратов и фактическая сумма выплат "
        "из данного ответа пока не подтверждены.",
        "Исторические рейтинги, публикация каждого отзыва и реальные оплаченные "
        "органические заказы отдельно не подтверждены.",
        "Итог: наблюдаемая динамика не доказывает причинное действие прошлых выкупов "
        "или отзывов; экономическая окупаемость без проверенных затрат неизвестна.",
    ])
    return "\n".join(lines)
