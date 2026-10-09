"""No Telegram calls; synthetic messages and temporary SQLite archives only."""
import importlib.util
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("msp_signal_notify", ROOT / "apps/msp_signal_notify/notify.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class PassiveNotifierTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.archive = self.root / "archive.sqlite3"
        self.state = self.root / "state.sqlite3"
        self.clock = date(2026, 10, 8)
        db = sqlite3.connect(self.archive)
        db.execute("""CREATE TABLE messages (
            chat_id TEXT, message_id INTEGER, text TEXT, last_received_utc TEXT)""")
        db.commit()
        db.close()

    def tearDown(self):
        self.tmp.cleanup()

    def insert(self, mid, text, when="2099-01-01T00:00:00Z"):
        with sqlite3.connect(self.archive) as db:
            db.execute("INSERT INTO messages VALUES (?,?,?,?)", (m.CHANNEL_ID, mid, text, when))

    def update(self, mid, text):
        with sqlite3.connect(self.archive) as db:
            db.execute("UPDATE messages SET text=?,last_received_utc='2099-01-02T00:00:00Z' WHERE message_id=?",
                       (text, mid))

    def run_scan(self, recipient):
        return m.run_once(self.archive, self.state, recipient, self.clock)

    def test_only_six_reviewed_types(self):
        samples = [
            ("Поднять цену", "SIG-002"),
            ("Нужно обнулить FBS для распродажи FBO", "SIG-016"),
            ("Карточки с обнуленными остатками", "SIG-015"),
            ("Превышен расход по РК", "SIG-021"),
            ("Аномально высокий ДРР", "SIG-022"),
            ("Расхождение в размерах или весе с контрольными данными", "SIG-032"),
        ]
        for title, sig in samples:
            self.assertEqual(m.identify(title)[0], sig)
        self.assertIsNone(m.identify("ТЕСТ Поднять цену"))
        self.assertIsNone(m.identify("Нужно опубликовать отзыв"))
        self.assertIsNone(m.identify("Карточки в бане!"))

    def test_price_advice_inclusive_rule_and_missing_production_date(self):
        rows = "Товар (123456789) _3 поступление 11.10.2026\nТовар (987654321) _3 поступление 12.10.2026\nТовар (112233445) _5 неизвестно"
        advice = m.price_advice(rows, self.clock)
        self.assertEqual(len(advice), 3)
        self.assertIn("НЕ поднимать", advice[0])
        self.assertIn("РЕКОМЕНДУЕТСЯ поднять", advice[1])
        self.assertIn("РЕКОМЕНДУЕТСЯ поднять", advice[2])
        self.assertIn("не заказан на производство", advice[2])
        self.assertIn("граница 11.10.2026", advice[0])

    def test_missing_production_date_and_six_days_means_raise_price(self):
        rows = "Изделие (123456789) _6   \nДругое изделие (987654321) _6"
        advice = m.price_advice(rows, date(2026, 10, 9))
        self.assertEqual(len(advice), 2)
        for item in advice:
            self.assertIn("РЕКОМЕНДУЕТСЯ поднять цену", item)
            self.assertIn("запас 6 дн.", item)
            self.assertIn("дата поступления с производства отсутствует", item)
        report = m.format_report("SIG-002", "Поднять цену", rows, 77, date(2026, 10, 9))
        self.assertIn("не заказан на производство", report)
        self.assertIn("ИМИТАЦИЯ", report)

    def test_invalid_or_stale_date_is_not_treated_as_missing(self):
        rows = ("Товар (123456789) _6 32.10.2026\n"
                "Товар (987654321) _6 01.10.2026\n"
                "Товар (112233445) дата не указана")
        advice = m.price_advice(rows, date(2026, 10, 9))
        self.assertEqual(len(advice), 3)
        for item in advice:
            self.assertIn("недостаточно данных", item)
            self.assertNotIn("РЕКОМЕНДУЕТСЯ поднять", item)

    def test_first_start_skips_old_history_and_sends_new_only(self):
        self.insert(10, "Превышен расход по РК: старый сигнал")
        outgoing = []
        sender = lambda s: outgoing.append(s) or len(outgoing)
        self.assertTrue(self.run_scan(sender)["initialized"])
        self.assertEqual(outgoing, [])
        self.insert(11, "Превышен расход по РК: кампания 777")
        first = self.run_scan(sender)
        self.assertEqual(first["sent"], 1)
        self.assertIn("777", outgoing[0])
        self.assertIn("ИМИТАЦИЯ", outgoing[0])
        self.assertIn("https://t.me/c/3375632914/11", outgoing[0])
        self.assertEqual(self.run_scan(sender)["sent"], 0)
        self.assertEqual(len(outgoing), 1)

    def test_all_six_and_edits_send_again_only_when_changed(self):
        self.run_scan(lambda msg: 1)
        headings = [
            "Поднять цену: (123456789) _3 12.10.2026",
            "Нужно обнулить FBS для распродажи FBO: SKU 10",
            "Карточки с обнуленными остатками: SKU 11",
            "Превышен расход по РК: кампания 20",
            "Аномально высокий ДРР: кампания 21",
            "Расхождение в размерах или весе с контрольными данными: SKU 31",
            "Карточки в бане!",
        ]
        for mid, text in enumerate(headings, start=20):
            self.insert(mid, text)
        outgoing = []
        send = lambda s: outgoing.append(s) or len(outgoing)
        result = self.run_scan(send)
        self.assertEqual(result["sent"], 6)
        self.assertEqual(self.run_scan(send)["sent"], 0)
        self.update(22, "Карточки с обнуленными остатками: SKU 11 и SKU 12")
        self.assertEqual(self.run_scan(send)["sent"], 1)
        self.assertEqual(len(outgoing), 7)

    def test_send_failure_does_not_mark_complete(self):
        self.run_scan(lambda msg: 1)
        self.insert(2, "Аномально высокий ДРР кампания 23")
        with self.assertRaises(RuntimeError):
            self.run_scan(lambda msg: (_ for _ in ()).throw(RuntimeError("transport")))
        outgoing = []
        result = self.run_scan(lambda msg: outgoing.append(msg) or 22)
        self.assertEqual(result["sent"], 1)
        self.assertEqual(len(outgoing), 1)
        self.assertEqual(self.run_scan(lambda msg: 23)["sent"], 0)

    def test_ignores_other_channel_in_archive(self):
        self.run_scan(lambda msg: 1)
        with sqlite3.connect(self.archive) as db:
            db.execute("INSERT INTO messages VALUES (?,?,?,?)",
                       ("-1000000000000", 3, "Поднять цену", "2099-01-01T00:00:00Z"))
        self.assertEqual(self.run_scan(lambda msg: 7)["sent"], 0)


if __name__ == "__main__":
    unittest.main()
