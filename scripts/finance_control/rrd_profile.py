"""Fixed report-only read-only forensic export. No credentials, network or repair."""
import hashlib,importlib.util,json,os,stat,sys,fcntl
from pathlib import Path
ARCHIVE=Path('/opt/mcp/data/msp-marketplace-reports')
STATE=Path('/var/lib/msp-finance-control')
PLAN={'schema':1,'cabinet':'wb_laser_master','year':2026,'report_id':601780521,'report_type':1,'max_send_entries':3}
def digest(value):return hashlib.sha256((json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n').encode()).hexdigest()
def analyze(page,previous,cursor,*,report_id=601780521,report_type=1):
 seen={};conflicts=[]
 for rows in previous:
  for row in rows:
   ident=row['rrdId'];value=digest(row)
   if ident in seen and seen[ident]!=value:raise ValueError('conflicting acknowledged identity')
   seen[ident]=value
 ids=[];metadata=[];reversals=[];duplicates=[];new={};old_equal=[];old_conflict=[]
 new_lower=[];identical=[];conflicting=[]
 previous_id=cursor
 for index,row in enumerate(page['rows']):
  ident=row.get('rrdId')
  if type(ident) is not int or ident<=0:raise ValueError('non-integer row identifier')
  if row.get('reportId')!=report_id or row.get('reportType')!=report_type:raise ValueError('foreign row identity')
  value=digest(row);ids.append(ident);metadata.append({'index':index,'rrdId':ident,'row_sha256':value})
  if ident<=previous_id:reversals.append({'index':index,'previous':previous_id,'current':ident})
  if ident in new:
   duplicates.append({'index':index,'rrdId':ident,'same_payload':new[ident]==value})
  new[ident]=value
  if ident in seen:
   (identical if seen[ident]==value else conflicting).append(ident)
  elif ident<=cursor:new_lower.append(ident)
  if ident<=cursor:
   (old_equal if seen.get(ident)==value else old_conflict).append(ident)
  previous_id=ident
 return {'cursor':cursor,'rows_received':len(ids),'unique_ids':len(set(ids)),
         'minimum_id':min(ids) if ids else None,'maximum_id':max(ids) if ids else None,
         'last_id':ids[-1] if ids else None,'last_is_maximum':bool(ids) and ids[-1]==max(ids),
         'adjacent_order_violations':reversals,'within_response_duplicates':duplicates,
         'verified_previous_identical_ids':old_equal,'previous_or_unknown_conflicting_ids':old_conflict,
         'new_ids_below_cursor':new_lower,'identical_previous_ids':identical,
         'conflicting_previous_ids':conflicting,'rows':metadata,'provider_calls':0}
def trusted(path):
 for p in [path,*path.parents]:
  st=p.lstat()
  if st.st_uid!=0 or stat.S_ISLNK(st.st_mode) or st.st_mode&0o022:raise ValueError('untrusted root code')
def main():
 if os.geteuid()!=0 or sys.argv[1:]:raise ValueError('root fixed read-only profile only')
 trusted(Path(__file__))
 lock=os.open(STATE/'controller.lock',os.O_RDONLY|os.O_NOFOLLOW);fcntl.flock(lock,fcntl.LOCK_SH|fcntl.LOCK_NB)
 if (STATE/'active-run.json').exists():raise ValueError('financial execution active')
 release=Path(json.loads((STATE/'INSTALL.json').read_text())['release']);trusted(release)
 if release!=Path('/opt/mcp/projects/msp-marketplace-reports-releases/control-a99cbd5e98205875d59e2e305da00d15f9a7fb922ac1646796314271007224ad'):raise ValueError('different installed release')
 sys.path.insert(0,str(release));spec=importlib.util.spec_from_file_location('control_profile',release/'control.py');control=importlib.util.module_from_spec(spec);spec.loader.exec_module(control);control.verify_payload()
 from apps.msp_marketplace_reports import standalone_wb as s,wb_page_resume as p
 from diagnostics import publish
 s.reconcile_admission(ARCHIVE,PLAN)
 budget=s.read_control(ARCHIVE/'.wb-executor'/(s._digest(PLAN)+'.json'));seal=budget.pop('state_sha256',None)
 if seal!=s._digest(budget) or seal!='bf7b0f8abb68e42e38b16f38315ccdef26d7e9905e3440d1e380bb30a32a3c35':raise ValueError('changed selected budget; do not retry')
 folder=p._dir(ARCHIVE,PLAN['cabinet'],2026,601780521,1);state=p._read_json(folder/'state.json',required=True)
 p._validate_state(state,PLAN['cabinet'],2026,601780521,1);p._verify_pages(folder,state,601780521,1)
 raw_path=folder/('response-'+str(state['current_rrd_id'])+'.json');page,raw=p._read_json(raw_path,required=True,with_bytes=True)
 if page['payload_sha256']!=p._sha(p._canonical({k:v for k,v in page.items() if k!='payload_sha256'})):raise ValueError('response checksum mismatch')
 if page['report_id']!=601780521 or page['report_type']!=1 or page['cursor']!=state['current_rrd_id']:raise ValueError('foreign response envelope')
 previous=[p._read_json(folder/('page-'+str(entry['cursor'])+'.json'),required=True)['rows'] for entry in state['pages']]
 out=analyze(page,previous,state['current_rrd_id']);out.update(report_id=601780521,cabinet=PLAN['cabinet'],budget_entries=budget['send_entries'],budget_state_sha256=seal,response_sha256=hashlib.sha256(raw).hexdigest(),status='READ_ONLY_PROFILE_COMPLETE')
 publish(STATE/'results',out,name='wb-601780521-rrd-profile.json')
 print(json.dumps({k:v for k,v in out.items() if k!='rows'},sort_keys=True));os.close(lock)
if __name__=='__main__':
 try:main()
 except Exception as exc:print(json.dumps({'status':'HOLD','error_type':type(exc).__name__,'provider_calls':0}));raise SystemExit(1)
