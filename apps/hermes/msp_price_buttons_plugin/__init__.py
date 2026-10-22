"""Hermes native Telegram callback plugin (no second bot receiver).

Install only after verifying the remote Hermes version supports
register_platform_handler. This handler is scoped to the msp2: prefix.
"""
from __future__ import annotations
import asyncio
import os
import sys
from pathlib import Path

# Deployment pins a bundle symlink next to this plugin, so the old shared
# /opt/mcp/projects/msp-server-stack checkout can remain untouched.
ROOT = Path(__file__).parent / "bundle"


def register(ctx):
    if not hasattr(ctx, "register_platform_handler"):
        raise RuntimeError("Hermes plugin API missing register_platform_handler")

    def wire(application, adapter):
        from telegram.ext import CallbackQueryHandler
        if not (ROOT / "apps/msp_signal_notify/price_buttons.py").is_file():
            raise RuntimeError("Pinned SIG-002 bundle is missing")
        pinned = str(ROOT.resolve())
        if pinned not in sys.path:
            sys.path.insert(0, pinned)
        from apps.msp_signal_notify.price_buttons import DecisionRefused, handle_click

        async def clicked(update, context):
            query = update.callback_query
            if query is None or not query.data:
                return
            msg = query.message
            if msg is None:
                await query.answer("Сообщение недоступно.", show_alert=True)
                return
            # Use Telegram immutable user ID; no usernames or untrusted message body.
            try:
                # Fast acknowledgement: don't hold Telegram's spinner while MCP runs.
                # Processing itself has a durable, one-use SQLite claim.
                await query.answer("Проверяю решение Orgobot…")
                result = await asyncio.to_thread(
                    handle_click, query.data, query.from_user.id,
                    msg.chat_id, getattr(msg, "message_thread_id", None), msg.message_id)
            except DecisionRefused as exc:
                await context.bot.send_message(
                    chat_id=msg.chat_id,
                    message_thread_id=getattr(msg, "message_thread_id", None),
                    text="МСП | Решение не выполнено: " + str(exc))
                return
            except Exception:
                await context.bot.send_message(
                    chat_id=msg.chat_id,
                    message_thread_id=getattr(msg, "message_thread_id", None),
                    text="МСП | Ошибка обработки кнопки, требуется ручная проверка.")
                return
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
            await context.bot.send_message(
                chat_id=msg.chat_id,
                message_thread_id=getattr(msg, "message_thread_id", None),
                text="МСП | " + result + ". Статус queued НЕ означает изменение цены.")
        application.add_handler(CallbackQueryHandler(clicked, pattern=r"^msp2:[0-9a-f]{24}:[yn]$"))

    ctx.register_platform_handler("telegram", wire)
