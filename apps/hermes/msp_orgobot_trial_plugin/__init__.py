"""Scoped Telegram callback plugin for ONE real Orgobot decision.

No second polling bot, no mutation on plugin registration, no general-purpose
price editing. Requires a separately minted and verified single-use card.
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).parent / "bundle"


def register(ctx):
    def wire(application, adapter):
        from telegram.ext import CallbackQueryHandler
        root = ROOT.resolve()
        if not (root/"apps/msp_signal_notify/orgobot_trial.py").is_file():
            raise RuntimeError("Reviewed SIG-002 trial bundle unavailable")
        if str(root) not in sys.path:
            sys.path.insert(0,str(root))
        from apps.msp_signal_notify.orgobot_trial import confirm, check_command, DecisionRefused

        async def watch(context, chat_id, thread_id, command):
            # Read-only status monitoring; never repeat orgobot_price_decide.
            for _ in range(20):
                await asyncio.sleep(6)
                try:
                    status = await asyncio.to_thread(check_command, command)
                except Exception:
                    continue
                if status in ("done", "failed", "blocked"):
                    msg = ("МСП | Orgobot №169 | Команда " + str(command)
                           + "\nСтатус: " + status
                           + ("\nОбработка завершена. Фактическую новую цену сверяем отдельно."
                              if status == "done" else "\nТребуется проверка причины."))
                    try:
                        await context.bot.send_message(chat_id=chat_id,
                             message_thread_id=thread_id, text=msg)
                    except Exception:
                        pass
                    return

        async def on_click(update, context):
            query = update.callback_query
            if not query or not query.data:
                return
            msg = query.message
            if not msg:
                await query.answer("Исходное сообщение недоступно.",show_alert=True)
                return
            await query.answer("Проверяю полномочия и состояние Orgobot…")
            chat_id = msg.chat_id
            topic = getattr(msg,"message_thread_id",None)
            try:
                command = await asyncio.to_thread(
                    confirm, query.data, query.from_user.id,
                    chat_id, topic, msg.message_id,
                    context.bot.username)
            except DecisionRefused as exc:
                await context.bot.send_message(chat_id=chat_id,
                   message_thread_id=topic,
                   text="МСП | Orgobot №169: решение НЕ выполнено. " + str(exc))
                return
            except Exception:
                await context.bot.send_message(chat_id=chat_id,
                   message_thread_id=topic,
                   text="МСП | Orgobot №169: непредвиденная ошибка, требуется ручная проверка.")
                return
            try:
                await query.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
            await context.bot.send_message(chat_id=chat_id,
               message_thread_id=topic,
               text="МСП | Orgobot №169: команда "+str(command)+
                    " поставлена в очередь. Это пока НЕ подтверждение изменения цены.")
            asyncio.create_task(watch(context,chat_id,topic,command))

        application.add_handler(CallbackQueryHandler(
             on_click,pattern=r"^msp3:[0-9a-f]{32}:[yn]$"))
    ctx.register_platform_handler("telegram",wire)
