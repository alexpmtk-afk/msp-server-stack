"""Single-decision Orgobot price trial: human-only, bounded, fail-closed.

This module is not a general price editor. For acceptance it can act ONLY on
Orgobot decision 169 (rule 48, article 1970428469, +25%, source #2701).
It does nothing unless a pre-reviewed one-use card was sent and clicked.
"""
from __future__ import annotations

import datetime as dt
import decimal
import json
import os
import secrets
import sqlite3
from contextlib import closing
from pathlib import Path

from apps.msp_signal_notify.price_buttons import OrgobotMCP, DecisionRefused

DB = Path("/opt/mcp/data/msp/msp_orgobot_live_trial.sqlite3")
TARGET = {
    "id": 169,
    "orgobot_id": 48,
    "market_article": "1970428469",
    "marketplaceid_id": 1,
    "blockid_id": 1,
    "post_id": 2701,
    "percent": "25.00",
}
CHAT_ID = -1002485321031
THREAD_ID = 758


def connect(path=DB):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    conn = sqlite3.connect(p, timeout=15)
    os.chmod(p, 0o600)
    conn.execute("""CREATE TABLE IF NOT EXISTS trials(
       nonce TEXT PRIMARY KEY, decision_id INTEGER NOT NULL UNIQUE,
       allowed_users TEXT NOT NULL, sent_message_id INTEGER,
       state TEXT NOT NULL, answer TEXT, command_id INTEGER,
       created_utc TEXT NOT NULL, expires_utc TEXT NOT NULL
    )""")
    conn.commit()
    return conn


def _now():
    return dt.datetime.now(dt.timezone.utc)


def create_card(allowed_user_ids, path=DB, clock=None):
    """Prepare a single card; no QRsite writes. Requires explicit numeric allowlist."""
    users = sorted({int(v) for v in allowed_user_ids if str(v).isdecimal() and int(v) > 0})
    if len(users) != 1:
        raise DecisionRefused("Для реального теста требуется ровно один уполномоченный Telegram-пользователь.")
    created = clock or _now()
    with closing(connect(path)) as db:
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute("SELECT nonce,sent_message_id,state,expires_utc,allowed_users "
                              "FROM trials WHERE decision_id=?",
                              (TARGET["id"],)).fetchone()
        if existing:
            if (existing[2] != "waiting"
                    or created > dt.datetime.fromisoformat(existing[3])
                    or json.loads(existing[4]) != users):
                raise DecisionRefused("Решение уже занято, просрочено или связано с другим пользователем.")
            return existing[0], existing[1]
        nonce = secrets.token_hex(16)
        db.execute("INSERT INTO trials(nonce,decision_id,allowed_users,state,created_utc,expires_utc)"
                   " VALUES(?,?,?,?,?,?)",
                   (nonce, TARGET["id"], json.dumps(users), "waiting", created.isoformat(),
                    (created + dt.timedelta(hours=12)).isoformat()))
        db.commit()
    return nonce, None


def markup(nonce):
    if not isinstance(nonce, str) or len(nonce)!=32 or not all(c in "0123456789abcdef" for c in nonce):
        raise DecisionRefused("Неверный ключ подтверждения.")
    return {"inline_keyboard": [[
        {"text": "Да — повысить на 25%", "callback_data": "msp3:" + nonce + ":y"},
        {"text": "Нет — отказать", "callback_data": "msp3:" + nonce + ":n"},
    ]]}


def bind_message(nonce, telegram_message_id, path=DB):
    if type(telegram_message_id) is not int or telegram_message_id <= 0:
        raise DecisionRefused("Telegram не подтвердил отправку реальной карточки.")
    with closing(connect(path)) as db:
        db.execute("BEGIN IMMEDIATE")
        changed = db.execute("UPDATE trials SET sent_message_id=? WHERE nonce=? AND "
                             "sent_message_id IS NULL AND state='waiting'",
                             (telegram_message_id, nonce)).rowcount
        db.commit()
    if changed != 1:
        raise DecisionRefused("Не удалось однозначно привязать сообщение.")


def _owner_ok(raw, bot_username):
    if not bot_username or not isinstance(bot_username, str):
        return False
    vals = [raw] if isinstance(raw, (str, dict)) else raw
    if not isinstance(vals, list):
        return False
    names = []
    for v in vals:
        if isinstance(v, dict):
            v = v.get("username") or v.get("telegram") or ""
        names += str(v).replace(";", ",").replace(" ", ",").split(",")
    return bot_username.lower().lstrip("@") in [str(x).lower().strip().lstrip("@") for x in names]


