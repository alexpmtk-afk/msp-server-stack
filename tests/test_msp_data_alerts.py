import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("msp_alerts",ROOT/"apps/msp_data_sync/run_with_alerts.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class MSPAlertTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.base=Path(self.tmp.name)
        self.business=str(self.base/"business.sqlite3")
        c=sqlite3.connect(self.business)
        c.executescript("""
            create table sync_run(run_id integer primary key,source text);
            create table sync_run_issue(run_id integer,source text,source_row integer,error text,created_at text);
            insert into sync_run values (1,'price_journal_current');
            insert into sync_run_issue values (1,'price_journal_current',125,'bad SKU','2026-10-08');
            insert into sync_run_issue values (1,'price_journal_current',348,'bad date','2026-10-08');
        """)
        c.close()
        self.alerts=str(self.base/"alerts.sqlite3")
        self.failed={"source":"price_journal_current","status":"partial","source_rows":2000,"rejected":2}
        self.ok={"source":"price_journal_current","status":"success","source_rows":2000,"rejected":0}

    def tearDown(self):
        self.tmp.cleanup()

    def state(self):
        c=sqlite3.connect(self.alerts)
        result=c.execute("select source,state,fingerprint,last_message_id from alert_delivery_state").fetchall()
        c.close()
        return result

    def test_deduplicate_identical_partial_and_recovery_once(self):
        texts=[]
        def deliver(message):
            texts.append(message)
            return len(texts)+1000
        with patch.object(m,"send_telegram",side_effect=deliver):
            m.run_alerts(self.alerts,self.business,[self.failed])
            m.run_alerts(self.alerts,self.business,[self.failed])
            m.run_alerts(self.alerts,self.business,[self.ok])
            m.run_alerts(self.alerts,self.business,[self.ok])
        self.assertEqual(len(texts),2)
        self.assertIn("125",texts[0])
        self.assertIn("348",texts[0])
        self.assertIn("ПРЕДУПРЕЖДЕНИЕ",texts[0])
        self.assertIn("ВОССТАНОВЛЕНО",texts[1])
        self.assertEqual(self.state()[0][1],"ok")

    def test_failed_no_per_run_errors_still_alerts(self):
        bad={"source":"price_journal_archive","status":"failed","error":"HTTP 500"}
        with patch.object(m,"send_telegram",return_value=44) as send:
            m.run_alerts(self.alerts,self.business,[bad])
            m.run_alerts(self.alerts,self.business,[bad])
        self.assertEqual(send.call_count,1)
        self.assertIn("ПОЛНЫЙ СБОЙ",send.call_args[0][0])

    def test_delivery_failure_does_not_advance_state(self):
        with patch.object(m,"send_telegram",side_effect=RuntimeError("transport")):
            with self.assertRaises(RuntimeError):
                m.run_alerts(self.alerts,self.business,[self.failed])
        self.assertEqual(self.state(),[])
        with patch.object(m,"send_telegram",return_value=555) as send:
            m.run_alerts(self.alerts,self.business,[self.failed])
        self.assertEqual(send.call_count,1)
        self.assertEqual(self.state()[0][1],"problem")

    def test_changed_source_error_triggers_new_alert(self):
        with patch.object(m,"send_telegram",return_value=1) as send:
            m.run_alerts(self.alerts,self.business,[self.failed])
            c=sqlite3.connect(self.business)
            c.execute("insert into sync_run values(2,'price_journal_current')")
            c.execute("insert into sync_run_issue values(2,'price_journal_current',555,'missing SKU','2026-10-08')")
            c.commit();c.close()
            m.run_alerts(self.alerts,self.business,[self.failed])
        self.assertEqual(send.call_count,2)

    def test_no_message_for_healthy_sources_or_technical_skips(self):
        good=[{"source":s,"status":"success","source_rows":12,
               "skipped_technical":1 if s=="price_journal_current" else 0,"rejected":0} for s in m.SOURCES]
        with patch.object(m,"send_telegram") as send:
            m.run_alerts(self.alerts,self.business,good)
        send.assert_not_called()

    def test_unrecognized_status_never_overwrites_alert_state(self):
        with self.assertRaises(ValueError):
            m.run_alerts(self.alerts,self.business,[{"source":"self_purchase","status":"unknown"}])

    def test_telegram_error_never_leaks_url_or_bot_token(self):
        import os, urllib.error
        env={"MSP_ALERT_BOT_TOKEN":"123456:dangerfake","MSP_ALERT_CHAT_ID":"-1002485321031","MSP_ALERT_THREAD_ID":"758"}
        with patch.dict(os.environ,env),patch.object(m.urllib.request,"urlopen",side_effect=urllib.error.URLError("secret leak")):
            with self.assertRaisesRegex(RuntimeError,"secret redacted") as ctx:
                m.send_telegram("sample")
        self.assertNotIn(env["MSP_ALERT_BOT_TOKEN"],str(ctx.exception))

if __name__=="__main__":
    unittest.main()
