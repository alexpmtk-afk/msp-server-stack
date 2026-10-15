"""SIG-002 per-item Telegram approval buttons; fail-closed Orgobot command bridge.

The notifier only SENDS buttons. Only the existing Hermes Telegram gateway
receives callbacks (via the companion scoped plugin). No getUpdates/webhook.
"""
from __future__ import annotations

import datetime as dt
from contextlib import closing
import json
import os
import re
import secrets
import sqlite3
import urllib.parse
import urllib.request
from pathlib import Path

DB_PATH = Path("/opt/mcp/data/msp/msp_signal_price_buttons.sqlite3")
TOKEN_RE = re.compile(r"^msp2:([0-9a-f]{24}):([yn])$")
MCP_URL = "https://qrbott.ru/mcp"
SCHEMA = """CREATE TABLE IF NOT EXISTS price_buttons (
    token TEXT PRIMARY KEY,
    source_message_id INTEGER NOT NULL,
    sku TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    sent_message_id INTEGER,
    created_utc TEXT NOT NULL,
    expires_utc TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'waiting',
    answer TEXT,
    decision_id TEXT,
    command_id TEXT,
    UNIQUE(source_message_id, sku, fingerprint)
)"""


class DecisionRefused(Exception):
    """User-facing rejection without disclosing secrets."""


def now_utc():
    return dt.datetime.now(dt.timezone.utc)


def connect(path=DB_PATH):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(p, timeout=20)
    os.chmod(p, 0o600)
    db.execute(SCHEMA)
    db.commit()
    return db


def reserve(db, source_id: int, sku: str, clock=None, fingerprint=''):
    """Issue opaque, non-guessable per-item token; don't reissue delivered buttons."""
    if not re.fullmatch(r"\d{5,15}", sku):
        raise ValueError("invalid SKU")
    db.execute("UPDATE price_buttons SET state='superseded' WHERE source_message_id=? AND sku=? "
               "AND fingerprint<>? AND state='waiting'", (source_id, sku, fingerprint))
    record = db.execute("SELECT token, sent_message_id FROM price_buttons "
                        "WHERE source_message_id=? AND sku=? AND fingerprint=?",
                        (source_id, sku, fingerprint)).fetchone()
    if record and record[1] is not None:
        return record[0], True
    if record:
        return record[0], False
    stamp = clock or now_utc()
    token = secrets.token_hex(12)
    db.execute("INSERT INTO price_buttons(token,source_message_id,sku,fingerprint,created_utc,expires_utc)"
               " VALUES(?,?,?,?,?,?)",
               (token, source_id, sku, fingerprint, stamp.isoformat(),
                (stamp + dt.timedelta(hours=48)).isoformat()))
    db.commit()
    return token, False


def bind_sent(db, token, telegram_message_id):
    if not isinstance(telegram_message_id, int) or telegram_message_id < 1:
        raise ValueError("missing Telegram message ID")
    db.execute("UPDATE price_buttons SET sent_message_id=? WHERE token=? AND sent_message_id IS NULL",
               (telegram_message_id, token))
    db.commit()


def markup(token):
    if not re.fullmatch(r"[0-9a-f]{24}", token):
        raise ValueError("invalid token")
    return {"inline_keyboard": [[
        {"text": "Да — поднять", "callback_data": "msp2:" + token + ":y"},
        {"text": "Нет — отклонить", "callback_data": "msp2:" + token + ":n"}
    ]]}


def _extract(obj):
    """Convert common MCP structuredContent / JSON text payloads to objects."""
    if not isinstance(obj, dict):
        raise DecisionRefused("Некорректный ответ MCP.")
    if obj.get("isError"):
        raise DecisionRefused("Orgobot MCP вернул ошибку.")
    if "structuredContent" in obj and isinstance(obj["structuredContent"], (dict, list)):
        return obj["structuredContent"]
    for item in obj.get("content", []):
        if item.get("type") == "text":
            try:
                return json.loads(item["text"])
            except (ValueError, TypeError):
                pass
    return obj