def _is_target(row, bot_username):
    if not isinstance(row, dict):
        return False
    for name in ("id", "orgobot_id", "marketplaceid_id", "blockid_id", "post_id"):
        value = row.get(name)
        if isinstance(value, bool) or not str(value).isdecimal() or int(value) != TARGET[name]:
            return False
    if str(row.get("market_article") or "") != TARGET["market_article"]:
        return False
    if str(row.get("status")) != "waiting":
        return False
    try:
        if decimal.Decimal(str(row.get("percent"))) != decimal.Decimal(TARGET["percent"]):
            return False
    except decimal.InvalidOperation:
        return False
    return _owner_ok(row.get("responsible_telegram"), bot_username)


def _get_fresh_target(client, bot_username):
    data = client.call("orgobot_price_decisions_list", {"limit": 200})
    rows = data.get("results") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise DecisionRefused("Orgobot не вернул проверяемый список решений.")
    matched = [r for r in rows if str(r.get("id")) == str(TARGET["id"])]
    if len(matched) != 1 or not _is_target(matched[0], bot_username):
        raise DecisionRefused("Решение изменилось либо не назначено этому Hermes Bot.")
    return matched[0]


def confirm(data, user_id, chat_id, thread_id, message_id, bot_username,
            client_factory=OrgobotMCP, path=DB, clock=None):
    """At most one orgobot_price_decide, ONLY after authorized Telegram click."""
    import re
    match = re.fullmatch(r"msp3:([0-9a-f]{32}):([yn])", data or "")
    if not match:
        raise DecisionRefused("Неверная кнопка.")
    if (int(chat_id), int(thread_id)) != (CHAT_ID, THREAD_ID):
        raise DecisionRefused("Неверная Telegram-группа или тема.")
    nonce, letter = match.groups()
    stamp = clock or _now()
    with closing(connect(path)) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT decision_id,allowed_users,sent_message_id,state,expires_utc "
                         "FROM trials WHERE nonce=?", (nonce,)).fetchone()
        if not row or row[2] != int(message_id) or row[0] != TARGET["id"]:
            raise DecisionRefused("Кнопка не соответствует утверждённому решению.")
        if int(user_id) not in json.loads(row[1]):
            raise DecisionRefused("Вы не уполномочены принимать это решение.")
        if row[3] != "waiting":
            raise DecisionRefused("Решение уже принято или находится на проверке.")
        if stamp > dt.datetime.fromisoformat(row[4]):
            raise DecisionRefused("Срок действия подтверждения истёк.")
        db.execute("UPDATE trials SET state='processing',answer=? WHERE nonce=? AND state='waiting'",
                   ("yes" if letter=="y" else "no", nonce))
        db.commit()
    # Never retry a price command after any error or timeout: outcome may be unknown.
    try:
        client = client_factory()
        _get_fresh_target(client, bot_username)
        response = client.call("orgobot_price_decide", {
            "decision_id": TARGET["id"], "answer": "yes" if letter=="y" else "no"})
        command = response.get("command_id") if isinstance(response, dict) else None
        if isinstance(command, bool) or not str(command).isdecimal() or int(command) <= 0:
            raise DecisionRefused("Нет числового command_id от Orgobot.")
        with closing(connect(path)) as db:
            db.execute("UPDATE trials SET state='queued',command_id=? WHERE nonce=? AND state='processing'",
                       (int(command), nonce))
            db.commit()
        return int(command)
    except Exception:
        with closing(connect(path)) as db:
            db.execute("UPDATE trials SET state='needs_review' WHERE nonce=? AND state='processing'", (nonce,))
            db.commit()
        raise DecisionRefused("Результат неизвестен; повтор запрещён до проверки Orgobot.") from None


def check_command(command_id, client_factory=OrgobotMCP, path=DB):
    """Read-only status probe (does not repeat price mutation)."""
    if isinstance(command_id, bool) or not str(command_id).isdecimal() or int(command_id) <= 0:
        raise DecisionRefused("Неизвестная команда.")
    with closing(connect(path)) as db:
        row = db.execute("SELECT state FROM trials WHERE command_id=? AND decision_id=?",
                         (int(command_id), TARGET["id"])).fetchone()
        if not row:
            raise DecisionRefused("Команда не принадлежит текущему тесту.")
    client=client_factory()
    d=client.call("orgobot_price_command_status", {"command_id": int(command_id)})
    status=d.get("status") if isinstance(d,dict) else None
    if status not in ("queued","processing","done","failed","blocked"):
        raise DecisionRefused("Orgobot вернул неизвестный статус.")
    with closing(connect(path)) as db:
        db.execute("UPDATE trials SET state=? WHERE command_id=? AND state IN ('queued','processing')",
                   (status,int(command_id)))
        db.commit()
    return status
