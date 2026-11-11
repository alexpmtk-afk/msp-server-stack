"""Install one pinned scoped service, start via the owner's common run.py."""
import os,json,time,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import year_root as h
import root_common as r

RUNNER=Path('/home/hermes/workspace/task-visibility/run.py')

def rule_text():
    return ('polkit.addRule(function(action, subject) {\n'
            '  if (subject.user === "hermes" && action.id === "org.freedesktop.systemd1.manage-units" &&\n'
            '      action.lookup("unit") === "'+h.UNIT+'" && action.lookup("verb") === "start") {\n'
            '    return polkit.Result.YES;\n  }\n});\n').encode()

def service_text():
    return ('[Unit]\nDescription=Fixed Dmitrieva Ozon Jan-Oct2026 accruals\n'
            '[Service]\nType=oneshot\nUser=root\nUMask=0077\nRestart=no\nNoNewPrivileges=yes\n'
            'TimeoutStartSec=100000\nRuntimeMaxSec=100000\nStandardOutput=null\n'
            'StandardError=file:'+str(h.ROOT/'year.stderr')+'\n'
            'ExecStart=/usr/bin/python3 -I -B '+str(h.ROOT/'year_root.py')+'\n'
            'ExecStopPost=/usr/bin/python3 -I -B '+str(h.ROOT/'year_root.py')+' --cleanup\n').encode()

def main():
    if os.geteuid()!=0:raise PermissionError('root console required')
    h.preflight()
    for p in (h.UNIT_FILE,h.RULE,h.ROOT/'setup-ownership.json',h.ROOT/'approval.json'):
        if p.exists() or p.is_symlink():raise ValueError('existing setup; reconcile, no reset')
    if r.run(['/usr/bin/systemctl','show',h.UNIT,'-p','LoadState']).strip()!=b'LoadState=not-found':raise ValueError('preexisting unit')
    if r.run(['/usr/bin/systemctl','is-active','polkit.service']).strip()!=b'active':raise ValueError('authorization service unavailable')
    r.trust(h.UNIT_FILE.parent);r.trust(h.RULE.parent)
    service=service_text();rule=rule_text()
    r.save(h.ROOT/'setup-ownership.json',r.doc({'unit_sha256':r.sha(service),'rule_sha256':r.sha(rule)}),0o600)
    r.save(h.ROOT/'approval.json',r.doc({'cabinet':h.CABINET,'year':2026,'from_month':1,'to_month':10,'start_before_epoch':time.time()+1200,'max_new_send_entries':1152}),0o644)
    r.save(h.UNIT_FILE,service,0o644);r.save(h.RULE,rule,0o644)
    r.run(['/usr/bin/systemctl','daemon-reload'])
    env=['/usr/sbin/runuser','-u','hermes','--','/usr/bin/env','--ignore-environment','HOME=/home/hermes','USER=hermes','PATH=/usr/sbin:/usr/bin:/sbin:/bin','XDG_RUNTIME_DIR=/run/user/1001','DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1001/bus']
    # Foreground permission-only probe (no service start), allows policy reload.
    for i in range(10):
        try:
            r.run(env+['/usr/bin/python3','-I','-B',str(h.ROOT/'check_permission.py')]);break
        except RuntimeError:
            if i==9:raise
            time.sleep(1)
    verify=json.dumps(['/usr/bin/python3','-I','-B',str(h.ROOT/'verify_results.py')])
    launched=r.run(env+['/usr/bin/python3','-I','-B',str(RUNNER),h.TASK,'--title','Начисления Ozon ИП Дмитриева: январь–октябрь2026','--cwd','/home/hermes/workspace','--verify-command',verify,'--','/usr/bin/systemctl','--no-ask-password','start','--wait',h.UNIT])
    print(launched.decode().strip())
    print('REQUEST_REGISTERED_NOT_YET_COMPLETE')
    print('PROGRESS '+str(h.PUBLIC))

if __name__=='__main__':main()
