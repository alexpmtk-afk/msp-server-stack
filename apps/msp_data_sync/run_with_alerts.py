#!/usr/bin/env python3
"""Daily MSP sync: run all sources, send state-change alerts to a fixed Telegram topic.

Only existing Hermes Bot API token is used, never getUpdates / polling.
The protected environment file is installed on REMOTE, outside git.
"""
import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SOURCES = ("product_catalog", "self_purchase", "price_journal_current", "price_journal_archive")
DISPLAY = {
    "product_catalog": "Каталог товаров",
    "self_purchase": "Самовыкупы",
    "price_journal_current": "Журнал изменения цен",
    "price_journal_archive": "Журнал изменения цен (архив)",
    "sync_runner": "Запуск синхронизации",
}
BAD = {"partial", "failed"}
GOOD = {"success", "unchanged_snapshot", "not_modified"}


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def send_telegram(text):
    token = os.environ.get("MSP_ALERT_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat = os.environ["MSP_ALERT_CHAT_ID"]
    thread = os.environ["MSP_ALERT_THREAD_ID"]
    if not token or not chat.startswith("-100") or not thread.isdigit():
        raise ValueError("invalid telegram alert destination (no token printed)")
    payload = urllib.parse.urlencode({
        "chat_id": chat,
        "message_thread_id": thread,
        "text": text[:3900],
        "disable_web_page_preview": "true",
    }).encode()
    # NEVER print the exception or request URL: Telegram bot token is in its path.
    request = urllib.request.Request(
        "https://api.telegram.org/bot" + token + "/sendMessage",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            answer = json.load(response)
    except Exception:
        raise RuntimeError("Telegram Bot API delivery failed (secret redacted)") from None
    if not answer.get("ok"):
        raise RuntimeError("Telegram Bot API refused delivery (secret redacted)")
    result = answer.get("result", {})
    if (str(result.get("chat", {}).get("id")) != chat or
            str(result.get("message_thread_id")) != thread):
        raise RuntimeError("Telegram delivered to unexpected destination")
    return result.get("message_id")


def latest_issues(connection, source):
    """A separate per-run table preserves exact row errors even with deduped sync_error."""
    try:
        record = connection.execute(
            "select run_id from sync_run where source=? order by run_id desc limit 1", (source,)
        ).fetchone()
        if record is None:
            return []
        rows = connection.execute(
            "select source_row,error from sync_run_issue where run_id=? order by source_row,error limit 30",
            (record[0],),
        ).fetchall()
        return [(row or 0, message[:135]) for row, message in rows]
    except sqlite3.Error:
        return []


def signature(source, result, issues):
    """No timestamps or volume counters: same persistent problem => one alert."""
    body = {
        "source": source,
        "status": result["status"],
        "issues": issues,
        "rejected": result.get("rejected", 0),
        "failed": str(result.get("error", ""))[:135] if result["status"] == "failed" else "",
    }
    return hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def make_message(source, result, issues, recovering=False):
    name = DISPLAY.get(source, source)
    if recovering:
        return "МСП | ВОССТАНОВЛЕНО\nИсточник: " + name + "\nСинхронизация снова работает без ошибок."
    status = result["status"]
    headline = "МСП | ПОЛНЫЙ СБОЙ" if status == "failed" else "МСП | ПРЕДУПРЕЖДЕНИЕ"
    lines = [headline, "Источник: " + name, "Статус: " + status]
    if status == "partial":
        lines.append("Отклонено строк: " + str(result.get("rejected", 0)))
        if result.get("source_rows") is not None:
            lines.append("Обработано строк: " + str(result["source_rows"]))
        lines.append("Корректные записи сохранены.")
    elif result.get("error"):
        lines.append("Причина: " + str(result["error"]).replace("\n", " ")[:200])
    if issues:
        lines.append("Строки и причины:")
        lines.extend(("— №" + str(row) if row else "— источник") + ": " +
                     reason.replace("\n", " ") for row, reason in issues[:12])
        if len(issues) > 12:
            lines.append("И другие ошибки (см. SQLite sync_run_issue).")
    return "\n".join(lines)


def notify_one(connection, business_connection, source, result):
    status = result.get("status", "failed")
    if status not in BAD | GOOD:
        raise ValueError("unknown sync status, refusing to alter alert state")
    issues = latest_issues(business_connection, source) if status in BAD else []
    fp = signature(source, result, issues) if status in BAD else None
    row = connection.execute(
        "select state,fingerprint from alert_delivery_state where source=?", (source,)
    ).fetchone()
    state, previous_fp = row if row else ("ok", None)
    if status in GOOD and state == "ok":
        return "silent-ok"
    if status in BAD and state == "problem" and previous_fp == fp:
        return "suppressed-duplicate"
    message = make_message(source, result, issues, recovering=status in GOOD)
    message_id = send_telegram(message)
    connection.execute(
        "insert into alert_delivery_state(source,state,fingerprint,last_sent_at,last_message_id) "
        "values(?,?,?,?,?) on conflict(source) do update set "
        "state=excluded.state,fingerprint=excluded.fingerprint,"
        "last_sent_at=excluded.last_sent_at,last_message_id=excluded.last_message_id",
        (source, "problem" if status in BAD else "ok", fp, utc_now(), message_id),
    )
    connection.commit()
    return "sent-" + ("problem" if status in BAD else "recovered")


def run_alerts(db_path, business_db_path, results):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path, timeout=20)
    business = sqlite3.connect('file:' + str(business_db_path) + '?mode=ro', uri=True, timeout=15)
    try:
        con.execute("create table if not exists alert_delivery_state("
                    "source text primary key,state text not null,"
                    "fingerprint text,last_sent_at text,last_message_id integer)")
        con.commit()
        for result in results:
            source = result.get("source", "sync_runner")
            if source not in SOURCES and source != "sync_runner":
                raise ValueError("unknown source")
            outcome = notify_one(con, business, source, result)
            print("ALERT " + source + " " + outcome, file=sys.stderr, flush=True)
    finally:
        business.close()
        con.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--db")
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    main_db = args.db or os.getenv("MSP_DATA_DB") or config["database_path"]
    command = [sys.executable, str(Path(__file__).with_name("sync.py")),
               "--config", args.config, "--source", "all", "--db", main_db]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=300)
        if proc.stdout:
            print(proc.stdout, end="", flush=True)
        if proc.stderr:
            print(proc.stderr[:1500], file=sys.stderr, flush=True)
        try:
            data = json.loads(proc.stdout)
            results = data.get("sync", [])
            if not isinstance(results, list) or len(results) != 4 or {
                r.get("source") for r in results
            } != set(SOURCES):
                raise ValueError("invalid sync result source coverage")
        except (ValueError, TypeError, AttributeError):
            results = [{"source": "sync_runner", "status": "failed",
                        "error": "Failed to obtain complete synchronization report"}]
        code = proc.returncode
    except Exception:
        print("Sync process could not start or timed out", file=sys.stderr)
        results = [{"source": "sync_runner", "status": "failed",
                    "error": "Sync process could not start or timed out"}]
        code = 1
    if os.environ.get("MSP_ALERTS_ENABLED") != "1":
        print("ALERTS_DISABLED: system not fully configured", file=sys.stderr)
        return 1
    required = ("MSP_ALERT_CHAT_ID", "MSP_ALERT_THREAD_ID")
    if (not (os.environ.get("MSP_ALERT_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")) or
            any(not os.environ.get(k) for k in required)):
        print("ALERTS_MISSING_PROTECTED_CONFIGURATION", file=sys.stderr)
        return 1
    try:
        run_alerts(os.path.join(os.path.dirname(main_db), "msp_alert_delivery.sqlite3"), main_db, results)
    except Exception as exc:
        print("ALERT_DELIVERY_FAILURE=" + type(exc).__name__, file=sys.stderr)
        return 1
    # Never hide a real partial/failed source as a successful service run.
    return code if code else (1 if any(r.get("status") in BAD for r in results) else 0)


if __name__ == "__main__":
    raise SystemExit(main())
