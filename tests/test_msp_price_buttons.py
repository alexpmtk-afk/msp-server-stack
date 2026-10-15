"""Offline SIG-002 Telegram button and Orgobot guard acceptance."""
import datetime as dt
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from apps.msp_signal_notify import price_buttons as b


class FakeOrgobot:
    calls = []

    def call(self, name, args):
        self.calls.append((name, args))
        if name == "orgobot_price_decisions_list":
            return {"decisions": [
                {"id": 555, "market_article": "2791038373", "orgobot_id": 48,
                 "marketplaceid_id": 1, "blockid_id": 3, "post_id": 2666, "status": "waiting",
                 "responsible_telegram": "@group_123123123_bot"}]}
        if name == "orgobot_price_decide":
            return {"command_id": 991, "status": "queued"}
        if name == "orgobot_price_command_status":
            return {"status": "queued"}
        raise AssertionError(name)


class Sig002ButtonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "actions.sqlite3"
        self.t = dt.datetime(2026, 10, 15, tzinfo=dt.timezone.utc)
        FakeOrgobot.calls = []
        self.env = patch.dict(os.environ, {
            "MSP_PRICE_BUTTON_ALLOWED_USER_IDS": "12345",
            "MSP_PRICE_LIVE_ENABLED": "1",
            "MSP_ORGOBOT_EXECUTOR_USERNAME": "group_123123123_bot",
            "MSP_PRICE_LIVE_DECISION_IDS": "555",
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def issue(self):
        with b.connect(self.path) as db:
            token, duplicate = b.reserve(db, 2666, "2791038373", clock=self.t)
            self.assertFalse(duplicate)
            b.bind_sent(db, token, 7444)
        return token

    def click(self, token, answer="y", user_id=12345, thread=758, clock=None):
        return b.handle_click("msp2:" + token + ":" + answer,
                              user_id, -1002485321031, thread, 7444,
                              client_factory=FakeOrgobot, path=self.path, clock=clock or self.t)

    def test_markup_and_two_buttons(self):
        token = self.issue()
        kb = b.markup(token)
        self.assertEqual(len(kb["inline_keyboard"][0]), 2)
        self.assertEqual(kb["inline_keyboard"][0][0]["callback_data"], "msp2:" + token + ":y")
        self.assertEqual(kb["inline_keyboard"][0][1]["callback_data"], "msp2:" + token + ":n")
        self.assertLess(len(kb["inline_keyboard"][0][0]["callback_data"].encode()), 64)

    def test_yes_invokes_exact_orgobot_tool_and_is_idempotent(self):
        token = self.issue()
        text = self.click(token)
        self.assertIn("991", text)
        self.assertEqual([c[0] for c in FakeOrgobot.calls],
                         ["orgobot_price_decisions_list", "orgobot_price_decide"])
        self.assertEqual(FakeOrgobot.calls[1][1], {"decision_id": 555, "answer": "yes"})
        with self.assertRaises(b.DecisionRefused):
            self.click(token)
        self.assertEqual(len(FakeOrgobot.calls), 2)
        with b.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT state FROM price_buttons WHERE token=?", (token,)).fetchone()[0], "queued")

    def test_source_post_mismatch_never_invokes_price_decide(self):
        token = self.issue()
        class Mismatch(FakeOrgobot):
            def call(self, name, args):
                response = super().call(name, args)
                if name == "orgobot_price_decisions_list":
                    response["decisions"][0]["post_id"] = 2701
                return response
        with self.assertRaises(b.DecisionRefused):
            b.handle_click("msp2:" + token + ":y", 12345, -1002485321031, 758, 7444,
                           client_factory=Mismatch, path=self.path, clock=self.t)
        self.assertEqual([name for name, _ in FakeOrgobot.calls], ["orgobot_price_decisions_list"])

    def test_decision_not_allowlisted_never_mutates(self):
        token = self.issue()
        with patch.dict(os.environ, {"MSP_PRICE_LIVE_DECISION_IDS": ""}):
            with self.assertRaises(b.DecisionRefused):
                self.click(token)
        self.assertEqual([name for name, _ in FakeOrgobot.calls], ["orgobot_price_decisions_list"])

    def test_rule_outside_48_52_is_never_executed(self):
        token = self.issue()
        class UnsupportedRule(FakeOrgobot):
            def call(self, name, args):
                response = super().call(name, args)
                if name == "orgobot_price_decisions_list":
                    response["decisions"][0]["orgobot_id"] = 99
                return response
        with self.assertRaises(b.DecisionRefused):
            b.handle_click("msp2:" + token + ":y", 12345, -1002485321031, 758, 7444,
                           client_factory=UnsupportedRule, path=self.path, clock=self.t)
        self.assertEqual([name for name, _ in FakeOrgobot.calls], ["orgobot_price_decisions_list"])

    def test_no_invokes_explicit_decline(self):
        token = self.issue()
        self.click(token, answer="n")
        self.assertEqual(FakeOrgobot.calls[1][1], {"decision_id": 555, "answer": "no"})

    def test_other_user_wrong_topic_expired_and_test_only_no_mcp(self):
        token = self.issue()
        for kwargs in ({"user_id": 888}, {"thread": 25},
                       {"clock": self.t + dt.timedelta(hours=49)}):
            with self.assertRaises(b.DecisionRefused):
                self.click(token, **kwargs)
        with patch.dict(os.environ, {"MSP_PRICE_LIVE_ENABLED": "0"}):
            result = self.click(token)
            self.assertIn("ТЕСТ: принято Да", result)
            with self.assertRaises(b.DecisionRefused):
                self.click(token)
        with b.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT state FROM price_buttons WHERE token=?",
                                        (token,)).fetchone()[0], "tested")
        self.assertFalse(FakeOrgobot.calls)

    def test_status_uses_integer_command_id_and_only_reads_status(self):
        token = self.issue()
        self.click(token)
        class Finished(FakeOrgobot):
            def call(self, name, args):
                if name == "orgobot_price_command_status":
                    self.calls.append((name, args))
                    self.assertions = args
                    return {"status": "done"}
                return super().call(name, args)
        notes = []
        self.assertEqual(b.refresh_commands(lambda msg: notes.append(msg) or 100,
                                            client_factory=Finished, path=self.path), 1)
        self.assertEqual(len(notes), 1)
        self.assertEqual(FakeOrgobot.calls[-1][0], "orgobot_price_command_status")
        self.assertEqual(FakeOrgobot.calls[-1][1], {"command_id": 991})
        self.assertIs(type(FakeOrgobot.calls[-1][1]["command_id"]), int)
        with b.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT state FROM price_buttons WHERE token=?",
                                        (token,)).fetchone()[0], "done")
        self.assertEqual(b.refresh_commands(lambda msg: 1, client_factory=Finished, path=self.path), 0)

    def test_network_error_never_retries_mutation(self):
        token = self.issue()
        class BadMCP(FakeOrgobot):
            def call(self, name, args):
                if name == "orgobot_price_decide":
                    raise TimeoutError("unknown whether accepted")
                return super().call(name, args)
        with self.assertRaises(b.DecisionRefused):
            b.handle_click("msp2:" + token + ":y", 12345, -1002485321031, 758, 7444,
                           client_factory=BadMCP, path=self.path, clock=self.t)
        with self.assertRaises(b.DecisionRefused):
            self.click(token)
        with b.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT state FROM price_buttons WHERE token=?", (token,)).fetchone()[0], "needs_review")

    def test_ambiguous_orgobot_rows_block_without_decide(self):
        token = self.issue()
        class Ambiguous(FakeOrgobot):
            def call(self, name, args):
                response = super().call(name, args)
                if name == "orgobot_price_decisions_list":
                    response["decisions"].append(dict(response["decisions"][0], id=556))
                return response
        with self.assertRaises(b.DecisionRefused):
            b.handle_click("msp2:" + token + ":y", 12345, -1002485321031, 758, 7444,
                           client_factory=Ambiguous, path=self.path, clock=self.t)
        self.assertEqual([n for n, _ in FakeOrgobot.calls], ["orgobot_price_decisions_list"])


if __name__ == "__main__":
    unittest.main()
