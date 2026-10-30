"""Check captured independent results for the pinned R97 recheck."""
import json,sys
from pathlib import Path
p=Path(sys.argv[1])
def read(name):return [json.loads(x) for x in (p/name).read_text().splitlines()]
for name,want in [('results.jsonl',True),('baseline_results.jsonl',False)]:
 for x in read(name):
  if x['check'].startswith('R97_1_'):assert x['journal_directory_resynced'] is want
  if x['check']=='R97_2_SCHEMA_TYPES':
   assert len(x['cases'])==16
   if want:assert all(y['blocked'] and y['unchanged'] for y in x['cases'])
   else:assert sum(not y['blocked'] for y in x['cases'])==4
extra=read('extra_results.jsonl');assert len(extra)==49 and all(x['status']=='PASS' for x in extra[:-1])
ad=read('admission_review_results.jsonl')[-1];reg=read('regression_review_results.jsonl')[-1]
counts={'stage3':61,'extra':extra[-1]['cases'],'admission':sum(v for k,v in ad.items() if k!='check'),'stage2_regression':sum(v for k,v in reg.items() if k!='check'),'core':read('core_control_results.jsonl')[-1]['core_cases']}
assert all(not x.read_bytes() for x in p.glob('*errors.txt'))
assert 'STOCK_TESTS 140 PASS' in (p/'stock_tests.txt').read_text()
assert read('concurrency_results.jsonl')[-1]['cases']==2
expected=json.loads((p/'summary.json').read_text());assert expected['counts']==counts and expected['total_new_commit']==sum(counts.values())
print(json.dumps(dict(total=sum(counts.values()),stock=140,baseline=59,validation='PASS')))
