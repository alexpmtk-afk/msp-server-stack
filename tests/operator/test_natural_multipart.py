"""Natural Russian multipart controls: opt-in, explicit intent, no guesswork."""
import tempfile
import unittest
from pathlib import Path
from apps.operator_layer.tasks import Journal
from apps.operator_layer.multipart import Collector, natural_control
from apps.operator_layer.production import receive

SCOPE=('default','owner','telegram:fixture','session-fixture')

class NaturalMultipartTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.j=Journal(Path(self.tmp.name)/'private');self.addCleanup(self.j.close)
  self.c=Collector(self.j)
 def send(self,text,i,enabled=True):
  return self.c.receive(SCOPE,str(i),i,text,natural_controls_enabled=enabled)
 def test_default_off_preserves_everyday_chat(self):
  for i,text in enumerate(('Сейчас отправлю задание частями','Всё, приступай','Обычный вопрос'),1):
   self.assertFalse(self.send(text,i,False)['consumed'])
  self.assertEqual(self.j.db.execute('SELECT COUNT(*) FROM multipart').fetchone()[0],0)
 def test_natural_end_without_begin_does_not_intercept(self):
  self.assertFalse(self.send('Всё, приступай',1)['consumed'])
  self.assertFalse(self.send('На этом всё, приступай!',2)['consumed'])
  self.assertFalse(self.send('Обычная беседа',3)['consumed'])
 def test_opt_in_builds_single_task_without_numbers(self):
  a=self.send('Сейчас отправлю задание частями',1)
  self.assertEqual(a['status'],'COLLECTING')
  self.assertEqual(a['mode'],'manual')
  self.assertEqual(a['received_parts'],[])
  self.assertEqual(self.send('Требуется отчёт по базе МСП.',2)['received_parts'],[1])
  self.assertEqual(self.send('Отдельно проанализируй ошибки.',3)['received_parts'],[1,2])
  self.assertEqual(self.j.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0],0)
  z=self.send('Всё, приступай!',4)
  self.assertEqual(z['status'],'COMPLETE')
  assembled=self.c.assemble(z['multipart_task_id'])
  self.assertEqual(assembled['status'],'ASSEMBLED')
  tid=assembled['durable_task_id']
  self.assertEqual(self.c.input_for(tid),'Требуется отчёт по базе МСП.\\n\\nОтдельно проанализируй ошибки.'.replace('\\n','\n'))
  self.assertEqual(self.j.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0],1)
  self.assertEqual(self.send('Всё, приступай!',4)['multipart_task_id'],z['multipart_task_id'])
  self.assertEqual(self.j.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0],1)
 def test_recovery_from_restart_in_open_mode(self):
  a=self.send('Я сейчас отправлю задание несколькими сообщениями',1)
  self.send('Первый блок',2)
  self.c=Collector(self.j)
  self.send('Второй блок',3)
  z=self.send('На этом всё, приступай',4)
  self.assertEqual(z['multipart_task_id'],a['multipart_task_id'])
  assembled=self.c.assemble(z['multipart_task_id'])
  self.assertEqual(self.c.input_for(assembled['durable_task_id']),'Первый блок\n\nВторой блок')
 def test_ambiguous_end_in_larger_text_is_payload(self):
  self.send('Начинаю большое задание',1)
  a=self.send('Фраза «всё, приступай» встречается в документе.',2)
  self.assertEqual(a['status'],'COLLECTING')
  b=self.send('Всё, приступай\\nно не сейчас',3)
  self.assertEqual(b['status'],'COLLECTING')
  c=self.send('/task end',4)
  self.assertEqual(c['status'],'COMPLETE')
 def test_natural_cancel_and_existing_slash_protocol(self):
  self.send('Сейчас опишу задачу в нескольких сообщениях',1)
  self.send('Черновик',2)
  self.assertEqual(self.send('Отмени сбор задания',3)['status'],'CANCELLED')
  self.assertEqual(self.j.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0],0)
  self.assertFalse(self.send('Всё, приступай',4)['consumed'])
  self.assertEqual(self.send('/task begin',5)['status'],'COLLECTING')
  self.send('Новый блок',6)
  self.assertEqual(self.send('/task end',7)['status'],'COMPLETE')
 def test_numbered_protocol_remains_unchanged(self):
  a=self.send('TASK 1/2\nА',1)
  self.assertEqual(a['mode'],'numbered')
  self.assertEqual(self.send('TASK 2/2 END\nБ',2)['status'],'COMPLETE')
  self.assertEqual(self.j.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0],0)
 def test_recognizer_standalone_only(self):
  self.assertIsNone(natural_control('Сегодня пример: Всё, приступай'))
  self.assertIsNone(natural_control('Всё, приступай\nэто цитата'))
  self.assertIsNone(natural_control('Я начинаю большое задание для исследования'))
  self.assertEqual(natural_control('  ЭТО ВСЁ, ПРИСТУПАЙ!  '),'/task end')
 def test_production_config_gates_recognition(self):
  with tempfile.TemporaryDirectory() as tmp:
   cfg={'root':str(Path(tmp)/'root'),'scope':SCOPE}
   self.assertFalse(receive(cfg,'a',None,'Сейчас отправлю задание частями')['consumed'])
   cfg['natural_multipart_enabled']='true'
   self.assertFalse(receive(cfg,'b',None,'Сейчас отправлю задание частями')['consumed'])
   cfg['natural_multipart_enabled']=True
   self.assertEqual(receive(cfg,'c',None,'Сейчас отправлю задание частями')['status'],'COLLECTING')
   self.assertEqual(receive(cfg,'d',None,'Текст')['status'],'COLLECTING')
   self.assertEqual(receive(cfg,'e',None,'Это всё, приступай')['status'],'DISPATCHED')
   self.assertEqual(receive(cfg,'f',None,'Всё, приступай')['consumed'],False)

if __name__=='__main__':unittest.main()
