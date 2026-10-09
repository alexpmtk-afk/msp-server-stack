import os,sqlite3,tempfile,unittest
from pathlib import Path
from apps.operator_layer.backup import BackupStore
class BackupTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.db=self.root/'live.sqlite3';self.c=sqlite3.connect(self.db);self.c.execute('pragma journal_mode=WAL');self.c.execute('create table t(id integer primary key,v text)');self.c.execute("insert into t values(1,'original')");self.c.commit();self.store=BackupStore(self.db,self.root/'backups',retention=2)
 def tearDown(self):self.c.close();self.tmp.cleanup()
 def test_wal_backup_restore_real(self):
  m=self.store.backup();self.assertEqual(m['integrity'],'ok');self.assertEqual(m['counts']['t'],1);self.assertEqual(m['foreign_key_errors'],0)
  self.assertEqual((self.root/'backups'/m['backup_id']/'database.sqlite3').stat().st_mode & 0o777,0o600)
  self.c.execute("update t set v='modified'");self.c.commit();self.c.close()
  with self.assertRaises(ValueError):self.store.restore(m['backup_id'],maintenance=False)
  r=self.store.restore(m['backup_id'],maintenance=True);self.assertIn('safety_backup_id',r)
  self.c=sqlite3.connect(self.db);self.assertEqual(self.c.execute('select v from t').fetchone()[0],'original')
 def test_corrupt_backup_and_traversal_rejected(self):
  m=self.store.backup();p=self.root/'backups'/m['backup_id']/'database.sqlite3';p.write_bytes(b'bad')
  with self.assertRaises(ValueError):self.store.restore(m['backup_id'],maintenance=True)
  with self.assertRaises(ValueError):self.store.restore('../bad',maintenance=True)
 def test_retention(self):
  for _ in range(3):self.store.backup()
  self.assertEqual(len(list((self.root/'backups').iterdir())),2)
if __name__=='__main__':unittest.main()
