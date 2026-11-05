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
 for n in ['control.py','worker.py','client.py','diagnostics.py','diagnostics_client.py']:files[n]=(ROOT/'scripts/finance_control'/n).read_bytes()
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
 diagnostic='[Unit]\nDescription=Read-only MSP finance diagnostics\n[Service]\nType=oneshot\nUser=root\nExecStart=/usr/bin/python3 -I -B '+release+'/diagnostics.py\nPrivateNetwork=yes\nNoNewPrivileges=yes\nProtectSystem=strict\nProtectHome=yes\nPrivateTmp=yes\nUMask=0077\nReadWritePaths=/var/lib/msp-finance-control/results\nInaccessiblePaths=/etc/msp-marketplace-reports /etc/msp-marketplace-reports-pilot /run/msp-finance-control /etc/msp-marketplace-reports-executor\nTimeoutStartSec=60\n'
 diagnostic_rule=rule.replace('msp-finance-control.service','msp-finance-diagnostics.service')
 files['units/msp-finance-diagnostics.service']=diagnostic.encode();files['units/48-msp-finance-diagnostics.rules']=diagnostic_rule.encode()
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
 # Pin the exact already-installed PR120 payload, not mutable branch state.
 old_raw=subprocess.check_output(['git','show','e418e253fc799d8a5f8b59c875bef2d3fa26fe91:docs/marketplace-reports/autonomous-control-20261105/install.py'])
 old_node=next(n for n in ast.parse(old_raw).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PACKAGE' for t in n.targets));old_package=ast.literal_eval(old_node.value)
 old_pin={k:old_package[k] for k in ('release','hashes','payload_sha256')}
 up_source=(ROOT/'scripts/finance_control/upgrade.py').read_text();up=up_source.replace('PACKAGE = {}  # BUILD_PACKAGE','PACKAGE = '+repr(package)).replace('OLD = {}  # BUILD_OLD','OLD = '+repr(old_pin)).encode();compile(up,'upgrade.py','exec')
 (OUT/'upgrade.py').write_bytes(up);up_local=Path('/home/hermes/workspace/msp-finance-diagnostics-upgrade.py');up_local.write_bytes(up)
 up_cmd='msp_diag_stage=$(mktemp -d /var/lib/msp-finance-diag.XXXXXXXX) && install -o root -g root -m 600 '+str(up_local)+' "$msp_diag_stage/upgrade.py" && printf \'%s  %s\\n\' '+sha(up)+' "$msp_diag_stage/upgrade.py" | sha256sum -c - && /usr/bin/python3 -I -B "$msp_diag_stage/upgrade.py"'
 subprocess.run(['/bin/sh','-n','-c',up_cmd],check=True);(OUT/'UPGRADE_ONE_LINE.txt').write_text(up_cmd+'\n')
 (OUT/'UPGRADE_MANIFEST.json').write_bytes(enc({'upgrade_sha256':sha(up),'old_release':old_pin['release'],'new_release':release,'root_execution':'NOT_EXECUTED','provider_calls':0}))
 print(json.dumps({'installer_sha256':sha(raw),'upgrade_sha256':sha(up),'release':release,'files':len(files)}))
if __name__=='__main__':build()