class OrgobotMCP:
    """Exact allowlisted QRsite MCP methods, with credential read only from REMOTE secret."""
    ALLOWED = frozenset({"orgobot_price_decisions_list",
                         "orgobot_price_decide", "orgobot_price_command_status"})

    def __init__(self, secret_path="/opt/mcp/secrets/andrey-qrsite.env"):
        raw = Path(secret_path).read_text(encoding="utf-8")
        values = {}
        for line in raw.splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip().strip("'\"")
        token = values.get("ANDREY_MCP_TOKEN", "")
        if not token.startswith("qr_"):
            raise DecisionRefused("Не настроен доступ Orgobot MCP.")
        self.token = token
        self.sid = None
        self.counter = 0
        self._post("initialize", {"protocolVersion": "2025-06-18",
                                  "capabilities": {},
                                  "clientInfo": {"name": "msp-sig002-approval", "version": "1.0"}},
                   notification=False)
        self._post("notifications/initialized", {}, notification=True)

    def _post(self, method, params, notification=False):
        self.counter += 1
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        if not notification:
            payload["id"] = self.counter
        headers = {"Authorization": "Bearer " + self.token,
                   "Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream",
                   "MCP-Protocol-Version": "2025-06-18"}
        if self.sid:
            headers["Mcp-Session-Id"] = self.sid
        request = urllib.request.Request(MCP_URL, data=json.dumps(payload).encode(),
                                         headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=20) as resp:
                self.sid = resp.headers.get("Mcp-Session-Id", self.sid)
                body = resp.read(1_000_000).decode("utf-8")
                if notification:
                    return {}
                if "text/event-stream" in resp.headers.get("Content-Type", ""):
                    events = [line[6:] for line in body.splitlines() if line.startswith("data: ")]
                    packet = next((json.loads(line) for line in reversed(events)
                                   if line.startswith("{")), None)
                else:
                    packet = json.loads(body)
        except Exception:
            # Network failures can occur AFTER Orgobot accepts a command:
            # never blindly retry a price mutation.
            raise DecisionRefused("Не удалось подтвердить ответ MCP; повторное нажатие запрещено.") from None
        if not isinstance(packet, dict) or packet.get("error"):
            raise DecisionRefused("Orgobot MCP не подтвердил операцию.")
        return packet.get("result", {})

    def call(self, name, arguments):
        if name not in self.ALLOWED:
            raise DecisionRefused("Запрещённый метод MCP.")
        return _extract(self._post("tools/call", {"name": name, "arguments": arguments}))


def _items(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("decisions", "results", "items"):
            if isinstance(data.get(key), list):
                return data[key]
    raise DecisionRefused("Не удалось разобрать список решений Orgobot.")


def select_decision(client, sku, executor, source_message_id=None):
    """Use verified QRsite schema; no guesswork, writes only on a unique exact match.

    Live 2026-10-15 input fields: id, orgobot_id, market_article,
    marketplaceid_id, blockid_id, responsible_telegram, status.
    Only Orgobot rules 48 and 52 are permitted for this path.
    """
    if source_message_id is None or isinstance(source_message_id, bool) or not str(source_message_id).isdecimal():
        raise DecisionRefused("Неизвестен номер исходного Telegram-сигнала.")
    rows = _items(client.call("orgobot_price_decisions_list", {"limit": 200}))
    wanted = executor.lower().lstrip("@")
    matches = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        article = str(row.get("market_article") or "")
        ruleset = row.get("orgobot_id")
        if isinstance(ruleset, bool) or not str(ruleset).isdecimal() or int(ruleset) not in (48, 52):
            continue
        raw = row.get("responsible_telegram") or []
        if isinstance(raw, (str, dict)):
            raw = [raw]
        if not isinstance(raw, list):
            continue
        owners = []
        for val in raw:
            if isinstance(val, dict):
                val = val.get("username") or val.get("telegram") or ""
            owners.extend(re.split(r"[,;\s]+", str(val)))
        if (article == str(sku)
                and str(row.get("post_id")) == str(source_message_id)
                and str(row.get("status")) == "waiting"
                and any(x.lower().lstrip("@") == wanted for x in owners)):
            matches.append(row)
    if len(matches) != 1:
        raise DecisionRefused("Нет единственного ожидающего решения Orgobot по товару, правилам 48/52 и ответственному.")
    decision_id = matches[0].get("id")
    if isinstance(decision_id, bool) or not str(decision_id).isdecimal() or int(decision_id) <= 0:
        raise DecisionRefused("Orgobot не вернул корректный числовой ID решения.")
    return int(decision_id)

def handle_click(data, user_id, chat_id, thread_id, message_id, client_factory=OrgobotMCP,
                 path=DB_PATH, clock=None):
    """Perform at most one mutation attempt per item. Raises DecisionRefused on any ambiguity."""
    match = TOKEN_RE.fullmatch(data or "")
    if not match:
        raise DecisionRefused("Неизвестная кнопка.")
    if str(chat_id) != "-1002485321031" or str(thread_id) != "758":
        raise DecisionRefused("Неверная тема Telegram.")
    token, answer = match.groups()
    if os.environ.get("MSP_PRICE_LIVE_ENABLED") != "1":
        # Safe acceptance mode: consume the button exactly once, without
        # accessing Orgobot, even when no write-scope or owner IDs are set.
        with closing(connect(path)) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT sent_message_id,expires_utc,state FROM price_buttons WHERE token=?",
                             (token,)).fetchone()
            if not row or row[0] != int(message_id) or row[2] != "waiting":
                raise DecisionRefused("Тестовая кнопка недействительна или уже нажата.")
            if (clock or now_utc()) > dt.datetime.fromisoformat(row[1]):
                raise DecisionRefused("Срок действия кнопки истёк.")
            db.execute("UPDATE price_buttons SET state='tested',answer=? WHERE token=? AND state='waiting'",
                       ("yes" if answer == "y" else "no", token))
            db.commit()
        return "ТЕСТ: принято " + ("Да" if answer == "y" else "Нет") + ". Команды Orgobot не отправлялись."
    allow = {x.strip() for x in os.environ.get("MSP_PRICE_BUTTON_ALLOWED_USER_IDS", "").split(",") if x.strip()}
    if not allow or str(user_id) not in allow:
        raise DecisionRefused("Нет разрешения на принятие решения.")
    executor = os.environ.get("MSP_ORGOBOT_EXECUTOR_USERNAME", "").strip()
    if not executor:
        raise DecisionRefused("Не настроен исполнитель Hermes Bot.")
    with closing(connect(path)) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT sku, sent_message_id, expires_utc, state, source_message_id FROM price_buttons WHERE token=?",
                         (token,)).fetchone()
        if not row or row[1] != int(message_id):
            raise DecisionRefused("Кнопка не связана с этим сообщением.")
        sku, _, expiry, status, source_message_id = row
        if status != "waiting":
            raise DecisionRefused("Решение уже обрабатывается или закрыто.")
        if (clock or now_utc()) > dt.datetime.fromisoformat(expiry):
            raise DecisionRefused("Срок действия кнопки истёк.")
        db.execute("UPDATE price_buttons SET state='processing',answer=? WHERE token=? AND state='waiting'",
                   ("yes" if answer == "y" else "no", token))
        db.commit()
    # A network failure here may be post-commit: fail closed, human review required.
    try:
        client = client_factory()
        decision_id = select_decision(client, sku, executor, source_message_id)
        permitted = {x.strip() for x in os.environ.get("MSP_PRICE_LIVE_DECISION_IDS", "").split(",") if x.strip()}
        if str(decision_id) not in permitted:
            raise DecisionRefused("Решение Orgobot не включено в список разрешённых для реального теста.")
        with closing(connect(path)) as db:
            db.execute("UPDATE price_buttons SET decision_id=? WHERE token=?", (str(decision_id), token))
            db.commit()
        reply = client.call("orgobot_price_decide", {"decision_id": decision_id,
                                                     "answer": "yes" if answer == "y" else "no"})
        command_id = reply.get("command_id") if isinstance(reply, dict) else None
        if isinstance(command_id, bool) or not str(command_id).isdecimal() or int(command_id) <= 0:
            raise DecisionRefused("Не получен числовой command_id; необходима ручная проверка Orgobot.")
        command_id = int(command_id)
        with closing(connect(path)) as db:
            db.execute("UPDATE price_buttons SET command_id=?,state='queued' WHERE token=?",
                       (str(command_id), token))
            db.commit()
        return "Команда Orgobot создана, ожидает проверки: " + str(command_id)
    except Exception:
        with closing(connect(path)) as db:
            db.execute("UPDATE price_buttons SET state='needs_review' WHERE token=? AND state='processing'",
                       (token,))
            db.commit()
        raise DecisionRefused("Нужна проверка Orgobot; повторный клик заблокирован.") from None


