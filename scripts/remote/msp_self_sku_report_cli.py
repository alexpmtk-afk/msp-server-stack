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


def _modules():
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
        if name not in ("account_limits", "wb_sku"):
            raise RuntimeError("PROVIDER_TOOL_NOT_ALLOWED")
        self.calls += 1
        if self.calls > MAX_READS:
            raise RuntimeError("PROVIDER_CALL_LIMIT_EXCEEDED")
        http, _, reply = _post(
            self.url, {"jsonrpc": "2.0", "id": self.calls + 100,
                       "method": "tools/call",
                       "params": {"name": name, "arguments": args}},
            self.session, self.protocol)
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


def report_card(marketplace, store, sku, *, as_of=None, source_audit=None,
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
    observations = {}
    passed = 0
    for request in plan["requests"]:
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
    # Review observations take priority over optional keyword price context.
    from review_source_adapter import review_source_evidence
    from own_order_reconciliation import fetch_own_wb_orders, format_own_orders_ru
    review_sources={};own_sources={};own_text=[]
    comments,state_comments=(None,"CALL_BUDGET")
    if client.calls<MAX_READS:
        comments,state_comments=client.call("wb_sku",{"sku":int(sku),"report":"comments"})
    preliminary=builder(selected["rows_for_local_analysis_only"], observations, as_of=day, requested_days=90)
    for cp in preliminary["history"]["checkpoints"]:
        windows=cp.get("windows")
        if not windows or not windows.get("after"):continue
        period,state_period=(None,"CALL_BUDGET")
        if client.calls<MAX_READS:
            period,state_period=client.call("wb_sku",{"sku":int(sku),"report":"by_period","d1":cp["review_date"],"d2":windows["after"]["d2"]})
        review_sources[cp["checkpoint_number"]]=review_source_evidence(sku=sku,event_date=cp["review_date"],after_start=windows["after"]["d1"],after_end=windows["after"]["d2"],comments=comments,period=period,comments_status=state_comments,period_status=state_period,lk_status=(source_audit or {}).get("lk_status","UNKNOWN_ACCESS_NOT_VERIFIED"))
        b=fetch_own_wb_orders(sku=sku,store=store,**windows["before"])
        a=fetch_own_wb_orders(sku=sku,store=store,**windows["after"])
        own_sources[cp["checkpoint_number"]]={"before":b,"after":a}
        own_text.append(format_own_orders_ru(b,a))
    # Additional read-only MPSTATS observation: exact historical days and
    # provider-labelled client_price, never seller edits or actual paid price.
    # Skip rather than overflow the per-request MPSTATS call budget.
    provider_keyword_rows = {}
    extra_price_status = "NOT_READ_CALL_BUDGET"
    if client.calls + len(plan["requests"]) <= MAX_READS:
        import external_visibility_evidence as _mpstats_external
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
        max_checkpoints=12, max_provider_reads=MAX_READS, review_source_evidence=review_sources, own_order_sources=own_sources)
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
    conclusions=[]
    for checkpoint in assembled["history"]["checkpoints"]:
        index=checkpoint["checkpoint_number"]
        observations=checkpoint.get("provider_observations",{})
        before=observations.get("before",{});after=observations.get("after",{})
        counts=(before.get("sales"),after.get("sales"))
        normalized=checkpoint.get("stock_normalized_orders",{})
        rate=normalized.get("rate_percent_change")
        trend=("оценочные заказы не выросли" if counts[0] is not None and counts[1] is not None and counts[1]<=counts[0] else "динамика заказов требует сверки")
        evidence=review_sources.get(index,{})
        found=evidence.get("observed_positive_text_entries")
        conclusions.append("Контроль "+str(index)+": "+trend+"; изменение оценочной интенсивности "+(str(round(rate,1))+"%" if isinstance(rate,(int,float)) else "UNKNOWN")+". Получено положительных текстовых записей MPSTATS: "+str(found if found is not None else "UNKNOWN")+"; полнота и независимость авторов неизвестны. Подтверждённого роста независимого спроса/эффекта исходного самовыкупа нет; точная динамика новых 4–5★ UNKNOWN, выборка мала, наличие и наблюдения цен менялись.")
    return {
        "status": assembled["status"],
        "text": ("Карточка определена по каталогу: " + marketplace.upper() +
                 "; магазин " + store + ".\n" + assembled["human_readable_ru"] + "\n" + "\n".join(price_observations_text)+"\n"+"\n".join(own_text)+"\nЕДИНЫЙ НЕСТОИМОСТНОЙ ВЫВОД\n"+"\n".join(conclusions)+"\nДенежная окупаемость отложена."),
        "review_source_evidence":review_sources,
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
