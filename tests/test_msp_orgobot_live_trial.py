"""Offline, synthetic acceptance for single real Orgobot decision #169."""
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from apps.msp_signal_notify import orgobot_trial as t


class FakeMCP:
    calls = []
    status = "done"
    changes = {}
    def __init__(self):
        pass
    def call(self, name, args):
        self.calls.append((name,args))
        if name=="orgobot_price_decisions_list":
            r = dict(t.TARGET, status="waiting",
                     responsible_telegram="@msp_hermes_test_bot")
            r.update(self.changes)
            return {"results":[r]}
        if name=="orgobot_price_decide":
            return {"command_id":802,"status":"queued"}
        if name=="orgobot_price_command_status":
            return {"status":self.status}
        raise AssertionError(name)


class SingleTrialTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=Path(self.tmp.name)/"trial.sqlite3"
        self.time=dt.datetime(2026,10,15,11,tzinfo=dt.timezone.utc)
        FakeMCP.calls=[]
        FakeMCP.changes={}
        FakeMCP.status="done"
        self.nonce,_=t.create_card([12345],path=self.db,clock=self.time)
        t.bind_message(self.nonce,9001,path=self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def decide(self,answer="y",user=12345,chat=t.CHAT_ID,thread=t.THREAD_ID,clk=None):
        return t.confirm("msp3:"+self.nonce+":"+answer,user,chat,thread,9001,
                         "msp_hermes_test_bot",client_factory=FakeMCP,
                         path=self.db,clock=clk or self.time)

    def test_yes_only_one_mutation_and_queue(self):
        self.assertEqual(self.decide(),802)
        self.assertEqual([x[0] for x in FakeMCP.calls],
                         ["orgobot_price_decisions_list","orgobot_price_decide"])
        self.assertEqual(FakeMCP.calls[-1][1],{"decision_id":169,"answer":"yes"})
        with self.assertRaises(t.DecisionRefused): self.decide()
        self.assertEqual(len(FakeMCP.calls),2)
        self.assertEqual(t.check_command(802,client_factory=FakeMCP,path=self.db),"done")
        with t.connect(self.db) as db:
            self.assertEqual(db.execute("SELECT state FROM trials").fetchone()[0],"done")

    def test_no_calls_no_only_once(self):
        self.assertEqual(self.decide("n"),802)
        self.assertEqual(FakeMCP.calls[-1][1],{"decision_id":169,"answer":"no"})

    def test_unauthorized_bad_topic_or_expired_does_not_call(self):
        for kwargs in ({"user":111}, {"chat":-111}, {"thread":4},
                       {"clk":self.time+dt.timedelta(hours=13)}):
            with self.assertRaises(t.DecisionRefused): self.decide(**kwargs)
        self.assertEqual(FakeMCP.calls,[])

    def test_changed_percent_owner_or_status_blocks_execution(self):
        for field,value in (("percent","30.00"),("responsible_telegram","@stranger"),
                            ("status","priced"),("blockid_id",7),("post_id",9999)):
            FakeMCP.changes={field:value}
            # One one-use card per subcase. No tool mutation allowed.
            with self.subTest(field=field):
                with self.assertRaises(t.DecisionRefused): self.decide()
                self.assertEqual([n for n,_ in FakeMCP.calls if n=="orgobot_price_decide"],[])
                with t.connect(self.db) as db:
                    db.execute("UPDATE trials SET state='waiting',answer=NULL")
                    db.commit()
                FakeMCP.calls=[]

    def test_missing_mcp_response_failclosed(self):
        class Uncertain(FakeMCP):
            def call(self,name,args):
                if name=="orgobot_price_decide":
                    raise TimeoutError("possible acceptance")
                return super().call(name,args)
        with self.assertRaises(t.DecisionRefused):
            t.confirm("msp3:"+self.nonce+":y",12345,t.CHAT_ID,t.THREAD_ID,9001,
                      "msp_hermes_test_bot",client_factory=Uncertain,
                      path=self.db,clock=self.time)
        with t.connect(self.db) as db:
            self.assertEqual(db.execute("SELECT state FROM trials").fetchone()[0],"needs_review")
        with self.assertRaises(t.DecisionRefused): self.decide()
        self.assertNotIn("orgobot_price_command_status",[name for name,_ in FakeMCP.calls])

    def test_markup_and_no_second_card(self):
        btn=t.markup(self.nonce)
        self.assertEqual([x["text"] for x in btn["inline_keyboard"][0]],
                         ["Да — повысить на 25%","Нет — отказать"])
        self.assertEqual(t.create_card([12345],path=self.db)[1],9001)


if __name__=="__main__":
    unittest.main()
