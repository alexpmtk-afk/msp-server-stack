"""Build a self-contained, checksummed ROOT recovery script; never executes it."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import tempfile
import venv

ROOT=Path(__file__).resolve().parents[2]
RELEASE=Path('/opt/mcp/projects/msp-marketplace-reports-releases/c1fee070e9efa0c925a78f266fdf03cb12a173cf')

def main():
    generated={}
    with tempfile.TemporaryDirectory() as d:
        env=Path(d)/'.venv';venv.EnvBuilder(with_pip=False,symlinks=True).create(env)
        for p in env.rglob('*'):
            if p.is_file() and not p.is_symlink():
                data=p.read_bytes().replace(str(env).encode(),str(RELEASE/'.venv').encode())
                generated[str(p.relative_to(env))]=hashlib.sha256(data).hexdigest()
    raw=subprocess.check_output(['git','show','04a1aae831967380179d7a4aa061e20e655472cb:scripts/wb_bootstrap/install.py'],cwd=ROOT)
    oldhash=hashlib.sha256(raw).hexdigest()
    source=(Path(__file__).parent/'recover.py').read_text()
    source=source.replace('GENERATED = {}  # BUILD_EMBED_GENERATED','GENERATED = '+repr(generated))
    source=source.replace("OLD_INSTALL_SHA = ''  # BUILD_EMBED_INSTALL_SHA",'OLD_INSTALL_SHA = '+repr(oldhash))
    out=ROOT/'docs/marketplace-reports/recovery-20261103'
    out.mkdir(exist_ok=True)
    dst=out/'repair.py';dst.write_text(source)
    local=Path('/home/hermes/workspace/msp-wb-repair.py');local.write_text(source)
    digest=hashlib.sha256(dst.read_bytes()).hexdigest()
    stage='$wb_repair_stage'
    command='wb_repair_stage=$(mktemp -d /var/lib/msp-wb-repair.XXXXXXXX) && install -o root -g root -m 600 '+str(local)+' "$wb_repair_stage/repair.py" && printf \'%s  %s\\n\' '+digest+' "$wb_repair_stage/repair.py" | sha256sum -c - && /usr/bin/python3 -I -B "$wb_repair_stage/repair.py"'
    (out/'ROOT_ONE_LINE.txt').write_text(command+'\n')
    summary={'repair_sha256':digest,'original_install_sha256':oldhash,'original_bundle_sha256':'eb2ac87f8ad6221c230fdf28b2cb384645e1018f1845b4d7e60f7a943c67767b',
             'original_manifest_sha256':'a6d556ae5aa28b8d07893cc9808dbc599d26641b1eeea586c69cc0bd80c2b059','generated_runtime_files':generated}
    (out/'REPAIR_MANIFEST.json').write_text(json.dumps(summary,indent=2)+'\n')
    assert len(command.splitlines())==1
    subprocess.run(['/bin/bash','-n','-c',command],check=True)
    # These are public runtime cfg/activation files, never credentials.
    checked=0
    for name,expected in generated.items():
        target=RELEASE/'.venv'/name
        if target.exists():
            assert hashlib.sha256(target.read_bytes()).hexdigest()==expected,name
            checked+=1
    print(json.dumps({'repair_sha256':digest,'live_runtime_generated_hashes_matched':checked,'shell_one_line_syntax':'PASS'}))

if __name__=='__main__':main()
