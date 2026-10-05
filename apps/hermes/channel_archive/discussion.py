"""Discussion capture and evidence-based reply audit; no outgoing messages."""
import json
from datetime import datetime, timezone
from .archive import connect, stamp, CHANNEL_ID
DISCUSSION_ID = '-1003493121508'

def tables(c):
    c.executescript('''CREATE TABLE IF NOT EXISTS discussion (
    message_id INTEGER PRIMARY KEY, date_utc TEXT NOT NULL, text TEXT NOT NULL,
    author_json TEXT NOT NULL, is_bot INTEGER NOT NULL, parent_id INTEGER,
    thread_id INTEGER, channel_post_id INTEGER, automatic INTEGER NOT NULL,
    edit_date_utc TEXT, received_utc TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS discussion_parent ON discussion(parent_id);
    ''')

def origin_id(m):
    if not m or not getattr(m,'is_automatic_forward',False): return None
    origin = getattr(m,'forward_origin',None)
    chat = getattr(origin,'chat',None) or getattr(m,'forward_from_chat',None)
    mid = getattr(origin,'message_id',None) or getattr(m,'forward_from_message_id',None)
    return mid if chat and str(chat.id) == CHANNEL_ID else None

def capture_discussion(update):
    m = getattr(update,'message',None) or getattr(update,'edited_message',None)
    if not m or str(m.chat.id) != DISCUSSION_ID: return False
    now = stamp(datetime.now(timezone.utc))
    with connect() as c:
        tables(c)
        parent = getattr(m,'reply_to_message',None)
        for item in ([parent] if parent else []) + [m]:
            user = getattr(item,'from_user',None)
            sender = getattr(item,'sender_chat',None)
            author = {'id':getattr(user,'id',None), 'name':getattr(user,'full_name',None),
                      'username':getattr(user,'username',None), 'sender_chat_id':getattr(sender,'id',None),
                      'sender_chat_title':getattr(sender,'title',None)}
            old = c.execute('SELECT edit_date_utc FROM discussion WHERE message_id=?',(item.message_id,)).fetchone()
            edited = stamp(getattr(item,'edit_date',None))
            if old and old[0] and (not edited or edited < old[0]): continue
            reply = getattr(item,'reply_to_message',None)
            c.execute('''INSERT INTO discussion VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(message_id) DO UPDATE SET text=excluded.text,author_json=excluded.author_json,
            is_bot=excluded.is_bot,parent_id=COALESCE(excluded.parent_id,discussion.parent_id),
            thread_id=COALESCE(excluded.thread_id,discussion.thread_id),
            channel_post_id=COALESCE(excluded.channel_post_id,discussion.channel_post_id),
            edit_date_utc=excluded.edit_date_utc,received_utc=excluded.received_utc''',
            (item.message_id,stamp(item.date),item.text or item.caption or '',json.dumps(author,ensure_ascii=False),
             int(bool(getattr(user,'is_bot',False))),getattr(reply,'message_id',None),
             getattr(item,'message_thread_id',None),origin_id(item),int(bool(getattr(item,'is_automatic_forward',False))),edited,now))
        c.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)',('last_discussion_received_utc',now))
    return True

def enrich(result):
    with connect() as c:
        tables(c)
        rows = {r['message_id']:dict(r) for r in c.execute('SELECT * FROM discussion')}
        def resolve(mid, seen=None):
            seen = set() if seen is None else seen
            if mid in seen or mid not in rows: return None
            seen.add(mid); r = rows[mid]
            return r['channel_post_id'] or resolve(r['parent_id'],seen) or resolve(r['thread_id'],seen)
        for post in result.get('messages',[]):
            comments = []
            roots = [r for r in rows.values() if r['channel_post_id'] == post['message_id']]
            for mid,r in rows.items():
                if not r['automatic'] and resolve(mid) == post['message_id']:
                    comment = dict(r); comment['author'] = json.loads(comment.pop('author_json'))
                    comment['link'] = 'https://t.me/c/'+DISCUSSION_ID[4:]+'/'+str(mid)
                    comments.append(comment)
            comments.sort(key=lambda r:(r['date_utc'],r['message_id']))
            human = [r for r in comments if not r['is_bot']]
            post.update(comments=comments,reply_count=len(human),
                        response_status='ответ есть' if human else 'ответ не зафиксирован' if roots else 'недостаточно данных',
                        responsible_verified=False, completion_verified=False)
        result['discussion_id'] = DISCUSSION_ID
        result['discussion_message_count'] = len(rows)
        result['unlinked_comment_count'] = sum(not r['automatic'] and resolve(mid) is None for mid,r in rows.items())
        result['reply_audit_note'] = 'Only observed discussion messages. No reply is not proof of no work; old comments unavailable. Reply does not prove completion or responsible identity. Bot messages excluded from reply_count.'
    return result
