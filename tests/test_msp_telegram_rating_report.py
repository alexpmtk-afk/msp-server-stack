"""Acceptance at the ordinary report seam, with synthetic source observations."""
import unittest
from unittest.mock import patch
from scripts.remote import msp_self_sku_report_cli as cli
from apps.msp_self_analytics.marketplace_rating_sources import collect_rating_evidence


class Reader:
    def __init__(self, marketplace='wb'):
        self.calls = 1
        self.marketplace = marketplace
        self.requests = []

    def call(self, name, args):
        self.calls += 1
        self.requests.append((name, args))
        if name == 'lk_wb_card_table':
            return None, 'TOOL_ERROR'
        assert name == ('wb_sku' if self.marketplace == 'wb' else 'ozon_sku')
        if args['report'] == 'comments':
            rows = [{'id': 'a', 'date': '2026-04-14', 'valuation': 2},
                    {'id': 'own', 'date': '2026-04-15', 'valuation': 5},
                    {'id': 'b', 'date': '2026-04-16', 'valuation': 4},
                    {'id': 'other-own', 'date': '2026-04-17', 'valuation': 5}]
            return (rows if self.marketplace == 'oz' else {'comments': rows}), 'PASS_JSON'
        return [{'data': d, 'rating': 4.8, 'commentsvaluation': 4.8, 'comments': 9, 'no_data': 0}
                for d in ('2026-04-13', '2026-04-14', '2026-04-15',
                          '2026-04-16', '2026-04-17', '2026-10-29')
                if args.get('d1', '') <= d <= args.get('d2', '9999')], 'PASS_JSON'


CP = {'checkpoint_number': 1, 'review_date': '2026-04-15',
      'windows': {'before': {'d1': '2026-04-13', 'd2': '2026-04-14'},
                  'after': {'d1': '2026-04-16', 'd2': '2026-04-17'}}}


class TelegramRatingReportTests(unittest.TestCase):
    def test_later_checkpoint_gets_own_eve_not_first_series_baseline(self):
        second = {'checkpoint_number': 2, 'review_date': '2026-04-17',
                  'windows': {'before': CP['windows']['before'],
                              'after': {'d1': '2026-04-18', 'd2': '2026-04-19'}}}
        got = collect_rating_evidence(Reader(), marketplace='wb', sku='123',
            checkpoints=[CP, second], as_of='2026-10-30')
        self.assertEqual(got['star_summaries'][2]['before_card_snapshot']['date'], '2026-04-16')

    def test_wb_registered_report_always_contains_new_rating_section(self):
        import tempfile
        import sqlite3
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'fixture.sqlite3'
            with sqlite3.connect(db) as c:
                c.execute('CREATE TABLE product_listing(marketplace,store,marketplace_sku,internal_article,product_name)')
                c.execute('CREATE TABLE self_purchase(marketplace,store,marketplace_sku,purchase_date,review_date,quantity,source_ordinal)')
                c.execute("INSERT INTO product_listing VALUES ('wb','fixture','123','ARTICLE','Fixture')")
                c.execute("INSERT INTO self_purchase VALUES ('wb','fixture','123','2026-04-14','2026-04-15',1,1)")
            with patch.object(cli, 'DB', db), patch.object(cli, '_price_history', return_value=([], 'UNAVAILABLE')):
                result = cli.report_card(None, None, '123', as_of='2026-10-30', provider_factory=Reader)
            self.assertIn('ОЦЕНКИ ПО ЗВЁЗДАМ', result['text'])
            self.assertIn('1★', result['text'])
            self.assertIn('Последний доступный рейтинг', result['text'])
            self.assertIn(1, result['star_summaries'])
            self.assertLessEqual(result['mpstats_calls'], 24)

    def test_both_marketplaces_show_stars_without_text_and_latest(self):
        for mp in ('wb', 'oz'):
            with self.subTest(marketplace=mp):
                reader = Reader(mp)
                got = collect_rating_evidence(reader, marketplace=mp, sku='123',
                    checkpoints=[CP, {'checkpoint_number': 2, 'review_date': '2026-04-17'}],
                    as_of='2026-10-30')
                stars = got['star_summaries'][1]
                self.assertEqual(stars['before_received_ratings']['stars']['2'], 1)
                self.assertEqual(stars['after_received_ratings']['received_count'], 1)
                self.assertEqual(stars['after_received_ratings']['mean_received_rating'], 4)
                self.assertEqual(stars['own_date_records_not_attributed']['received_count'], 2)
                self.assertEqual(stars['latest_available_card_snapshot']['date'], '2026-10-29')
                self.assertFalse(stars['complete_publication_history'])
                self.assertEqual(sum(a['report'] == 'comments' for _, a in reader.requests), 1)

    def test_regular_sku_request_without_registry_does_not_crash_or_invent_date(self):
        import tempfile
        import sqlite3
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'fixture.sqlite3'
            with sqlite3.connect(db) as c:
                c.execute('CREATE TABLE product_listing(marketplace,store,marketplace_sku,internal_article,product_name)')
                c.execute('CREATE TABLE self_purchase(marketplace,store,marketplace_sku,purchase_date,review_date,quantity,source_ordinal)')
                c.execute("INSERT INTO product_listing VALUES ('wb','fixture','123','ARTICLE','Fixture')")
            with patch.object(cli, 'DB', db):
                result = cli.report_card(None, None, '123', as_of='2026-10-30', provider_factory=Reader)
            self.assertEqual(result['status'], 'NO_REGISTERED_REVIEW_DATES')
            self.assertIn('нет зарегистрированной даты', result['text'])
            self.assertIn('1★', result['text'])
            self.assertIn('Последний доступный рейтинг', result['text'])
            self.assertFalse(result['causal_effect_proven'])
            self.assertLessEqual(result['mpstats_calls'], 24)

    def test_budget_exhaustion_is_unknown_not_empty_success(self):
        reader = Reader()
        reader.calls = 24
        result = collect_rating_evidence(reader, marketplace='wb', sku='123',
            checkpoints=[CP], as_of='2026-10-30')
        self.assertIsNone(result['star_summaries'][1]['after_received_ratings'])
        self.assertEqual(reader.calls, 24)

    def test_ozon_ordinary_report_includes_star_breakdown(self):
        rows = [{'marketplace': 'oz', 'store': 'fixture', 'marketplace_sku': '123',
                 'quantity': 1, 'purchase_date': '2026-04-14', 'review_date': '2026-04-15'}]
        with patch('apps.msp_self_analytics.sku_request.load_existing_series', return_value=rows):
            result = cli._report_ozon_ratings('fixture', '123', '2026-10-30', lambda: Reader('oz'))
        self.assertIn('1★', result['text'])
        self.assertIn('Последний доступный рейтинг', result['text'])
        self.assertIn('star_summaries', result)
