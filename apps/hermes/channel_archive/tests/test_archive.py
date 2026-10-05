"""Synthetic fixtures only; never writes test data to the production archive."""
import asyncio
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from channel_archive import archive as a
from channel_archive import _receive, _read_only

class ArchiveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch')
        self.before = os.environ.get('HERMES_HOME')
        os.environ['HERMES_HOME'] = self.tmp.name
    def tearDown(self):
        if self.before is None: os.environ.pop('HERMES_HOME',None)
        else: os.environ['HERMES_HOME'] = self.before
        self.tmp.cleanup()
    def post(self, mid=1, date='2026-10-03T15:00:00+00:00', text='СИГНАЛ МП', edited=None, cid=a.CHANNEL_ID):
        msg=SimpleNamespace(chat=SimpleNamespace(id=int(cid)),message_id=mid,date=datetime.fromisoformat(date),text=text,caption=None,edit_date=datetime.fromisoformat(edited) if edited else None)
        return SimpleNamespace(channel_post=None if edited else msg,edited_channel_post=msg if edited else None)
    def test_live_callback_dedup_edit_and_other_channel(self):
        asyncio.run(_receive(self.post(), None)); asyncio.run(_receive(self.post(), None))
        self.assertEqual(a.query(action='status')['message_count'],1)
        asyncio.run(_receive(self.post(text='Исправлено',edited='2026-10-03T15:01:00+00:00'),None))
        asyncio.run(_receive(self.post(),None))
        self.assertEqual(a.query()['messages'][0]['text'],'Исправлено')
        self.assertFalse(a.capture(self.post(cid='-1009999999999')))
        with a.connect() as c: self.assertEqual(c.execute('select count(*) from revisions').fetchone()[0],1)
    def test_dates_pagination_unicode_and_injection(self):
        a.capture(self.post(1,date='2026-10-02T23:59:59+00:00'))
        a.capture(self.post(2,date='2026-10-03T00:00:00+00:00'))
        a.capture(self.post(3,date='2026-10-03T23:59:59+00:00'))
        a.capture(self.post(4,date='2026-10-04T00:00:00+00:00'))
        r=a.query(start='2026-10-03',end='2026-10-03',limit=1,contains='сигнал')
        self.assertEqual(r['total'],2); self.assertTrue(r['has_more'])
        r2=a.query(start='2026-10-03',end='2026-10-03',limit=1,offset=r['next_offset'])
        self.assertFalse(r2['has_more']); self.assertEqual(r2['messages'][0]['message_id'],3)
        self.assertEqual(a.query(contains="' OR 1=1 --")['total'],0)
        with self.assertRaises(ValueError): a.query(start='2026-10-04',end='2026-10-03')
    def test_read_only_hook(self):
        event=SimpleNamespace(source=SimpleNamespace(platform='telegram',chat_id=a.CHANNEL_ID))
        self.assertEqual(_read_only(event)['action'],'skip')
        event.source.chat_id='639699477'
        self.assertIsNone(_read_only(event))
    def test_discussion_nested_reply_and_unknown(self):
        from channel_archive.discussion import capture_discussion, DISCUSSION_ID
        a.capture(self.post())
        self.assertEqual(a.query()['messages'][0]['response_status'],'недостаточно данных')
        root=self.post(mid=10,cid=DISCUSSION_ID).channel_post
        root.is_automatic_forward=True
        root.forward_origin=SimpleNamespace(chat=SimpleNamespace(id=int(a.CHANNEL_ID)),message_id=1)
        capture_discussion(SimpleNamespace(message=root))
        self.assertEqual(a.query()['messages'][0]['response_status'],'ответ не зафиксирован')
        reply=self.post(mid=11,cid=DISCUSSION_ID,text='В работе').channel_post
        reply.reply_to_message=root
        reply.from_user=SimpleNamespace(id=42,full_name='Ответственный',username='test',is_bot=False)
        capture_discussion(SimpleNamespace(message=reply))
        nested=self.post(mid=12,cid=DISCUSSION_ID,text='Готово').channel_post
        nested.reply_to_message=reply; nested.from_user=reply.from_user
        capture_discussion(SimpleNamespace(message=nested)); capture_discussion(SimpleNamespace(message=nested))
        r=a.query()['messages'][0]
        self.assertEqual(r['reply_count'],2); self.assertEqual(r['response_status'],'ответ есть')
        self.assertFalse(r['completion_verified'])
        bot=self.post(mid=13,cid=DISCUSSION_ID).channel_post
        bot.reply_to_message=root; bot.from_user=SimpleNamespace(is_bot=True)
        capture_discussion(SimpleNamespace(message=bot))
        self.assertEqual(a.query()['messages'][0]['reply_count'],2)
    def test_caption_media(self):
        p=self.post(text=None); p.channel_post.caption='Подпись'; p.channel_post.photo=[SimpleNamespace(file_id='fixture',file_unique_id='fixture-id')]
        a.capture(p); r=a.query()['messages'][0]
        self.assertEqual(r['text'],'Подпись'); self.assertEqual(r['content_type'],'photo')
        self.assertEqual(r['media']['file_id'],'fixture')

if __name__=='__main__': unittest.main()