def refresh_commands(sender, client_factory=OrgobotMCP, path=DB_PATH):
    """Poll asynchronous Orgobot command states; never resubmit yes/no."""
    if os.environ.get("MSP_PRICE_LIVE_ENABLED") != "1":
        return 0
    with closing(connect(path)) as db:
        rows = db.execute(
            "SELECT token,sku,command_id FROM price_buttons "
            "WHERE state IN ('queued','processing') AND command_id IS NOT NULL"
        ).fetchall()
    if not rows:
        return 0
    client = client_factory()
    completed = 0
    for token, sku, command_id in rows:
        try:
            if not str(command_id).isdecimal() or int(command_id) <= 0:
                continue
            result = client.call("orgobot_price_command_status", {"command_id": int(command_id)})
            state = result.get("status") if isinstance(result, dict) else None
            if state not in {"queued", "processing", "done", "failed", "blocked"}:
                continue
            if state in {"queued", "processing"}:
                with closing(connect(path)) as db:
                    db.execute("UPDATE price_buttons SET state=? WHERE token=? AND state IN ('queued','processing')",
                               (state, token))
                    db.commit()
                continue
            # Send before finalizing so delivery errors allow a later notification retry.
            sender("МСП | Orgobot\nSKU " + sku + "\nКоманда " + str(command_id)
                   + "\nСтатус: " + state
                   + ("\nОбработка завершена; фактическая цена требует проверки в маркетплейсе."
                      if state == "done" else "\nНеобходимо проверить результат вручную."))
            with closing(connect(path)) as db:
                db.execute("UPDATE price_buttons SET state=? WHERE token=? AND state IN ('queued','processing')",
                           (state, token))
                db.commit()
            completed += 1
        except Exception:
            # Remain queued/processing to retry only READ-ONLY status, not mutation.
            continue
    return completed
