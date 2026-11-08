"""Build a self-contained repair against a checked installed immutable baseline."""
import ast,base64,hashlib,json,subprocess,tempfile
from pathlib import Path
import build as base
ROOT=base.ROOT;OUT=base.OUT

def main():
 with tempfile.TemporaryDirectory(prefix='lineage-build-',dir='/home/hermes/.hermes/cache/scratch') as directory:
  base.OUT=Path(directory)
  base.build()
  generated=(base.OUT/'install.py').read_text()
 base.OUT=OUT
 node=next(n for n in ast.parse(generated).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PACKAGE' for t in n.targets));package=ast.literal_eval(node.value)
 old=json.loads((OUT/'LINEAGE_OLD_PIN.json').read_text());release=package['release'];files={n:base64.b64decode(v) for n,v in package['files'].items()}
 upgrade=(ROOT/'scripts/finance_control/upgrade.py').read_text().replace('PACKAGE = {}  # BUILD_PACKAGE','PACKAGE = '+repr(package)).replace('OLD = {}  # BUILD_OLD','OLD = '+repr(old))
 up=Path('/home/hermes/workspace/msp-finance-lineage-upgrade.py');up.write_text(upgrade);compile(upgrade,str(up),'exec')
 resume=(ROOT/'scripts/finance_control/resume_lineage_recovery.py').read_text().replace('__CONTROL_RELEASE__',release).replace('__ROOT_CONTROL_SHA__',base.sha(files['control.py'])).replace('__DRIVER_BASE64__',base64.b64encode((ROOT/'scripts/finance_control/history_driver.py').read_bytes()).decode())
 helper=Path('/home/hermes/workspace/msp-finance-resume-lineage.py');helper.write_text(resume);compile(resume,str(helper),'exec')
 (OUT/'lineage-upgrade.py').write_text(upgrade);(OUT/'resume-lineage.py').write_text(resume)
 command='msp_fix_stage=$(mktemp -d /var/lib/msp-finance-diag.XXXXXXXX) && install -o root -g root -m 600 '+str(up)+' "$msp_fix_stage/upgrade.py" && printf \'%s  %s\\n\' '+base.sha(upgrade.encode())+' "$msp_fix_stage/upgrade.py" | sha256sum -c - && /usr/bin/python3 -I -B "$msp_fix_stage/upgrade.py" && printf \'%s  %s\\n\' '+base.sha(resume.encode())+' '+str(helper)+' | sha256sum -c - && /usr/sbin/runuser -u hermes -- /usr/bin/env XDG_RUNTIME_DIR=/run/user/1001 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1001/bus /usr/bin/python3 -I -B '+str(helper)
 assert len(command.splitlines())==1;subprocess.run(['/bin/bash','-n','-c',command],check=True);(OUT/'ROOT_LINEAGE_REPAIR_AND_RESUME.txt').write_text(command+'\n')
 manifest={'old':old,'release':release,'hashes':package['hashes'],'payload_sha256':package['payload_sha256'],'upgrade_sha256':base.sha(upgrade.encode()),'resume_sha256':base.sha(resume.encode()),'production_install':'PENDING','root_execution':'NOT_EXECUTED'}
 (OUT/'LINEAGE_MANIFEST.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n');print(json.dumps({k:manifest[k] for k in ['release','upgrade_sha256','resume_sha256','production_install']}))
if __name__=='__main__':main()
