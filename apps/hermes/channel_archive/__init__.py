"""Receive allowed channel updates from Hermes' existing Telegram polling loop."""
import asyncio
import logging
import os
from datetime import datetime, timezone
from .archive import CHANNEL_ID, SCHEMA, capture, connect, handle, mark, stamp
from .discussion import DISCUSSION_ID, capture_discussion
log = logging.getLogger('channel_archive')

async def _receive(update, context):
    message = (getattr(update,'channel_post',None) or getattr(update,'edited_channel_post',None) or getattr(update,'message',None) or getattr(update,'edited_message',None))
    if message is None or str(message.chat.id) not in (CHANNEL_ID, DISCUSSION_ID): return
    try:
        if await asyncio.to_thread(capture_discussion if str(message.chat.id) == DISCUSSION_ID else capture,update):
            log.info('Archived channel post chat=%s message_id=%s',CHANNEL_ID,message.message_id)
        await asyncio.to_thread(mark,'last_update_seen_utc',stamp(datetime.now(timezone.utc)))
    except Exception:
        log.exception('Failed to archive channel post')
        try: await asyncio.to_thread(mark,'last_error_utc',stamp(datetime.now(timezone.utc)))
        except Exception: pass

def _wire_collector_v2(native, adapter=None):
    from telegram import Update
    from telegram.ext import TypeHandler
    mark('collector_attached_utc',stamp(datetime.now(timezone.utc)))
    mark('collector_pid',os.getpid())
    with connect() as c:
        c.execute('INSERT OR IGNORE INTO metadata VALUES (?,?)',('discussion_collection_started_utc',stamp(datetime.now(timezone.utc))))
    for old in list(getattr(native, 'handlers', {}).get(-95, [])):
        callback = getattr(old, 'callback', None)
        original = getattr(callback, '__wrapped__', callback)
        if (getattr(original, '__module__', None) == __name__
                and getattr(original, '__name__', None) == '_receive'):
            native.remove_handler(old, group=-95)
    native.add_handler(TypeHandler(Update, _receive), group=-95)
    log.info('Channel archive collector attached chat=%s pid=%s',CHANNEL_ID,os.getpid())

_wire = _wire_collector_v2

def _read_only(event, **kwargs):
    source = getattr(event, 'source', None)
    platform = getattr(source, 'platform', None)
    platform = getattr(platform, 'value', platform)
    if platform == 'telegram' and str(getattr(source, 'chat_id', '')) in (CHANNEL_ID, DISCUSSION_ID):
        return {'action':'skip','reason':'channel_archive: read-only channel; post is captured by native collector'}
    return None

def register(ctx):
    ctx.register_telegram_handler(_wire)
    ctx.register_hook("pre_gateway_dispatch", _read_only)
    ctx.register_tool('telegram_channel_archive','project',SCHEMA,handle,
                      check_fn=lambda: True,description=SCHEMA['description'],emoji='🗃️')
