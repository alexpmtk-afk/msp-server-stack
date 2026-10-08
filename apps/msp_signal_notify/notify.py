#!/usr/bin/env python3
"""Passive six-signal Telegram notifier. NO marketplace writes or getUpdates polling.

Reads only the Hermes channel_archive SQLite database and reuses the existing
msp_data_sync outbound send_telegram(). For safety, test outcomes are explicitly
labeled simulated; only the price signal receives a conservative advisory.
"""
from __future__ import annotations
import argparse
import hashlib
import os
import re
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from apps.msp_data_sync.run_with_alerts import send_telegram

CHANNEL_ID = "-1003375632914"
ARCHIVE_PATH = Path("/home/hermes/.hermes/channel-archive/messages.sqlite3")
STATE_PATH = Path("/opt/mcp/data/msp/msp_signal_notifications.sqlite3")
SIGNALS = (
    ("SIG-002", "Поднять цену", r"\bподнять\s+цен[уы]\b"),
    ("SIG-016", "Нужно обнулить FBS для распродажи FBO",
     r"\bнужно\s+обнулить\s+fbs\b"),
    ("SIG-015", "Карточки с обнулёнными остатками",
     r"\bкарточки\s+с\s+обнуленн\w*\s+остатк\w*"),
    ("SIG-021", "Превышен расход по РК",
     r"\bпревышен\s+расход\s+по\s+рк\b"),
    ("SIG-022", "Аномально высокий ДРР",
     r"\bаномально\s+высокий\s+дрр\b"),
    ("SIG-032", "Расхождение размеров или веса",
     r"\bрасхождени\w*\s+(?:в\s+)?размер\w*|\bрасхождени\w*.*\bвес\w*"),
)
SIMULATIONS = {
    "SIG-016": "FBS обнулён для указанных товаров (имитация).",
    "SIG-015": "Исключения проверены, необходимые остатки восстановлены (имитация).",
    "SIG-021": "Рекламная кампания поставлена на паузу (имитация).",
    "SIG-022": "Рекламная кампания поставлена на паузу (имитация).",
    "SIG-032": "Характеристики товаров обновлены (имитация).",
}
SKU = re.compile(r"\((\d{5,15})\)")
COVER = re.compile(r"(?<!\w)_(\d{1,3})(?!\d)")
DATE = re.compile(r"(?<!\d)(?:\d{4}-\d{2}-\d{2}|\d{1,2}\.\d{1,2}(?:\.\d{4})?)(?!\d)")
MSK = ZoneInfo("Europe/Moscow")


def normalized(text: str) -> str:
    return text.lower().replace("ё", "е")


def identify(text: str):
    """Only six reviewed types, never the separate TEST/other unreviewed cards."""
    head = normalized(text[:1600])
    if re.search(r"\bтест\s+поднять\s+цен[уы]\b", head):
        return None
    for code, title, pattern in SIGNALS:
        if re.search(pattern, head, re.IGNORECASE | re.DOTALL):
            return code, title
    return None


def parse_date(raw: str, today: date):
    try:
        if "-" in raw:
            value = date.fromisoformat(raw)
        else:
            bits = [int(x) for x in raw.split(".")]
            value = date(bits[2] if len(bits) == 3 else today.year, bits[1], bits[0])
        # A past date may be stale or a year-ambiguous planned arrival.
        return value if value >= today else None
    except (ValueError, TypeError):
        return None


def price_advice(text: str, today: date) -> list[str]:
    """Require explicit SKU, _N coverage days and inbound date on the same row.

    No inference of missing quantities or dates. A signal may contain items on
    multiple lines; uncertain items must be flagged rather than invented.
    """
    results, seen = [], set()
    for line in text.splitlines():
        ids = SKU.findall(line)
        if not ids:
            continue
        days = COVER.search(line)
        candidates = [parse_date(x, today) for x in DATE.findall(line)]
        arrivals = [d for d in candidates if d is not None]
        for market_sku in ids:
            if market_sku in seen:
                continue
            seen.add(market_sku)
            if not days or not arrivals:
                results.append(f"SKU {market_sku}: недостаточно данных для решения (нужны _N дней и дата поступления).")
                continue
            coverage = int(days.group(1))
            limit = today + timedelta(days=coverage)
            arrival = min(arrivals)
            choice = "НЕ поднимать цену" if arrival <= limit else "РЕКОМЕНДУЕТСЯ поднять цену"
            results.append(f"SKU {market_sku}: {choice}; запас {coverage} дн., поступление {arrival:%d.%m.%Y}, граница {limit:%d.%m.%Y}.")
    if not results:
        return ["Не удалось однозначно разобрать товары, дни покрытия и даты поступления; необходима проверка исходного сигнала."]
    return results


