#!/usr/bin/env python3
"""Hermes read-only on-demand analysis: SKU -> SQLite -> MPSTATS -> Russian report.

Must run locally as hermes in the dedicated self-purchases Skill. No writes,
review generation, scheduled outbound messages or other marketplace actions.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import sqlite3
import sys
import tomllib
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

DB = Path("/opt/mcp/data/msp/msp_data.sqlite3")
CONFIG = Path("/home/hermes/.codex/config.toml")
SKILL_SCRIPTS = Path("/home/hermes/.hermes/skills/productivity/msp-self-purchases/scripts")
MAX_READS = 24
ROOT = Path(__file__).resolve().parents[2]
if (ROOT / 'apps/msp_self_analytics').is_dir():
    sys.path.insert(0, str(ROOT))


def _modules():
    if (ROOT / 'apps/msp_self_analytics').is_dir():
        from apps.msp_self_analytics.sku_request import plan_requested_sku, resolve_catalog_listing
        from apps.msp_self_analytics.self_purchase_analysis import build_observational_case
        return plan_requested_sku, resolve_catalog_listing, build_observational_case
    if not SKILL_SCRIPTS.is_dir():
        raise RuntimeError("SKILL_SCRIPTS_UNAVAILABLE")
    sys.path.insert(0, str(SKILL_SCRIPTS))
    from sku_request import plan_requested_sku, resolve_catalog_listing
    from self_purchase_analysis import build_observational_case
    return plan_requested_sku, resolve_catalog_listing, build_observational_case


def _decode_reply(raw):
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        for line in reversed(raw.splitlines()):
            if line.startswith("data:"):
                try:
                    return json.loads(line[5:].strip())
                except ValueError:
                    continue
    return None


def _post(url, payload, session=None, protocol=None):
    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream"}
    if session:
        headers["Mcp-Session-Id"] = session
    if protocol:
        headers["MCP-Protocol-Version"] = protocol
    req = urllib.request.Request(
        url, data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=45) as answer:
            status, meta = answer.status, dict(answer.headers.items())
            body = answer.read(2_000_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        status, meta = exc.code, dict(exc.headers.items())
        body = exc.read(80_000).decode("utf-8", "replace")
    return status, meta, _decode_reply(body)


def _unpack(data):
    if not isinstance(data, dict) or data.get("error"):
        return None, "RPC_ERROR"
    result = data.get("result")
    if not isinstance(result, dict) or result.get("isError"):
        return None, "TOOL_ERROR"
    structured = result.get("structuredContent")
    if isinstance(structured, (dict,list)):
        return structured, "PASS_STRUCTURED"
    for item in result.get("content") or []:
        if isinstance(item, dict) and item.get("type") == "text":
            try:
                val = json.loads(item.get("text") or "")
                if isinstance(val, (dict,list)):
                    return val, "PASS_JSON"
            except ValueError:
                pass
    return None, "NO_DICT"


def _period_stats(payload):
    if not isinstance(payload, dict):
        return {}
    if isinstance(payload.get("period_stats"), dict):
        return payload["period_stats"]
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("period_stats"), dict):
        return data["period_stats"]
    return {}


def _provider_url():
    params = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    url = params["mcp_servers"]["mpstats"]["url"]
    if not isinstance(url, str) or not url.startswith(("https://", "http://")):
        raise RuntimeError("PROVIDER_CONFIG_INVALID")
    return url


class MpstatsReader:
    def __init__(self):
        self.url = _provider_url()
        self.session = None
        self.protocol = None
        self.calls = 0
        for version in ("2025-06-18", "2025-03-26"):
            status, headers, result = _post(
                self.url, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                           "params": {"protocolVersion": version, "capabilities": {},
                                      "clientInfo": {"name": "hermes-self-sku-readonly",
                                                     "version": "1"}}})
            if status < 400 and isinstance(result, dict) and isinstance(result.get("result"), dict):
                self.protocol = result["result"].get("protocolVersion") or version
                self.session = headers.get("Mcp-Session-Id") or headers.get("mcp-session-id")
                break
        if self.protocol is None:
            raise RuntimeError("PROVIDER_INITIALIZATION_FAILED")
        _post(self.url, {"jsonrpc": "2.0", "method": "notifications/initialized",
                         "params": {}}, self.session, self.protocol)
        quotas, state = self.call("account_limits", {})
        if quotas is None:
            raise RuntimeError("PROVIDER_LIMITS_UNAVAILABLE")

    def call(self, name, args):
        if name not in ("account_limits", "wb_sku", "ozon_sku", "lk_wb_card_table"):
            raise RuntimeError("PROVIDER_TOOL_NOT_ALLOWED")
        if self.calls >= MAX_READS:
            raise RuntimeError("PROVIDER_CALL_LIMIT_EXCEEDED")
        self.calls += 1
        try:
            http, _, reply = _post(
                self.url, {"jsonrpc": "2.0", "id": self.calls + 100,
                           "method": "tools/call",
                           "params": {"name": name, "arguments": args}},
                self.session, self.protocol)
        except (urllib.error.URLError, TimeoutError, OSError):
            return None,"NETWORK_UNAVAILABLE"
        body, status = _unpack(reply)
        return body, (status if http < 400 else "HTTP_ERROR")


def _price_history(marketplace, store, sku):
    con = sqlite3.connect(DB.resolve().as_uri() + "?mode=ro",
                          uri=True, timeout=10)
    try:
        con.execute("PRAGMA query_only=ON")
        available = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='view' AND name='v_price_history'").fetchone()
        if not available:
            return None, "UNAVAILABLE"
        keys = {r[1] for r in con.execute("PRAGMA table_info(v_price_history)")}
        fields = ("event_date", "source_segment", "source_ordinal",
                  "old_price", "new_price", "list_price", "minimum_price",
                  "discount_percent")
        if not {"marketplace", "store", "marketplace_sku", *fields}.issubset(keys):
            return None, "UNAVAILABLE"
        rows = con.execute(
            """SELECT event_date, source_segment, source_ordinal,
                      old_price, new_price, list_price, minimum_price,
                      discount_percent FROM v_price_history
                 WHERE marketplace=? AND store=? AND marketplace_sku=?
                 ORDER BY event_date, source_segment, source_ordinal LIMIT 1001""",
            (marketplace, store, sku)).fetchall()
        if len(rows) > 1000:
            return None, "UNAVAILABLE"
        # Missing dates are deliberately ignored, never replaced with today.
        return ([dict(zip(fields, record)) for record in rows if record[0]],
                "VERIFIED_READONLY_VIEW")
    finally:
        con.close()


def format_checkpoint_conclusion(checkpoint, review_evidence):
    """Descriptive, evidence-gated conclusion for ONE registered checkpoint."""
    number = checkpoint.get("checkpoint_number", "?")
    source = checkpoint.get("provider_observations") or {}
    before = source.get("before") or {}
    after = source.get("after") or {}
    b, a = before.get("sales"), after.get("sales")
    if all(type(x) in (int, float) and x >= 0 for x in (b, a)):
        direction = ("выросли" if a > b else
                     "снизились" if a < b else "не изменились")
        pieces = ["оценочные заказы MPSTATS " + direction +
                  " (" + str(b) + " → " + str(a) + ")"]
    else:
        pieces = ["динамика оценочных заказов MPSTATS неизвестна"]
    norm = checkpoint.get("stock_normalized_orders") or {}
    if norm.get("status") in ("READY_LOW_SAMPLE", "READY_DESCRIPTIVE"):
        delta = norm.get("rate_percent_change")
        if type(delta) in (int, float):
            pieces.append("изменение заказов на день наличия " +
                          (f"{delta:+.1f}%").replace(".", ","))
        else:
            pieces.append("процентное изменение заказов на день наличия неизвестно")
        if norm.get("small_observed_sample") is True:
            pieces.append("выборка оценочных заказов мала")
    else:
        pieces.append("нормированная интенсивность заказов неизвестна")
    if norm.get("stock_coverage_differs") is True:
        pieces.append("дни наличия различаются")
    elif norm.get("stock_coverage_differs") is None:
        pieces.append("полная история дней наличия не подтверждена")
    count = review_evidence.get("observed_positive_text_entries")
    if type(count) is int and count >= 0:
        pieces.append("в источнике получено записей 4–5★ с текстом: " +
                      str(count) + " (полнота неизвестна)")
    else:
        pieces.append("количество полученных записей 4–5★ с текстом неизвестно")
    pieces.append("полное число новых положительных оценок и независимый "
                  "внешний спрос неизвестны; причинный эффект не доказан")
    return "Контроль " + str(number) + ": " + "; ".join(pieces) + "."

def _report_ozon_ratings(store,sku,day,provider_factory):
    """Same checkpoint/formula engine, Ozon-only source adapter.

    Ozon orders/revenue/price normalization is NOT certified by this rating
    research and is never populated with WB observations.
    """
    try:
        from apps.msp_self_analytics.sku_request import load_existing_series
        from apps.msp_self_analytics.series_analysis import analyze_series
        from apps.msp_self_analytics.marketplace_rating_sources import collect_rating_evidence
        from apps.msp_self_analytics.review_source_adapter import format_review_source_evidence_ru
    except ModuleNotFoundError:
        from sku_request import load_existing_series
        from series_analysis import analyze_series
        from marketplace_rating_sources import collect_rating_evidence
        from review_source_adapter import format_review_source_evidence_ru
    rows=load_existing_series(DB,marketplace='oz',store=store,sku=sku)
    if not any(row.get('review_date') for row in rows):
        return {'status':'NO_REGISTERED_REVIEW_DATES','marketplace':'oz',
                'text':'Ozon: в реестре нет зарегистрированной даты собственного отзыва. Дата покупки не подставляется; сравнение ДО/ПОСЛЕ не выполнялось.',
                'mpstats_calls':0,'history_checkpoint_count':0,
                'causal_effect_proven':False,'marketplace_actions_allowed':False}
    history=analyze_series(rows,as_of=day,requested_days=90)
    checkpoints=history['checkpoints']
    if not any(cp.get('windows') for cp in checkpoints):
        return {'status':'POST_WINDOW_PENDING','marketplace':'oz',
                'text':'Ozon: нет завершённых суток ПОСЛЕ зарегистрированных дат отзывов.',
                'mpstats_calls':0,'history_checkpoint_count':len(checkpoints),
                'causal_effect_proven':False,'marketplace_actions_allowed':False}
    client=provider_factory()
    collected=collect_rating_evidence(client,marketplace='oz',sku=sku,checkpoints=checkpoints,max_reads=MAX_READS,as_of=day)
    text=['OZON; магазин '+store+'. История оценок и отзывов по отдельным датам реестра.']
    for cp in checkpoints:
        stars=collected['star_summaries'].get(cp['checkpoint_number'])
        if stars:
            from apps.msp_self_analytics.rating_history_query import format_review_date_summary_ru
            text.append(format_review_date_summary_ru(stars))
        e=collected['evidence'].get(cp['checkpoint_number'])
        if e:text.append(format_review_source_evidence_ru(e))
        else:text.append('Контроль '+str(cp['checkpoint_number'])+': завершённое окно ещё недоступно.')
    text.append('Заказы, выручка и цены Ozon этим исследованием источников не подтверждены; значения WB не подставлялись. Полные новые 4–5★ неизвестны, независимые покупатели и причинный эффект не установлены. Денежная окупаемость отложена.')
    return {'status':'OBSERVATIONAL_REPORT_PARTIAL','marketplace':'oz','text':'\n'.join(text),
            'review_source_evidence':collected['evidence'],'star_summaries':collected['star_summaries'],'mpstats_calls':client.calls,
            'history_checkpoint_count':len(checkpoints),'order_history_status':'OZON_FULL_METRICS_NOT_VERIFIED',
            'causal_effect_proven':False,'marketplace_actions_allowed':False}


def report_card(marketplace, store, sku, *, as_of=None,
                provider_factory=MpstatsReader):
    """Return the owner's Russian report; suitable for an authorized Hermes reply.

    Do not publish raw SKU or report to GitHub issue comments or public logs.
    """
    planner, resolve_listing, builder = _modules()
    # Authoritative catalog lookup: the owner can submit only a numeric SKU.
    # Never guess identity from an internal article or merge two listing keys.
    match = resolve_listing(DB, sku=sku, marketplace=marketplace, store=store)
    marketplace, store, sku = (
        match["marketplace"], match["store"], match["marketplace_sku"])
    day = as_of or dt.datetime.now(ZoneInfo("Europe/Moscow")).date().isoformat()
    from apps.msp_self_analytics.sku_request import load_existing_series
    try:
        registered=load_existing_series(DB,marketplace=marketplace,store=store,sku=sku)
    except ValueError as exc:
        if str(exc)!='SKU_HAS_NO_RECORDED_PURCHASES':raise
        registered=[]
    if not any(row.get('review_date') for row in registered):
        from apps.msp_self_analytics.rating_history_query import query_history, format_history_ru
        client=provider_factory()
        last=dt.date.fromisoformat(day)-dt.timedelta(days=1)
        history=query_history(client,marketplace=marketplace,sku=sku,
            d1=(last-dt.timedelta(days=89)).isoformat(),d2=last.isoformat(),as_of=day)
        return {'status':'NO_REGISTERED_REVIEW_DATES','marketplace':marketplace,'store':store,
            'text':('Карточка '+sku+'; магазин '+store+'. В реестре нет зарегистрированной даты '
                    'собственного отзыва. Сравнение до/после не выполнено; дата покупки не подставляется. '
                    'Укажите дату отзыва для сравнения. Ниже только история оценок за последние 90 завершённых дней.\n'+format_history_ru(history)),
            'rating_history':history,'mpstats_calls':client.calls,'causal_effect_proven':False,
            'marketplace_actions_allowed':False}
    if marketplace=="oz":
        return _report_ozon_ratings(store,sku,day,provider_factory)
    selected = planner(DB, marketplace=marketplace, store=store, sku=sku,
                       as_of=day, max_checkpoints=12, max_provider_reads=MAX_READS)
    if selected["status"] == "OZON_PROVIDER_MAPPING_NOT_YET_VERIFIED":
        return {"status": "OZON_PROVIDER_NOT_READY",
                "text": "Для Ozon пока не проверена структура исторического источника MPSTATS. Данные WB подставлять нельзя.",
                "mpstats_calls": 0}
    plan = selected["analysis_plan"]
    if plan["provider_read_count"] == 0:
        return {"status": plan["status"],
                "text": "Для этой карточки пока нет завершённых периодов после записанных дат отзывов.",
                "mpstats_calls": 0}
    if plan["provider_read_count"] > MAX_READS:
        raise RuntimeError("PROVIDER_CALL_LIMIT_EXCEEDED")
    client = provider_factory()
    from apps.msp_self_analytics.marketplace_rating_sources import collect_rating_evidence
    preliminary=builder(selected["rows_for_local_analysis_only"], {}, as_of=day, requested_days=90)
    # Ratings are mandatory; optional full/keyword metrics use the remaining
    # shared budget, not the other way around.
    collected=collect_rating_evidence(client,marketplace='wb',sku=sku,
        checkpoints=preliminary['history']['checkpoints'],max_reads=MAX_READS,as_of=day)
    observations = {}
    passed = 0
    for request in plan["requests"]:
        payload,state=(None,"CALL_BUDGET")
        if client.calls<MAX_READS:
            payload, state = client.call(
                "wb_sku", {"sku": int(sku), "report": "full",
                           "d1": request["d1"], "d2": request["d2"]})
        stats = _period_stats(payload)
        observations[request["key"]] = dict(
            request_status=state,
            d1=request["d1"], d2=request["d2"],
            **{f: stats.get(f) for f in (
                "sales", "revenue", "days_in_stock", "sales_estimated",
                "revenue_estimated", "purchase", "purchase_after_return",
                "lost_profit")})
        if state in ("PASS_JSON", "PASS_STRUCTURED") and stats:
            passed += 1
    from apps.msp_self_analytics.own_order_reconciliation import fetch_own_wb_orders, format_own_orders_ru
    review_sources=collected['evidence'];dated_ratings=collected['dated_rating_sources']
    dated_activity={number:{'status':'UNAVAILABLE','reason':'WB_DAILY_NEW_REVIEWS_NOT_VERIFIED'} for number in review_sources}
    own_sources={};own_text=[]
    for cp in preliminary['history']['checkpoints']:
        windows=cp.get('windows')
        if not windows:continue
        b=fetch_own_wb_orders(sku=sku,store=store,**windows["before"])
        a=fetch_own_wb_orders(sku=sku,store=store,**windows["after"])
        own_sources[cp["checkpoint_number"]]={"before":b,"after":a}
        own_text.append(format_own_orders_ru(b,a))
    if client.calls<MAX_READS:
        lk_data,lk_state=client.call("lk_wb_card_table",{
            "type":"articles","value":str(sku),"period_type":"90days","self_redemption":False})
        # Never trust aggregate cabinet scope or guess a new field mapping.
        lk_status=("Недоступна: отказ или ошибка доступа MCP"
                   if lk_state in ("TOOL_ERROR","HTTP_ERROR","NETWORK_UNAVAILABLE") else
                   "Ответ получен, но кабинет, поля и историческая семантика не подтверждены")
        for evidence in review_sources.values():evidence["lk_status"]=lk_status
    # Additional read-only MPSTATS observation: exact historical days and
    # provider-labelled client_price, never seller edits or actual paid price.
    # Skip rather than overflow the per-request MPSTATS call budget.
    provider_keyword_rows = {}
    extra_price_status = "NOT_READ_CALL_BUDGET"
    if client.calls + len(plan["requests"]) <= MAX_READS:
        from apps.msp_self_analytics import external_visibility_evidence as _mpstats_external
        extra_price_status = "CHECKED_PROVIDER_SPARSE_HISTORY"
        for request in plan["requests"]:
            content, state = client.call("wb_sku", {
                "sku": int(sku), "report": "keywords",
                "d1": request["d1"], "d2": request["d2"]})
            provider_keyword_rows[request["key"]] = (
                _mpstats_external.analyze_keyword_history(
                    content if state in ("PASS_JSON", "PASS_STRUCTURED") else None,
                    d1=request["d1"], d2=request["d2"]))
    prices, price_status = _price_history(marketplace, store, sku)
    assembled = builder(
        selected["rows_for_local_analysis_only"], observations, as_of=day,
        price_events=prices, price_source_status=price_status,
        verified_unit_costs=None, requested_days=90,
        max_checkpoints=12, max_provider_reads=MAX_READS, review_source_evidence=review_sources, own_order_sources=own_sources,
        dated_rating_sources=dated_ratings,dated_review_activity_sources=dated_activity)
    price_observations_text=[]
    if provider_keyword_rows:
        for checkpoint in assembled["history"]["checkpoints"]:
            number=checkpoint["checkpoint_number"]
            refs=plan["checkpoint_to_requests"].get(number)
            if not isinstance(refs,dict):continue
            before=provider_keyword_rows.get(refs.get("before"))
            after=provider_keyword_rows.get(refs.get("after"))
            rendered=_mpstats_external.format_keyword_price_observations_ru(
                before, after, max_changes=10)
            price_observations_text.append(
                "Контроль "+str(number)+", внешняя история MPSTATS:\n"+rendered)
    else:
        price_observations_text.append(
            "Внешний ряд MPSTATS client_price: не запрашивался из-за "+
            "ограничения количества вызовов; неизвестно не означает постоянную цену.")
    conclusions=[format_checkpoint_conclusion(cp,review_sources.get(cp["checkpoint_number"],{})) for cp in assembled["history"]["checkpoints"]]
    from apps.msp_self_analytics.rating_history_query import format_review_date_summary_ru
    star_text='\n'.join(format_review_date_summary_ru(s) for s in collected['star_summaries'].values())
    return {
        "status": assembled["status"],
        "text": ('ОЦЕНКИ ПО ЗВЁЗДАМ\n'+star_text+'\n'+"Карточка определена по каталогу: " + marketplace.upper() +
                 "; магазин " + store + ".\n" + assembled["human_readable_ru"] + "\n" + "\n".join(price_observations_text)+"\n"+"\n".join(own_text)+"\n"+"\n".join(conclusions)+"\nЕдиный итог: оценка заказов MPSTATS описательна, внешние независимые заказы после очистки и сверки не установлены. Найденные положительные отзывы не доказывают независимый спрос или причинный эффект. Денежная окупаемость отложена."),
        "review_source_evidence":assembled["review_source_evidence"],
        "star_summaries":collected['star_summaries'],
        "nonfinancial_outcome":assembled["nonfinancial_outcome"],
        "own_order_sources":own_sources,
        "provider_windows": len(plan["requests"]),
        "provider_windows_with_data": passed,
        "mpstats_calls": client.calls,
        "external_client_price_status": extra_price_status,
        "history_checkpoint_count": len(assembled["history"]["checkpoints"]),
        "planned_total_per_card": assembled["history"]["series"]["planned_total_per_card"],
        "registered_purchase_rows": assembled["history"]["series"]["recorded_completed_purchase_rows"],
        "causal_effect_proven": False,
        "marketplace_actions_allowed": False,
    }


def main():
    p = argparse.ArgumentParser(description="Исторический анализ самовыкупов по SKU (только чтение)")
    p.add_argument("--marketplace", choices=["wb", "oz"], help="Необязательно: определяется по каталогу")
    p.add_argument("--store", help="Необязательно: определяется по каталогу сопоставлений")
    p.add_argument("--sku", required=True)
    p.add_argument("--json", action="store_true", help="Локальный структурированный результат вместо текста")
    args = p.parse_args()
    try:
        out = report_card(args.marketplace, args.store, args.sku)
    except Exception as exc:
        allow = {"INVALID_CARD_IDENTITY", "UNSUPPORTED_MARKETPLACE",
                 "INVALID_STORE", "INVALID_WB_SKU", "INVALID_OZON_SKU",
                 "SKU_HAS_NO_RECORDED_PURCHASES", "SERIES_ROW_LIMIT_EXCEEDED",
                 "SKU_NOT_IN_PRODUCT_CATALOG", "CATALOG_CANDIDATE_LIMIT_EXCEEDED",
                 "INVALID_MARKETPLACE_SKU", "MARKETPLACE_DISAMBIGUATION_REQUIRED",
                 "STORE_DISAMBIGUATION_REQUIRED",
                 "CHECKPOINT_LIMIT_EXCEEDED", "PROVIDER_READ_LIMIT_EXCEEDED",
                 "PROVIDER_INITIALIZATION_FAILED", "PROVIDER_LIMITS_UNAVAILABLE",
                 "PROVIDER_CONFIG_INVALID", "PROVIDER_CALL_LIMIT_EXCEEDED"}
        reason = str(exc)
        message = {
            "STORE_DISAMBIGUATION_REQUIRED":
                "SKU найден в нескольких магазинах. Уточните магазин, чтобы не смешивать разные карточки.",
            "MARKETPLACE_DISAMBIGUATION_REQUIRED":
                "SKU найден на нескольких маркетплейсах. Уточните маркетплейс.",
            "SKU_NOT_IN_PRODUCT_CATALOG":
                "SKU отсутствует в действующем каталоге сопоставлений МСП.",
            "SKU_HAS_NO_RECORDED_PURCHASES":
                "Карточка найдена в каталоге, но завершённых самовыкупов пока не зарегистрировано.",
        }.get(reason, "Не удалось сформировать проверенный исторический отчёт. "
                      "Данные не изменены; сведения, которых нет, не подставлялись.")
        out = {"status": "REPORT_NOT_READY",
               "reason": reason if reason in allow else type(exc).__name__,
               "text": message}
    if args.json:
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(out["text"])
    if out["status"] in ("REPORT_NOT_READY", "OBSERVATIONAL_REPORT_PARTIAL"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
