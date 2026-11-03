"""Root-only bounded synthetic acceptance launcher. No provider credentials/API."""
import base64,hashlib,json,os,pwd,stat,subprocess,sys,tempfile
from pathlib import Path
PAYLOAD="IiIiQm91bmRlZCBzeW50aGV0aWMtb25seSBxdW90YSBleGVyY2lzZTsgbmV2ZXIgaW1wb3J0cy9jb25zdHJ1Y3RzIEhUVFAgdHJhbnNwb3J0LgpQcmVwYXJlZCwgTk9UIGV4ZWN1dGVkIG9uIGluc3RhbGxlZCBSZWRpcy4gTWFpbiBydW5zIG9ubHkgYXMgbXNwLXJlcG9ydHMgVUlEOTk1LgoiIiIKaW1wb3J0IGFzeW5jaW8KaW1wb3J0IGJhc2U2NAppbXBvcnQganNvbgppbXBvcnQgb3MKaW1wb3J0IHNlY3JldHMKaW1wb3J0IHN5cwpmcm9tIHVybGxpYi5wYXJzZSBpbXBvcnQgdXJsc3BsaXQKClJFTEVBU0U9Jy9vcHQvbWNwL3Byb2plY3RzL21zcC1tYXJrZXRwbGFjZS1yZXBvcnRzLXJlbGVhc2VzL2MxZmVlMDcwZTllZmEwYzkyNWE3OGYyNjZmZGYwM2NiMTJhMTczY2YnCgoKZGVmIGxvb3BiYWNrX3VybCh1cmwpOgogICAgcD11cmxzcGxpdCh1cmwpCiAgICBpZiAocC5zY2hlbWUhPSdyZWRpcycgb3IgcC5ob3N0bmFtZSE9JzEyNy4wLjAuMScgb3IgcC5wb3J0IT0xNjM3OQogICAgICAgICAgICBvciBwLnBhdGghPScvMCcgb3IgcC51c2VybmFtZSE9J3F1b3RhX3J1bnRpbWUnIG9yIG5vdCBwLnBhc3N3b3JkCiAgICAgICAgICAgIG9yIHAucXVlcnkgb3IgcC5mcmFnbWVudCk6CiAgICAgICAgcmFpc2UgVmFsdWVFcnJvcignYXBwcm92ZWQgbG9jYWwgcnVudGltZSBlbmRwb2ludCByZXF1aXJlZCcpCiAgICByZXR1cm4gdXJsCgoKZGVmIGZha2VfY3JlZGVudGlhbHMoc3VmZml4KToKICAgIHBheWxvYWQ9YmFzZTY0LnVybHNhZmVfYjY0ZW5jb2RlKGpzb24uZHVtcHMoeydzaWQnOidzeW50aGV0aWMtb25seS1uby1zZWxsZXInfSkuZW5jb2RlKCkpLmRlY29kZSgpLnJzdHJpcCgnPScpCiAgICByZXR1cm4geyd0b2tlbic6J3N5bnRoZXRpYy4nK3BheWxvYWQrJy4nK3N1ZmZpeH0KCgphc3luYyBkZWYgZXhlcmNpc2UodXJsKToKICAgIGZyb20gYXBwcy5tc3BfbWFya2V0cGxhY2VfcmVwb3J0cy5zaGFyZWRfcmF0ZV9saW1pdCBpbXBvcnQgR2xvYmFsUmF0ZUNvbnRyb2xsZXIsUmF0ZVJ1bGUKICAgIGZyb20gYXBwcy5tc3BfbWFya2V0cGxhY2VfcmVwb3J0cy5xdW90YSBpbXBvcnQgcmVxdWVzdF9ydWxlcwogICAgZnJvbSBhcHBzLm1zcF9tYXJrZXRwbGFjZV9yZXBvcnRzLnByb3ZpZGVycyBpbXBvcnQgUmVxdWVzdCxXQl9ERVRBSUwsV0JfTElTVAogICAgIyBDaGVjayBhY2NlcHRlZCBhY2NvdW50IGlkZW50aXR5L2ZpbmFuY2UgZ3JvdXAgd2l0aG91dCBsb2FkaW5nIGFueSBjcmVkZW50aWFsLgogICAgZGV0YWlsPXJlcXVlc3RfcnVsZXMoJ3diJyxmYWtlX2NyZWRlbnRpYWxzKCdmaXJzdCcpLFJlcXVlc3QoJ3diJyxXQl9ERVRBSUwrJzg4MzgwMTYzMicse30pKQogICAgYWxpYXNlcz1yZXF1ZXN0X3J1bGVzKCd3YicsZmFrZV9jcmVkZW50aWFscygnc2Vjb25kJyksUmVxdWVzdCgnd2InLFdCX0xJU1Qse30pKQogICAgaWYgZGV0YWlsIT1hbGlhc2VzIG9yIHNvcnRlZChyLmludGVydmFsX3NlY29uZHMgZm9yIHIgaW4gZGV0YWlsKSE9WzYwLjAsNjUuMF06CiAgICAgICAgcmFpc2UgVmFsdWVFcnJvcignYWNjZXB0ZWQgc2VsbGVyIGZpbmFuY2UgcnVsZXMgZHJpZnQnKQogICAgIyBSZXBsYWNlIHRoZSBlbnRpcmUgc2VsbGVyIGNvbXBvbmVudDogbm8gYWN0dWFsIG9yIGhhc2hlZCBzZWxsZXIga2V5IGlzIHVzZWQuCiAgICBwcmVmaXg9J21hcmtldHBsYWNlLXJhdGU6djE6d2I6c3ludGhldGljLXBpbG90LScrc2VjcmV0cy50b2tlbl9oZXgoMTYpCiAgICBydWxlcz1bUmF0ZVJ1bGUocHJlZml4Kyc6JytyLmtleS5zcGxpdCgnOicsNClbNF0sci5pbnRlcnZhbF9zZWNvbmRzKSBmb3IgciBpbiBkZXRhaWxdCiAgICBvdGhlcj1bUmF0ZVJ1bGUocHJlZml4Kyctb3RoZXI6JytyLmtleS5zcGxpdCgnOicsNClbNF0sci5pbnRlcnZhbF9zZWNvbmRzKSBmb3IgciBpbiBkZXRhaWxdCiAgICBvbmU9R2xvYmFsUmF0ZUNvbnRyb2xsZXIocmVkaXNfdXJsPXVybCk7dHdvPUdsb2JhbFJhdGVDb250cm9sbGVyKHJlZGlzX3VybD11cmwpCiAgICB0cnk6CiAgICAgICAgaWYgb25lLmJhY2tlbmQhPSdyZWRpcycgb3IgdHdvLmJhY2tlbmQhPSdyZWRpcyc6cmFpc2UgVmFsdWVFcnJvcignUmVkaXMgcmVxdWlyZWQnKQogICAgICAgICMgVHdvIHNpbXVsdGFuZW91cyBjbGllbnRzIGZvciBvbmUgc3ludGhldGljIG93bmVyOiBleGFjdGx5IG9uZSBhZG1pc3Npb24uCiAgICAgICAgYWRtaXNzaW9ucz1hd2FpdCBhc3luY2lvLmdhdGhlcihvbmUudHJ5X2FjcXVpcmUocnVsZXMpLHR3by50cnlfYWNxdWlyZShydWxlcykpCiAgICAgICAgaWYgc29ydGVkKHhbMF0gZm9yIHggaW4gYWRtaXNzaW9ucykhPVtGYWxzZSxUcnVlXTpyYWlzZSBWYWx1ZUVycm9yKCdhdG9taWMgYWRtaXNzaW9uIGZhaWxlZCcpCiAgICAgICAgaWYgbm90IDA8bmV4dCh3YWl0IGZvciBvayx3YWl0IGluIGFkbWlzc2lvbnMgaWYgbm90IG9rKTw9NjY6cmFpc2UgVmFsdWVFcnJvcignc2FmZXR5IHdhaXQgZmFpbGVkJykKICAgICAgICBpZiBub3QgKGF3YWl0IG9uZS50cnlfYWNxdWlyZShvdGhlcikpWzBdOnJhaXNlIFZhbHVlRXJyb3IoJ293bmVyIGlzb2xhdGlvbiBmYWlsZWQnKQogICAgICAgIGF3YWl0IG9uZS5kZWZlcihydWxlcyw5MCkKICAgICAgICBhZG1pdHRlZCx3YWl0PWF3YWl0IHR3by50cnlfYWNxdWlyZShydWxlcykKICAgICAgICBpZiBhZG1pdHRlZCBvciBub3QgODU8d2FpdDw9OTE6cmFpc2UgVmFsdWVFcnJvcignY29vbGRvd24gZmFpbGVkJykKICAgICAgICAjIE5vIFNDQU4sIERFTCwgRkxVU0gsIENPTkZJRyBvciByZWFsIGtleXM7IGZvdXIgc3ludGhldGljIGtleXMsIFRUTDw9NzE1cy4KICAgICAgICByZXR1cm4geydzeW50aGV0aWNfcXVvdGEnOidQQVNTJywnY2xpZW50cyc6Miwna2V5cyc6NCwndHRsX2NlaWxpbmdfc2Vjb25kcyc6NzE1LAogICAgICAgICAgICAgICAgJ3Byb3ZpZGVyX2NhbGxzJzowLCdsaXZlX3NlbGxlcl9rZXlzX3RvdWNoZWQnOjAsJ2FwaV9lbmFibGVkJzpGYWxzZSwKICAgICAgICAgICAgICAgICdjcm9zc19ob3N0X2V4Y2x1c2lvbl9wcm92ZW4nOkZhbHNlfQogICAgZmluYWxseToKICAgICAgICBmb3IgY3RsIGluIChvbmUsdHdvKToKICAgICAgICAgICAgaWYgY3RsLl9yZWRpcyBpcyBub3QgTm9uZTphd2FpdCBjdGwuX3JlZGlzLmFjbG9zZSgpCgoKZGVmIG1haW4oKToKICAgIGlmIG9zLmdldGV1aWQoKSE9OTk1IG9yIHN5cy5hcmd2WzE6XSE9WyctLXN5bnRoZXRpYy13cml0ZS1hcHByb3ZlZCddOgogICAgICAgIHByaW50KGpzb24uZHVtcHMoeydzeW50aGV0aWNfcXVvdGEnOidCTE9DS0VEJywncmVhc29uJzonYXBwcm92ZWQgaXNvbGF0ZWQgd3JpdGUgc2NvcGUgYW5kIG1zcC1yZXBvcnRzIHJlcXVpcmVkJ30pKTtyZXR1cm4gMgogICAgdHJ5OgogICAgICAgIGlmIG9zLmVudmlyb24uZ2V0KCdNQVJLRVRQTEFDRV9SRVFVSVJFX1JFRElTJykhPScxJzpyYWlzZSBWYWx1ZUVycm9yKCdSZWRpcyByZXF1aXJlZCcpCiAgICAgICAgdXJsPWxvb3BiYWNrX3VybChvcy5lbnZpcm9uLmdldCgnTUFSS0VUUExBQ0VfTUNQX1JFRElTX1VSTCcsJycpKQogICAgICAgIHN5cy5wYXRoLmluc2VydCgwLFJFTEVBU0UpCiAgICAgICAgcmVzdWx0PWFzeW5jaW8ucnVuKGFzeW5jaW8ud2FpdF9mb3IoZXhlcmNpc2UodXJsKSx0aW1lb3V0PTIwKSkKICAgICAgICBwcmludChqc29uLmR1bXBzKHJlc3VsdCxzb3J0X2tleXM9VHJ1ZSkpO3JldHVybiAwCiAgICBleGNlcHQgRXhjZXB0aW9uIGFzIGV4YzoKICAgICAgICAjIE5vIFVSTCwgY3JlZGVudGlhbCwgZXhjZXB0aW9uIHRleHQgb3IgdHJhY2ViYWNrIGluIG91dHB1dC4KICAgICAgICBwcmludChqc29uLmR1bXBzKHsnc3ludGhldGljX3F1b3RhJzonRkFJTCcsJ2Vycm9yX3R5cGUnOnR5cGUoZXhjKS5fX25hbWVfXywncHJvdmlkZXJfY2FsbHMnOjB9KSk7cmV0dXJuIDEKCmlmIF9fbmFtZV9fPT0nX19tYWluX18nOnJhaXNlIFN5c3RlbUV4aXQobWFpbigpKQo="
DIGEST="80c1ef163ec5e31c9850232ff180e09decb85cd1e2dbd3c8867962c1e785d187"
RELEASE=Path('/opt/mcp/projects/msp-marketplace-reports-releases/c1fee070e9efa0c925a78f266fdf03cb12a173cf')
def main():
    if os.geteuid()!=0 or sys.argv[1:]!=['--synthetic-write-approved']:
        print('BLOCKED: root and explicit synthetic-only approval required');return 2
    user=pwd.getpwnam('msp-reports')
    if (user.pw_uid,user.pw_gid)!=(995,985):raise ValueError('existing identity drift')
    if Path('/etc/msp-marketplace-reports-executor/approval.json').exists():raise ValueError('provider approval must remain absent')
    env=Path('/etc/msp-marketplace-reports-executor/redis-runtime.env')
    for p in [env,*env.parents]:
        st=p.lstat()
        if stat.S_ISLNK(st.st_mode) or st.st_uid!=0 or st.st_mode&0o022:raise ValueError('unsafe Redis EnvFile path')
    if stat.S_IMODE(env.stat().st_mode)!=0o600:raise ValueError('Redis EnvFile mode')
    # Never open/read/print/copy the EnvFile: PID1 injects it into nonroot service.
    data=base64.b64decode(PAYLOAD)
    if hashlib.sha256(data).hexdigest()!=DIGEST:raise ValueError('probe digest')
    folder=Path(tempfile.mkdtemp(prefix='msp-quota-probe-',dir='/var/lib'))
    script=folder/'probe.py'
    fd=os.open(script,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as f:
        f.write(data);f.flush();os.fchown(f.fileno(),0,0);os.fchmod(f.fileno(),0o644);os.fsync(f.fileno())
    os.chmod(folder,0o755)
    cmd=['/usr/bin/systemd-run','--quiet','--wait','--collect','--pipe','--unit='+folder.name,
         '-p','User=msp-reports','-p','Group=msp-reports','-p','UMask=0077',
         '-p','EnvironmentFile='+str(env),'-p','NoNewPrivileges=yes',
         '-p','ProtectSystem=strict','-p','ProtectHome=yes','-p','PrivateTmp=yes',
         '-p','IPAddressDeny=any','-p','IPAddressAllow=127.0.0.1/32','-p','RuntimeMaxSec=30',
         str(RELEASE/'.venv/bin/python'),'-I','-B',str(script),'--synthetic-write-approved']
    run=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=45,check=False)
    # stdout is the fixed redacted probe result. Never relay arbitrary stderr.
    try:
        result=json.loads(run.stdout)
        if run.returncode or result.get('synthetic_quota')!='PASS' or result.get('provider_calls')!=0:raise ValueError()
    except (ValueError,UnicodeError):
        result={'synthetic_quota':'FAIL','systemd_exit':run.returncode,'provider_calls':0,'api_enabled':False}
    receipt={'probe_sha256':DIGEST,'result':result,'report_approval_created':False}
    p=folder/'result.json';fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as f:
        json.dump(receipt,f,sort_keys=True);f.flush();os.fchmod(f.fileno(),0o600);os.fsync(f.fileno())
    print(json.dumps({'receipt':str(p),**result},sort_keys=True))
    return 0 if result['synthetic_quota']=='PASS' else 1
if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:
        print(json.dumps({'synthetic_quota':'FAIL','error_type':type(exc).__name__,'provider_calls':0}));sys.exit(1)
