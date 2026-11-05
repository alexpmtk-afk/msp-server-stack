"""Self-contained, checksum-pinned one-time controller installation. Does not run it."""
import ast,base64,hashlib,json,ipaddress,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'docs/marketplace-reports/autonomous-control-20261105'
def sha(b):return hashlib.sha256(b).hexdigest()
def enc(v):return (json.dumps(v,sort_keys=True,separators=(',',':'))+'\n').encode()
def build():
 old=(ROOT/'docs/marketplace-reports/history-first-20261103/history.py').read_bytes();assert sha(old)=='cb1bb6e097c23ab3d42a505076f29ce4d7df4e76a3e30eb20694ed8e0e90c3ee'
 node=next(n for n in ast.parse(old).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PACKAGE' for t in n.targets));accepted=ast.literal_eval(node.value)
 files={n:base64.b64decode(v) for n,v in accepted['files'].items() if n.startswith('apps/')}
 for n in ['standalone_wb.py','finance_receipts.py']:files['apps/msp_marketplace_reports/'+n]=(ROOT/'scripts/finance_control/overlays'/n).read_bytes()
 for n in ['control.py','worker.py','client.py']:files[n]=(ROOT/'scripts/finance_control'/n).read_bytes()
 files['pilot_supervisor.py']=(ROOT/'scripts/finance_control/supervisor.py').read_bytes()
 files['build-source.sha256']=sha(Path(__file__).read_bytes()).encode()
 release='/opt/mcp/projects/msp-marketplace-reports-releases/control-'+sha(enc({n:sha(b) for n,b in files.items()}))
 files={n:b.replace(b'__CONTROL_RELEASE__',release.encode()) for n,b in files.items()}
 assets=accepted['accepted_assets'];assets['runtime_files']={r['path']:r['sha256'] for r in accepted['runtime_records']}
 assets['runner_base64']=base64.b64encode(files['worker.py']).decode();assets['runner_sha256']=sha(files['worker.py'])
 assets['app_code_sha256']=sha(enc({Path(n).name:sha(b) for n,b in files.items() if n.startswith('apps/')}))
 files['assets.json']=enc(assets);files['pilot_supervisor.py']=(ROOT/'scripts/finance_control/supervisor.py').read_bytes()
 common='\nNoNewPrivileges=yes\nProtectSystem=strict\nProtectHome=yes\nPrivateTmp=yes\nUMask=0077\nRestart=no\nReadWritePaths=/var/lib/msp-finance-control /etc/msp-marketplace-reports-executor /run/systemd/system /run/msp-finance-control\n'
 python='/opt/mcp/projects/msp-marketplace-reports-releases/c1fee070e9efa0c925a78f266fdf03cb12a173cf/.venv/bin/python'
 # Exact resolver hosts only; controller itself has no provider HTTP client.
 dns=['127.0.0.1']
 for line in Path('/etc/resolv.conf').read_text().splitlines():
  f=line.split()
  if len(f)>1 and f[0]=='nameserver':dns.append(str(ipaddress.ip_address(f[1])))
 allow=' '.join(sorted(set(dns)))
 control='[Unit]\nDescription=Bounded MSP finance administrative control (not a financial sender)\nRequires=msp-finance-recover.service\nAfter=msp-finance-recover.service\n[Service]\nType=oneshot\nUser=root\nExecStart='+python+' -I -B '+release+'/control.py\nExecStopPost='+python+' -I -B '+release+'/control.py --close\nTimeoutStartSec=1000\nTimeoutStopSec=150\nIPAddressDeny=any\nIPAddressAllow='+allow+'\n'+common
 recover='[Unit]\nDescription=Close owned MSP finance activation after boot; never downloads\nAfter=local-fs.target systemd-tmpfiles-setup.service\nBefore=msp-finance-control.service msp-wb-pilot.service\n[Service]\nType=oneshot\nRemainAfterExit=yes\nUser=root\nExecStart='+python+' -I -B '+release+'/control.py --recover\nTimeoutStartSec=150\nPrivateNetwork=yes\n'+common+'\n[Install]\nWantedBy=multi-user.target\n'
 rule='polkit.addRule(function(action, subject) {\n  if (action.id === "org.freedesktop.systemd1.manage-units" && action.lookup("unit") === "msp-finance-control.service" && action.lookup("verb") === "start" && subject.user === "hermes") { return polkit.Result.YES; }\n});\n'
 files['units/msp-finance-control.service']=control.encode();files['units/msp-finance-recover.service']=recover.encode();files['units/49-msp-finance-control.rules']=rule.encode()
 hashes={n:sha(b) for n,b in files.items()};files['files.json']=enc(hashes)
 package={'release':release,'files':{n:base64.b64encode(b).decode() for n,b in files.items()},'hashes':{n:sha(b) for n,b in files.items()}}
 package['payload_sha256']=sha(enc(package['hashes']))
 source=(ROOT/'scripts/finance_control/install.py').read_text();raw=source.replace('PACKAGE = {}  # BUILD_PACKAGE','PACKAGE = '+repr(package)).encode();compile(raw,'install.py','exec')
 OUT.mkdir(exist_ok=True);(OUT/'install.py').write_bytes(raw)
 local=Path('/home/hermes/workspace/msp-finance-control-install.py');local.write_bytes(raw)
 cmd='msp_control_stage=$(mktemp -d /var/lib/msp-control-install.XXXXXXXX) && install -o root -g root -m 600 '+str(local)+' "$msp_control_stage/install.py" && printf \'%s  %s\\n\' '+sha(raw)+' "$msp_control_stage/install.py" | sha256sum -c - && /usr/bin/python3 -I -B "$msp_control_stage/install.py"'
 assert len(cmd.splitlines())==1;subprocess.run(['/bin/sh','-n','-c',cmd],check=True);(OUT/'ROOT_ONE_LINE.txt').write_text(cmd+'\n')
 for n,b in files.items():
  if n.startswith('units/'):(OUT/Path(n).name).write_bytes(b)
 (OUT/'MANIFEST.json').write_text(json.dumps({'installer_sha256':sha(raw),'release':release,'payload_sha256':package['payload_sha256'],'files':[{'path':n,'sha256':h} for n,h in package['hashes'].items()],'root_execution':'NOT_EXECUTED','daily_timer':False},indent=2)+'\n')
 print(json.dumps({'installer_sha256':sha(raw),'release':release,'files':len(files)}))
if __name__=='__main__':build()
