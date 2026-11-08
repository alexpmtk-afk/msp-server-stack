import hashlib,importlib.util,json,subprocess,time
from pathlib import Path
SOURCE=Path('/home/hermes/.local/share/msp/finance-history-driver/driver-4d062537ea9ec7dd4200e1957828a613493facb5c00fd0fe0340ddadd9a8ccc2.py')
if hashlib.sha256(SOURCE.read_bytes()).hexdigest()!='4d062537ea9ec7dd4200e1957828a613493facb5c00fd0fe0340ddadd9a8ccc2':raise RuntimeError('driver snapshot drift')
spec=importlib.util.spec_from_file_location('finance_driver',SOURCE)
driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
driver.CABINETS=('wb_novokshenov',)
driver.STATE=Path('/home/hermes/.local/state/msp-finance-history-wb-novokshenov-20261108')
driver.EXPECTED_RELEASE='/opt/mcp/projects/msp-marketplace-reports-releases/control-638be59c983a0b6769d149cc1d577799a6aec346dabb8e83ed6d9aa18c7ac508'
driver.ROOT_PREFLIGHT_PINS[driver.EXPECTED_RELEASE]='8e9ec88f284c11a3950558633d4de674bff97e3aae55e0f419237ad89430d55d'
driver.ADMISSION_PREFLIGHT=True
original_gate=driver.gate
original_write=driver.write
TASK=Path('/home/hermes/workspace/task-visibility/task.py')
def tracked_write(path,value):
 original_write(path,value)
 if path.name!='state.json':return
 phase=value.get('phase');code='done' if phase=='COMPLETE' else ('blocked' if phase=='HOLD' else 'running')
 label={'COMPLETE':'Загрузка закончена по найденному списку; требуется итоговая сверка полноты','HOLD':'Загрузка остановлена; требуется разбор сохранённой ошибки','DISPATCHING':'Проверка архива и загрузка очередной порции','COOLDOWN':'Штатная пауза перед следующей порцией'}.get(phase,'Выполняется сбор отчётов за 2026 год')
 subprocess.run(['/usr/bin/python3',str(TASK),'wb-novokshenov-20261108',code,'--title','WB ИП Новакшенов — отчёты за 2026 год','--status',label],capture_output=True,timeout=15)
def gate(cabinet):
 path=driver.STATE/'state.json'
 current=json.loads(path.read_text()) if path.exists() else {}
 if current.get('last') is not None:return original_gate(cabinet)
 if current.get('wakes',0)!=0:raise ValueError('uncertain prior bootstrap; no repeat')
 if cabinet!='wb_novokshenov':raise ValueError('wrong campaign scope')
 installed=driver.root_json(driver.ROOT_STATE/'INSTALL.json')
 if installed.get('release')!=driver.EXPECTED_RELEASE or installed.get('schedule_enabled') is not False:raise ValueError('unexpected release or schedule')
 driver.control_preflight_verified();driver.unit_closed()
 unit=subprocess.run(['/usr/bin/systemctl','show','msp-finance-control.service','-p','ActiveState','--value'],capture_output=True,text=True,check=True,timeout=20).stdout.strip()
 if unit not in ('inactive','failed'):raise ValueError('controller active; no bootstrap')
 parent=json.loads(Path('/home/hermes/.local/state/msp-finance-history-wb-laser-master-20261106/state.json').read_text())
 req=json.loads((driver.ROOT_STATE/'inbox/request.json').read_text())
 if parent.get('phase')!='COMPLETE' or req.get('cabinet')!='wb_laser_master' or req.get('nonce')!='b677e7b7d0f142feaa54d56f774ffbeb':raise ValueError('previous campaign changed; reconcile first')
 receipt=driver.root_json(driver.ROOT_STATE/'results'/(req['nonce']+'.json'))
 if receipt!=parent.get('last') or receipt.get('status')!='PARTIAL' or receipt.get('jobs')!=[] or receipt.get('api_enabled_after_run') is not False or receipt.get('schedule_enabled') is not False:raise ValueError('previous campaign not closed')
 return 'READY'
driver.gate=gate
driver.write=tracked_write
if __name__=='__main__':raise SystemExit(driver.main())
