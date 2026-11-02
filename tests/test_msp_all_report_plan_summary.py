"""The ordinary WB/Ozon report shows independent plans even without review dates."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts.remote import msp_self_sku_report_cli as cli

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('plan_summary_sync',ROOT/'apps/msp_data_sync/sync.py')
sync=importlib.util.module_from_spec(spec);spec.loader.exec_module(sync)

class Reader:
    calls=1
    def call(self,name,args):
        self.calls+=1
        return ({'comments':[]} if name=='wb_sku' and args['report']=='comments' else []),'PASS_JSON'

class AllReportPlanSummaryTests(unittest.TestCase):
    def test_both_platforms_show_plan_and_fact_with_no_review_date(self):
        for market in ('wb','oz'):
            with self.subTest(market=market),tempfile.TemporaryDirectory() as tmp:
                db=Path(tmp)/'fixture.sqlite3';c=sync.dbopen(db)
                sync.product(c,[['мп','магазин','market_article','артикул_мп','артикул_наш','артикул_наш_▼','наименование 1С'],
                                [market,'laser','123','123','ART','ART','Fixture']],sync.begin_run(c,'product_catalog'))
                source=[['мп','магазин','market_article','артикул_наш_▼','наименование 1С','Кол-во выкупов','Дата выкупа','Дата отзыва','Кол-во отзывов','Ссылка на отзыв','Черновик отзывов'],
                        [market,'laser','123','ART','Fixture','3','01.04.2026','','2','',''],
                        [market,'laser','123','ART','Fixture','3','02.04.2026','','2','',''],
                        [market,'laser','123','ART','Fixture','3','','','2','','']]
                sync.selfbuy(c,source,sync.begin_run(c,'self_purchase'),{'legal_entity_store_mapping':{}});c.commit();c.close()
                with patch.object(cli,'DB',db):
                    result=cli.report_card(None,None,'123',as_of='2026-11-02',provider_factory=Reader)
                self.assertIn('План выкупов: 3; план отзывов: 2',result['text'])
                self.assertEqual(result['card_plan']['recorded_purchase_rows'],2)
                self.assertEqual(result['card_plan']['planned_rows_without_purchase'],1)
                self.assertEqual(result['card_plan']['recorded_review_rows'],0)
                self.assertEqual(result['status'],'NO_REGISTERED_REVIEW_DATES')
