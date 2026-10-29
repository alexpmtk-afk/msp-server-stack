import unittest,tempfile,sqlite3,json
from pathlib import Path
from unittest.mock import patch
import registry as r
class LedgerTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch');self.path=Path(self.tmp.name)/'db';self.c=r.connect(self.path)
 def tearDown(self):self.c.close();self.tmp.cleanup()
 def signal(self,mid=1,text='Расхождение размеров или веса\nTEST.0270',at='2026-10-29T01:00:00+00:00'):
  return r.ingest_signal(self.c,{'message_id':mid,'text':text,'date_utc':at})[0]
 def message(self,text='Внести размеры TEST.0270',chat=r.GROUP,mid='4',reply=None,actor='123',at='2026-10-29T03:00:00+00:00'):
  r.capture_message(self.c,dict(chat_id=chat,message_id=mid,at=at,actor_id=actor,text=text,reply_id=reply,thread_id='758',is_bot=False))
 def test_six_types_and_idempotent_edits(self):
  for n,(code,title,pat) in enumerate(r.RULES):
   text={'SIG-016':'Нужно обнулить FBS','SIG-015':'Карточки с обнулёнными остатками','SIG-021':'Превышен расход по РК','SIG-022':'Аномально высокий ДРР','SIG-032':'Расхождение размеров или веса'}.get(code,title)
   self.assertEqual(r.classify(text),[code]);self.signal(n,text);self.signal(n,text)
  self.assertEqual(self.c.execute('select count(*) from signals').fetchone()[0],6)
  self.signal(0,'Поднять цену\n(123456789)');self.assertEqual(self.c.execute('select count(*) from events').fetchone()[0],7)
 def test_group_feedback_exact_product_no_marketplace_execution(self):
  sid=self.signal();self.message();self.message()
  f=self.c.execute('select * from feedback').fetchone();self.assertEqual(f['signal_id'],sid);self.assertEqual(f['at'],'2026-10-29T03:00:00+00:00')
  self.assertEqual(self.c.execute('select count(*) from feedback').fetchone()[0],1);self.assertEqual(self.c.execute('select count(*) from actions').fetchone()[0],0)
 def test_ambiguous_and_wrong_product(self):
  self.signal();self.signal(2);self.message();f=self.c.execute('select * from feedback').fetchone();self.assertEqual(f['match_state'],'ambiguous');self.assertIsNone(f['signal_id'])
  self.message('Внести размеры TEST.02701',mid='5');self.assertEqual(self.c.execute('select count(*) from feedback').fetchone()[0],1)
 def test_reply_emoji_and_remote_actor_scope(self):
  sid=self.signal();r.add_link(self.c,r.REMOTE,50,sid,'test');self.message('👍',r.REMOTE,reply=50,actor=r.OWNER)
  self.assertEqual(self.c.execute('select signal_id from feedback').fetchone()[0],sid)
  self.message('Да',r.REMOTE,mid='6',reply=50,actor='666');self.assertEqual(self.c.execute('select count(*) from feedback').fetchone()[0],1)
 def test_partial_results_and_not_equal_semantics(self):
  sid=self.signal()
  for market,status in [('wb','OK'),('ozon','ERR')]:
   r.result(self.c,'test',[sid],'TEST.0270',{'job_id':'j'+market,'status':'completed','marketplace':market,'results':[{'offer_id':'TEST.0270','status':status,'tooltip':'reason'}]})
  self.assertEqual(dict(self.c.execute('select marketplace,status from actions')),{'wb':'updated','ozon':'failed'})
  r.result(self.c,'test',[sid],'TEST.0270',{'job_id':'jwb','status':'completed','marketplace':'wb','results':[{'status':'NOT'}]})
  self.assertEqual(self.c.execute("select status from actions where marketplace='wb'").fetchone()[0],'already_equal')
 def test_pending_error_mismatched_job_and_offer(self):
  sid=self.signal()
  for v in [{'status':'waiting_vendor','results':[{'status':'OKT'}]},{'status':'completed','error':'bad','results':[{'status':'OK'}]}]:
   r.result(self.c,'a',[sid],'TEST.0270',{'job_id':'j',**v})
  self.assertEqual(self.c.execute('select status from actions').fetchone()[0],'unknown')
  r.result(self.c,'b',[sid],'TEST.0270',{'job_id':'bad','status':'completed','results':[{'status':'OK'}]},expected_jobs=['good'])
  r.result(self.c,'b',[sid],'TEST.0270',{'job_id':'j','status':'completed','results':[{'status':'OK','offer_id':'OTHER'}]})
  self.assertEqual(self.c.execute('select count(*) from actions').fetchone()[0],1)
 def test_no_future_signal_matches(self):
  self.signal(at='2026-10-29T05:00:00+00:00');self.message();self.assertEqual(self.c.execute('select count(*) from feedback').fetchone()[0],0)
 def test_native_ingress_and_callback_timestamp(self):
  sid=self.signal();r.add_link(self.c,r.REMOTE,50,sid,'test');self.c.commit()
  r.ingest_update({'callback_query':{'id':'x','data':'mspdim2:'+'a'*24+':y','from':{'id':int(r.OWNER)},'message':{'chat':{'id':int(r.REMOTE)},'message_id':50,'message_thread_id':758}}},self.path)
  self.assertEqual(self.c.execute('select text from feedback').fetchone()[0],'Да')
  self.assertIsNotNone(self.c.execute('select at from feedback').fetchone()[0])
 def test_unknown_legacy_times_stay_unknown(self):
  sid=self.signal();r.feedback_record(self.c,'legacy',[sid],'yes',None);r.feedback_record(self.c,'legacy',[sid],'yes',None)
  self.assertIsNone(self.c.execute('select at from feedback').fetchone()[0]);self.assertEqual(self.c.execute('select count(*) from feedback').fetchone()[0],1)

 def test_simulation_and_proof_required(self):
  sid=self.signal()
  with self.assertRaises(ValueError):r.record_action(self.c,sid,'k','TEST.0270','wb','','updated','Сделано',None)
  r.record_action(self.c,sid,'k','TEST.0270','wb','','simulation','Имитация',None)
  self.assertEqual(self.c.execute('select execution_summary from v_signal_registry').fetchone()[0],'simulation')
 def test_partial_view_and_manual_resolution(self):
  sid=self.signal()
  for market,state in [('wb','updated'),('ozon','failed')]:r.record_action(self.c,sid,market,'TEST.0270',market,'',state,'Причина','fixture-only proof')
  self.assertEqual(self.c.execute('select execution_summary from v_signal_registry').fetchone()[0],'partial')
 def test_out_of_scope_remote_topic_not_stored(self):
  r.ingest_update({'message':{'message_id':555,'date':1793250000,'chat':{'id':int(r.REMOTE)},'message_thread_id':999,'from':{'id':int(r.OWNER)},'text':'unrelated'}},self.path)
  self.assertEqual(self.c.execute('select count(*) from messages').fetchone()[0],0)
 def test_restart_and_integrity(self):
  sid=self.signal();self.message();self.c.commit()
  with r.connect(self.path) as other:
   self.assertEqual(other.execute('select feedback_count from v_signal_registry').fetchone()[0],1)
   self.assertEqual(other.execute('pragma integrity_check').fetchone()[0],'ok')
   self.assertEqual(other.execute('pragma foreign_key_check').fetchall(),[])

 def test_verified_executor_link_resolves_cross_chat_ambiguity(self):
  sid=self.signal();self.signal(2);self.message();self.assertEqual(self.c.execute('select match_state from feedback').fetchone()[0],'ambiguous')
  r.add_link(self.c,r.GROUP,'4',sid,'verified_executor_direct_link')
  r.match_feedback(self.c,dict(self.c.execute('select * from messages').fetchone()))
  self.assertEqual(self.c.execute('select signal_id from feedback').fetchone()[0],sid)

 def test_reply_chain_keeps_signal_identity(self):
  sid=self.signal();self.message();self.message('Да',chat=r.GROUP,mid='5',reply='4')
  self.assertEqual([x[0] for x in self.c.execute('select signal_id from feedback')],[sid,sid])

 def test_false_success_and_nested_error_never_confirm_action(self):
  sid=self.signal()
  for i,payload in enumerate([{'job_id':'j','status':'completed','success':False,'results':[{'status':'OK'}]},{'job_id':'k','status':'completed','results':[{'status':'OK','details':{'success':False}}]}]):
   r.result(self.c,str(i),[sid],'TEST.0270',payload)
  self.assertEqual([x[0] for x in self.c.execute('select status from actions')],['unknown','unknown'])

if __name__=='__main__':unittest.main()
