import csv
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

module=Path(__file__).with_name('local_reports.py')
if not module.exists():module=Path(__file__).resolve().parents[1]/'docs/data-sources/wb-financial-reports/local_reports.py'
spec=importlib.util.spec_from_file_location('reader',module)
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

class ReportsTest(unittest.TestCase):
    def setUp(self):
        scratch=Path('/home/hermes/.hermes/cache/scratch')
        self.temp=tempfile.TemporaryDirectory(dir=scratch if scratch.is_dir() else Path(__file__).resolve().parent)
        self.root=Path(self.temp.name)
        self.scope=self.root/'.b7-generations/wb_weekly_finance_main/wb_dmitrieva/2026'
        self.generation='a'*32
        self.folder=self.scope/'generations'/self.generation
        self.folder.mkdir(parents=True)
        self.rows=[]
        for i,op in enumerate(('Продажа','Возврат','Хранение','Неизвестная операция'),1):
            row={name:'0' for name in r.AMOUNTS}
            row.update(reportId=123,rrdId=i,reportType=1,currency='RUB',nmId=7,
                       sellerOperName=op,docTypeName=op if op in ('Продажа','Возврат') else '',
                       rrDate='2026-01-02',saleDt='2026-01-02T00:00:00Z',orderDt='2026-01-01T00:00:00Z',srvDbs=False)
            if op=='Продажа':row.update(retailAmount='100',forPay='80')
            if op=='Возврат':row.update(retailAmount='20',forPay='16')
            if op=='Хранение':row.update(paidStorage='5',nmId=0)
            if op=='Неизвестная операция':row.update(deduction='-3')
            self.rows.append(row)
        self.publish()

    def tearDown(self):self.temp.cleanup()

    def publish(self):
        header=list(self.rows[0])+['_raw_json']
        stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=header,delimiter=';',lineterminator='\n');writer.writeheader()
        for row in self.rows:
            writer.writerow({**{k:r.csv_cell(v) for k,v in row.items()},'_raw_json':json.dumps(row,ensure_ascii=False)})
        payload=stream.getvalue().encode('utf-8-sig')
        (self.folder/'data.csv').write_bytes(payload)
        sha=lambda b:hashlib.sha256(b).hexdigest()
        meta={'schema':1,'dataset':'wb_weekly_finance_main','cabinet':'wb_dmitrieva','period':'2026','status':'LOCAL_VERIFIED','sha256':sha(payload),'bytes':len(payload),'rows':len(self.rows)}
        metabytes=json.dumps(meta).encode();(self.folder/'data.csv.meta.json').write_bytes(metabytes)
        descriptor={'schema':2,'scope':'2026','generation':self.generation,'parent':None,'parent_sha256':None,'files':[{'path':'data.csv','sha256':sha(payload),'bytes':len(payload)},{'path':'data.csv.meta.json','sha256':sha(metabytes),'bytes':len(metabytes)}]}
        raw=json.dumps(descriptor).encode();(self.folder/'generation.json').write_bytes(raw)
        (self.scope/'CURRENT.json').write_text(json.dumps({'schema':2,'generation':self.generation,'sha256':sha(raw)}))

    def snapshot(self):return r.resolve('wb_dmitrieva',1,root=self.root)

    def test_exact_values_return_direction_and_unallocated_cost(self):
        result=r.summarize('wb_dmitrieva',(1,),root=self.root)
        self.assertEqual(result['ordinary_sales_returns'][0]['net_sales'],'80')
        self.assertEqual(result['ordinary_sales_returns'][0]['net_goods_payout'],'64')
        store=next(x for x in result['operation_breakdown'] if x['operation']=='Хранение')
        self.assertEqual(store['raw_amount_sums']['paidStorage'],'5')
        self.assertEqual(store['without_product_rows'],1)
        unknown=next(x for x in result['operation_breakdown'] if x['operation']=='Неизвестная операция')
        self.assertEqual(unknown['raw_amount_sums']['deduction'],'-3')
        self.assertEqual(result['selected_rows'],4)

    def test_sku_filter_does_not_allocate_shared_cost(self):
        result=r.summarize('wb_dmitrieva',(1,),root=self.root,nm_id='7')
        self.assertEqual(result['selected_rows'],3)
        self.assertFalse(any(x['operation']=='Хранение' for x in result['operation_breakdown']))

    def test_boolean_serialization_is_not_corruption(self):
        self.assertEqual(list(r.iter_rows(self.snapshot()))[0]['srvDbs'],'false')

    def test_semantic_amount_is_not_a_delivery_count(self):
        row={'deliveryService':'27.35','deliveryAmount':'2','returnAmount':'1','paymentProcessing':'Комиссия'}
        self.assertEqual(str(r.semantic_value(row,'delivery_fee')),'27.35')
        self.assertEqual(str(r.semantic_value(row,'delivery_count')),'2')
        self.assertEqual(r.semantic_value(row,'payment_fee_type'),'Комиссия')

    def test_loyalty_components_are_not_swapped(self):
        row={'cashbackAmount':'10','cashbackDiscount':'20','cashbackCommissionChange':'3'}
        self.assertEqual(str(r.semantic_value(row,'loyalty_points')),'10')
        self.assertEqual(str(r.semantic_value(row,'loyalty_compensation')),'20')
        self.assertEqual(str(r.semantic_value(row,'loyalty_fee')),'3')

    def test_absent_official_field_is_not_zero(self):
        self.assertIsNone(r.semantic_value(self.rows[0],'agency_vat_rate'))

    def test_reject_tampered_payload(self):
        with (self.folder/'data.csv').open('ab') as stream:stream.write(b'bad')
        with self.assertRaises(ValueError):self.snapshot()

    def test_reject_duplicate_row_identity(self):
        self.rows.append(dict(self.rows[0]));self.publish()
        with self.assertRaises(ValueError):list(r.iter_rows(self.snapshot()))

    def test_changed_current_during_iteration_rejected(self):
        snap=self.snapshot();it=r.iter_rows(snap);next(it)
        (self.scope/'CURRENT.json').write_text('{}')
        with self.assertRaises(ValueError):list(it)

    def test_boolean_or_missing_is_not_numeric_zero(self):
        for value in (None,True,False,'','NaN','Infinity'):
            with self.subTest(value=value),self.assertRaises(ValueError):r.decimal(value)

    def test_reject_traversal_and_duplicate_types(self):
        with self.assertRaises(ValueError):r.resolve('../wb_dmitrieva',1,root=self.root)
        with self.assertRaises(ValueError):r.summarize('wb_dmitrieva',(1,1),root=self.root)

    def test_ui_only_and_unknown_fields_not_zero(self):
        for field in ('loyalty_kvv_fee','row_number','does_not_exist'):
            with self.subTest(field=field),self.assertRaises(ValueError):r.semantic_value(self.rows[0],field)

    def test_date_role_and_filter(self):
        result=r.summarize('wb_dmitrieva',(1,),root=self.root,start='2026-01-02',end='2026-01-02',date_role='order_date')
        self.assertEqual(result['selected_rows'],0)

    def test_mixed_currencies_never_summed(self):
        self.rows[1]['currency']='BYN';self.publish()
        result=r.summarize('wb_dmitrieva',(1,),root=self.root)
        self.assertEqual({x['currency'] for x in result['ordinary_sales_returns']},{'RUB','BYN'})

    def test_reject_symlink_snapshot(self):
        path=self.folder/'data.csv';path.rename(self.folder/'other.csv');path.symlink_to('other.csv')
        with self.assertRaises(ValueError):self.snapshot()

if __name__=='__main__':unittest.main()
