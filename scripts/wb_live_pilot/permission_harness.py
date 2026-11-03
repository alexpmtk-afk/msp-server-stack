"""Ephemeral CI root fixture: real nobody process reads production-written approval.
No services, secrets, APIs or production paths. Root only in hosted test runner.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
import tempfile

def main():
    if os.geteuid()!=0:raise RuntimeError('root fixture required')
    source=Path(sys.argv[1]).resolve();repo=source.parents[2]
    nobody=pwd.getpwnam('nobody')
    folder=Path(tempfile.mkdtemp(prefix='msp-auth-permission-test-',dir='/var/lib'))
    os.chmod(folder,0o755)
    try:
        target=folder/'apps/msp_marketplace_reports';target.mkdir(parents=True)
        os.chmod(folder/'apps',0o755);os.chmod(target,0o755)
        for src in (repo/'apps/msp_marketplace_reports').glob('*.py'):
            p=target/src.name;p.write_bytes(src.read_bytes());os.chmod(p,0o644)
        spec=importlib.util.spec_from_file_location('actual_launcher',source);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        m.APPROVAL=folder/'approval.json'
        raw=b'{"schema":1,"fixture":"nonsecret"}\n'
        m.write_new(m.APPROVAL,raw)  # old production semantics, root0600.
        code="import sys,json,os;sys.path.insert(0,sys.argv[1]);from apps.msp_marketplace_reports.standalone_wb import read_authorization; assert os.geteuid()!=0; assert read_authorization(sys.argv[2])['fixture']=='nonsecret'; print(json.dumps({'uid':os.geteuid(),'gid':os.getegid(),'read':'PASS'}))"
        def child():
            os.setgroups([]);os.setgid(nobody.pw_gid);os.setuid(nobody.pw_uid)
        args=['/usr/bin/python3','-I','-B','-c',code,str(folder),str(m.APPROVAL)]
        red=subprocess.run(args,preexec_fn=child,capture_output=True,timeout=15)
        if red.returncode==0 or b'PermissionError' not in red.stderr:raise AssertionError('root0600 must deny actual nonroot reader')
        m.APPROVAL.unlink()
        # Same production writer, with fixture executor gid substituted only for CI nobody.
        m.EXECUTOR_GID=nobody.pw_gid
        m.write_approval(raw)
        st=m.APPROVAL.stat()
        if st.st_uid!=0 or st.st_gid!=nobody.pw_gid or st.st_mode&0o777!=0o640:raise AssertionError('approval ownership/mode')
        green=subprocess.run(args,preexec_fn=child,capture_output=True,timeout=15)
        if green.returncode:raise AssertionError('actual unprivileged accepted read failed')
        result=json.loads(green.stdout)
        if result['uid']==0 or m.APPROVAL.read_bytes()!=raw:raise AssertionError('test did not drop UID/preserve content')
        print(json.dumps({'old0600':'PermissionError','fixed0640':'PASS','actual_reader_uid':result['uid'],'actual_reader_gid':result['gid'],'root_owner_preserved':True,'provider_calls':0},sort_keys=True))
    finally:shutil.rmtree(folder)

if __name__=='__main__':main()
