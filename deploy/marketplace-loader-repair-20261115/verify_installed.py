"""Independent read-only production acceptance; never starts source requests."""
from pathlib import Path
import json,hashlib,csv,io,sys,datetime,subprocess
b=Path(__file__).resolve().parent
installation=json.loads(Path('/var/lib/msp-ozon-calendar-repair-20261115/installation.json').read_text());root=Path(installation['root_release']);package=json.loads((b/'package-receipt.json').read_text());manifest=json.loads((root/'MANIFEST.json').read_text())
assert hashlib.sha256((root/'MANIFEST.json').read_bytes()).hexdigest()==package['manifest_sha256']
for n,h in manifest.items():assert hashlib.sha256((root/n).read_bytes()).hexdigest()==h,n
sys.path.insert(0,str(root/'ozon/ozon_dmitrieva'))
from apps.msp_marketplace_reports.generation_store import read_active,read_generation
archive=Path('/opt/mcp/data/msp-marketplace-reports');audit=json.loads((b/'live-audit.json').read_text());cid='c6bf23a1e0b54b1a8f218fece1126e11';day='2026-11-14';results={}
def keyed(raw):
 values=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig')),delimiter=';'));d={(r['date'],r['accrual_id']):r for r in values};assert len(d)==len(values);return d
for cab in ('ozon_dmitrieva','ozon_laser_master','ozon_novokshenov'):
 history=archive/'ozon-daily-accruals'/cab
 state=history/day/cid/'attempt-01';receipt=json.loads((state/'worker-result.json').read_text());old_error=state/'worker-result.preflight-hold-20261115.json';error=json.loads(old_error.read_text())
 assert receipt['status']=='VERIFIED' and receipt['source_and_published_match'] and receipt['other_days_preserved'] and receipt['attempt']==1 and receipt['cycle_id']==cid
 assert error['status']=='HOLD' and error['error_type']=='AccrualError' and old_error.stat().st_uid==995
 snap=read_active(archive,'ozon_current_accruals',cab,'2026-11');actual=keyed(snap['files']['data.csv']);prior=audit['ozon'][cab]['generation']
 prior_receipts=[json.loads(p.read_text()) for p in (history/'2026-11-13').glob('*/attempt-*/worker-result.json')]
 pin=next(v['manifest_sha256'] for v in prior_receipts if v.get('generation')==prior and v.get('status')=='VERIFIED')
 before=read_generation(archive,'ozon_current_accruals',cab,'2026-11',prior,expected_digest=pin);previous=keyed(before['files']['data.csv'])
 assert {k:v for k,v in actual.items() if k[0]!=day}==previous,'Other dates changed'
 expected=keyed((state/'month.csv').read_bytes());assert {k:v for k,v in actual.items() if k[0]==day}==expected
 rawrows=[]
 for entry in sorted((state/day).glob('*.entry.json')):
  stem=entry.name.removesuffix('.entry.json');request=json.loads(entry.read_text());response=(entry.parent/(stem+'.response.json')).read_bytes();meta=json.loads((entry.parent/(stem+'.meta.json')).read_text())
  assert request['cabinet']==cab and request['body']['date']==day and meta['status']==200 and hashlib.sha256(response).hexdigest()==meta['sha256'];rawrows.extend(json.loads(response)['accruals'])
 assert len(rawrows)==len(expected)==receipt['rows']
 assert {str(r['accrual_id']):r for r in rawrows}=={r['accrual_id']:json.loads(r['_raw_json']) for r in expected.values()}
 results[cab]={'status':'VERIFIED','day_rows':len(expected),'month_rows':len(actual),'other_days_unchanged':True,'raw_response_equals_published_day':True,'source_entries':receipt['send_entries'],'attempt':receipt['attempt'],'generation':snap['generation'],'original_error_retained':True}
progress=json.loads(Path('/var/lib/msp-finance-control/results/ozon-daily.json').read_text());assert progress['status']=='VERIFIED' and progress['verified_reports']==3
cfg=json.loads(Path('/var/lib/msp-ozon-daily/schedule.json').read_text());assert cfg['calendar_policy']==installation['policy'] and cfg['root_release']==str(root/'ozon') and cfg['consolidated_notices'] is True
system={}
for unit in ('msp-ozon-daily.service','msp-wb-pilot.service','msp-finance-notices.service','msp-ozon-daily.timer','msp-wb-daily-weekly.timer'):
 raw=subprocess.check_output(['systemctl','show',unit,'-p','ActiveState','-p','ExecStart','-p','PrivateNetwork','-p','DropInPaths','-p','UnitFileState','-p','NextElapseUSecRealtime','-p','Result'],text=True);s=dict(x.split('=',1) for x in raw.splitlines() if '=' in x);system[unit]=s
assert str(root/'ozon/controller.py') in system['msp-ozon-daily.service']['ExecStart']
assert system['msp-wb-pilot.service']['PrivateNetwork']=='yes' and system['msp-wb-pilot.service']['DropInPaths']=='' and system['msp-wb-pilot.service']['ActiveState']=='inactive'
for unit in ('msp-ozon-daily.timer','msp-wb-daily-weekly.timer'):assert system[unit]['ActiveState']=='active' and system[unit]['UnitFileState']=='enabled'
assert system['msp-finance-notices.service']['ActiveState']=='active'
result={'status':'INSTALLED_AND_RECOVERY_VERIFIED','verified_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'installation':installation,'cabinets':results,'system':system,'manifest_files_verified':len(manifest),'verification_provider_calls':0}
(b/'installed-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'status':result['status'],'cabinets':results,'ozon_next':system['msp-ozon-daily.timer']['NextElapseUSecRealtime'],'wb_next':system['msp-wb-daily-weekly.timer']['NextElapseUSecRealtime']},ensure_ascii=False))