def format_report(code: str, title: str, content: str, message_id: int, today: date) -> str:
    link = f"https://t.me/c/{CHANNEL_ID[4:]}/{message_id}"
    lines = [
        "МСП | ТЕСТОВАЯ ОТРАБОТКА СИГНАЛА",
        "Источник: Сигналы МП",
        f"Тип: {title} ({code})",
        f"Оригинал: {link}",
        "Статус: ИМИТАЦИЯ. Реальных действий на маркетплейсах нет.",
    ]
    if code == "SIG-002":
        lines.extend(["Рекомендация по товарам:"] + ["— " + x for x in price_advice(content, today)])
    else:
        lines.append("Действие: " + SIMULATIONS[code])
        excerpt = " ".join(content.split())
        if excerpt:
            lines.append("Исходное сообщение: " + excerpt[:1000])
    return "\n".join(lines)


def connect_state(path: Path):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15)
    os.chmod(path, 0o600)
    db.execute("""CREATE TABLE IF NOT EXISTS meta (
      key TEXT PRIMARY KEY, value TEXT NOT NULL)""")
    db.execute("""CREATE TABLE IF NOT EXISTS notifications (
      chat_id TEXT NOT NULL, message_id INTEGER NOT NULL,
      fingerprint TEXT NOT NULL, telegram_message_id INTEGER NOT NULL,
      sent_utc TEXT NOT NULL, PRIMARY KEY (chat_id,message_id))""")
    db.commit()
    return db


def connect_archive(path: Path):
    if not path.is_file():
        raise RuntimeError("Hermes signal archive missing")
    return sqlite3.connect("file:" + str(path) + "?mode=ro", uri=True, timeout=15)


def meta(db, key: str):
    row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def set_meta(db, key, value):
    db.execute("INSERT INTO meta(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
               (key, str(value)))


def run_once(archive_path=ARCHIVE_PATH, state_path=STATE_PATH, sender=None, today=None):
    """On first call baseline existing history, later send only new/revised posts."""
    sender = sender or send_telegram
    today = today or datetime.now(MSK).date()
    now = datetime.now(timezone.utc)
    stats = {"initialized": False, "recognized": 0, "sent": 0, "duplicate": 0}
    with connect_archive(Path(archive_path)) as archive, connect_state(Path(state_path)) as state:
        baseline = meta(state, "baseline_message_id")
        if baseline is None:
            found = archive.execute("SELECT COALESCE(MAX(message_id),0) FROM messages WHERE chat_id=?", (CHANNEL_ID,)).fetchone()
            set_meta(state, "baseline_message_id", found[0])
            set_meta(state, "scan_utc", now.isoformat(timespec="seconds").replace("+00:00", "Z"))
            state.commit()
            stats["initialized"] = True
            return stats
        last_scan = meta(state, "scan_utc")
        assert last_scan, "state scan time missing"
        # Include a safety overlap to avoid losing inserts near a timestamp boundary.
        lower = (datetime.fromisoformat(last_scan.replace("Z", "+00:00")) -
                 timedelta(seconds=120)).isoformat(timespec="seconds").replace("+00:00", "Z")
        rows = archive.execute(
            "SELECT message_id,text FROM messages WHERE chat_id=? AND message_id>? "
            "AND last_received_utc>=? ORDER BY message_id",
            (CHANNEL_ID, int(baseline), lower)).fetchall()
        for mid, content in rows:
            sig = identify(content)
            if sig is None:
                continue
            stats["recognized"] += 1
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            old = state.execute("SELECT fingerprint FROM notifications WHERE chat_id=? AND message_id=?",
                                (CHANNEL_ID, mid)).fetchone()
            if old and old[0] == digest:
                stats["duplicate"] += 1
                continue
            report = format_report(*sig, content, mid, today)
            delivered = sender(report)
            if not isinstance(delivered, int) or delivered <= 0:
                raise RuntimeError("Telegram delivery confirmation missing")
            state.execute(
                "INSERT INTO notifications VALUES (?,?,?,?,?) "
                "ON CONFLICT(chat_id,message_id) DO UPDATE SET fingerprint=excluded.fingerprint,"
                "telegram_message_id=excluded.telegram_message_id,sent_utc=excluded.sent_utc",
                (CHANNEL_ID, mid, digest, delivered, now.isoformat(timespec="seconds")))
            state.commit()
            stats["sent"] += 1
        set_meta(state, "scan_utc", now.isoformat(timespec="seconds").replace("+00:00", "Z"))
        state.commit()
    return stats


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--once", action="store_true", help="single scan then exit")
    p.add_argument("--interval", type=int, default=5, help="poll delay in seconds")
    args = p.parse_args()
    if os.environ.get("MSP_SIGNAL_TEST_MODE") != "1":
        raise SystemExit("MSP_SIGNAL_TEST_MODE required; refusing to send")
    if not os.environ.get("MSP_ALERT_CHAT_ID") or not os.environ.get("MSP_ALERT_THREAD_ID"):
        raise SystemExit("Telegram destination not configured")
    if args.interval < 2:
        raise SystemExit("Minimum poll interval is 2 seconds")
    while True:
        try:
            stats = run_once()
            print("SIGNAL_SCAN " + " ".join(f"{k}={v}" for k, v in stats.items()), flush=True)
        except Exception as e:
            # Telegram bot credentials and URLs must never appear in logs.
            print("SIGNAL_SCAN_ERROR=" + type(e).__name__, flush=True)
            if args.once:
                raise SystemExit(1) from None
        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
