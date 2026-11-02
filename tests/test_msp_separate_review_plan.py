"""Independent non-additive purchase and review targets; synthetic data only."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from apps.msp_self_analytics.series_analysis import analyze_series
from apps.msp_self_analytics.sku_request import load_existing_series

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('separate_plan_sync',ROOT/'apps/msp_data_sync/sync.py')
sync=importlib.util.module_from_spec(spec);spec.loader.exec_module(sync)


def rows(review_plan=2):
    return [{'marketplace':'wb','store':'laser','marketplace_sku':'123','quantity':3,
             'planned_review_count':review_plan,'purchase_date':'2026-04-0'+str(i),
             'review_date':'2026-04-0'+str(i+1) if i<3 else None,'source_row':i}
            for i in (1,2,3)]


class SeparateReviewPlanTests(unittest.TestCase):
    def test_three_purchases_two_reviews_complete_independent_plans(self):
        result=analyze_series(rows(),as_of='2026-11-02')
        self.assertEqual(result['planned_total_per_card'],3)
        self.assertEqual(result['planned_review_total_per_card'],2)
        self.assertEqual(result['remaining_reviews_against_plan'],0)
        self.assertEqual(result['series_phase'],'REPORTED_SERIES_COMPLETE_PUBLICATION_UNVERIFIED')
        self.assertFalse(result['five_star_public_rating_confirmed_from_registry'])

    def test_missing_review_plan_never_defaults_to_purchase_plan(self):
        r=rows()
        for row in r:row.pop('planned_review_count')
        result=analyze_series(r,as_of='2026-11-02')
        self.assertIsNone(result['planned_review_total_per_card'])
        self.assertIsNone(result['remaining_reviews_against_plan'])
        self.assertEqual(result['series_phase'],'PURCHASE_PLAN_COMPLETE_REVIEW_PLAN_UNKNOWN')

    def test_zero_review_plan_is_known_and_conflicts_are_not_summed(self):
        r=rows(0)
        for row in r:row['review_date']=None
        self.assertEqual(analyze_series(r,as_of='2026-11-02')['planned_review_total_per_card'],0)
        r[1]['planned_review_count']=1
        result=analyze_series(r,as_of='2026-11-02')
        self.assertIsNone(result['planned_review_total_per_card'])
        self.assertEqual(result['planned_review_total_values_conflict'],[0,1])

    def test_new_csv_column_reaches_the_ordinary_analytics_loader(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/'test.sqlite3';c=sync.dbopen(db)
            sync.product(c,[['мп','магазин','market_article','артикул_мп','артикул_наш','артикул_наш_▼','наименование 1С'],
                            ['wb','laser','123','123','ART','ART','Fixture']],sync.begin_run(c,'product_catalog'))
            header=['мп','магазин','market_article','артикул_наш_▼','наименование 1С','Кол-во выкупов','Дата выкупа','Дата отзыва','Кол-во отзывов','Ссылка на отзыв','Черновик отзывов']
            source=[header,['wb','laser','123','ART','Fixture','3','01.04.2026','02.04.2026','2','',''],
                    ['wb','laser','123','ART','Fixture','3','02.04.2026','','2','','']]
            cfg={'legal_entity_store_mapping':{}}
            for _ in range(2):
                result=sync.selfbuy(c,source,sync.begin_run(c,'self_purchase'),cfg)
                self.assertEqual(result['rejected'],0)
            c.commit();c.close()
            got=load_existing_series(db,marketplace='wb',store='laser',sku='123')
            self.assertEqual(len(got),2)
            self.assertEqual([r['planned_review_count'] for r in got],[2,2])

