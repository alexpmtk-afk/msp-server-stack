"""P01 passive metadata: no sockets, provider calls, credentials or job payloads."""
import datetime,hashlib,json,os,shutil,socket,stat,subprocess,sys
from pathlib import Path

def no_network(event,args):
    if event in ('socket.connect','socket.getaddrinfo'):
        raise RuntimeError('network forbidden for local metadata collector')
sys.addaudithook(no_network)

def metadata(path):
    p=Path(path)
    try:
        s=p.lstat()
        return {'status':'PRESENT','uid':s.st_uid,'gid':s.st_gid,'mode':f'{stat.S_IMODE(s.st_mode):04o}',
                'symlink':stat.S_ISLNK(s.st_mode),'readable_by_uid':os.access(p,os.R_OK),
                'writable_by_uid':os.access(p,os.W_OK),'searchable_by_uid':os.access(p,os.X_OK)}
    except PermissionError:return {'status':'PERMISSION_DENIED'}
    except FileNotFoundError:return {'status':'NOT_PRESENT'}

def git_inventory(path,files):
    p=Path(path);r=subprocess.run(['git','-C',str(p),'rev-parse','HEAD'],capture_output=True,text=True)
    out={'head':r.stdout.strip() if r.returncode==0 else None,'files':{}}
    for name in files:
        f=p/name
        out['files'][name]=({'status':'PRESENT','source_sha256':hashlib.sha256(f.read_bytes()).hexdigest()}
                            if f.is_file() else {'status':'NOT_PRESENT'})
    return out

out={'observed_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
     'scope':'local metadata only; network denied; no credential contents, job payloads, environment values or financial rows',
     'uid':os.geteuid(),'expected_vps_label_matches':Path('/etc/hostname').read_text().strip().casefold()=='vm-817589'}
paths=['/opt/mcp/projects/msp-server-stack','/opt/mcp/data','/opt/mcp/data/msp-marketplace-reports',
       '/etc/msp-marketplace-reports','/etc/msp-marketplace-reports/cabinets.json',
       '/opt/marketplaces-mcp-ru','/opt/mcp/marketplaces-mcp-ru','/home/hermes/marketplaces-mcp-ru',
       '/home/hermes/.marketplace-mcp','/home/hermes/.local/share/marketplace-mcp',
       '/etc/redis','/etc/valkey','/run/redis','/var/run/docker.sock','/home/hermes/.ssh']
out['paths']={p:metadata(p) for p in paths}
st=os.statvfs('/opt/mcp/data');out['data_filesystem']={'available_bytes_to_uid':st.f_bavail*st.f_frsize,'readonly':bool(st.f_flag&os.ST_RDONLY)}
# Compare only current shell field PRESENCE; do not claim this is a service config.
out['current_shell_only']={'redis_related_field_count':sum('REDIS' in k or 'VALKEY' in k for k in os.environ),
                          'shared_queue_gate_is_enabled':os.environ.get('MSP_REPORTS_SHARED_QUEUE_VERIFIED')=='YES',
                          'ozon_gate_is_enabled':os.environ.get('MSP_REPORTS_OZON_FINANCE_METHODS_VERIFIED')=='YES'}
ancestors=set();pid=os.getpid()
while pid>1:
    ancestors.add(pid)
    try:pid=int((Path('/proc')/str(pid)/'stat').read_text().split(') ',1)[1].split()[1])
    except (OSError,ValueError,IndexError):break
counts={'redis_valkey_names':0,'container_runtime_names':0,'marketplace_command_candidates':0};errors=0
for p in Path('/proc').iterdir():
    if not p.name.isdigit() or int(p.name) in ancestors:continue
    try:
        comm=(p/'comm').read_text().strip().lower()
        if comm in ('redis-server','valkey-server'):counts['redis_valkey_names']+=1
        if comm in ('dockerd','containerd','podman'):counts['container_runtime_names']+=1
        if not any(x in comm for x in ('python','node','uvicorn','mcp')):continue
        cmd=(p/'cmdline').read_bytes().lower()
        cwd=os.readlink(p/'cwd').lower()
        if any(x in cmd for x in (b'marketplaces-mcp',b'marketplace_mcp',b'archive_queue',b'msp_marketplace_reports')) or 'marketplaces-mcp' in cwd:
            counts['marketplace_command_candidates']+=1
    except (FileNotFoundError,PermissionError,ProcessLookupError):errors+=1
out['bounded_process_inventory']={'counts':counts,'read_errors':errors,'excludes_probe_ancestors':True,
                                  'limitation':'command/cwd heuristic in visible namespace; not proof across hosts or renamed deployments'}
for user in (False,True):
    cmd=['systemctl']+(['--user'] if user else [])+['list-unit-files','--no-legend','--no-pager']
    r=subprocess.run(cmd,capture_output=True,text=True,timeout=15)
    out['user_units' if user else 'system_units']={'returncode':r.returncode,
        'matching_count':sum(any(w in line.lower() for w in ('marketplace','redis','valkey','docker','mcp')) for line in r.stdout.splitlines())}
r=subprocess.run(['ss','-ltnpH'],capture_output=True,text=True,timeout=10)
out['tcp_listener_metadata']={'returncode':r.returncode,'default_redis_port_listening':any(x.split()[3].rsplit(':',1)[-1]=='6379' for x in r.stdout.splitlines() if len(x.split())>=4),
                             'named_redis_valkey_listener_count':sum('redis' in x.lower() or 'valkey' in x.lower() for x in r.stdout.splitlines())}
out['tools_available']={x:bool(shutil.which(x)) for x in ('redis-cli','ssh','docker','podman')}
source_files=['apps/msp_marketplace_reports/quota.py','apps/msp_marketplace_reports/shared_rate_limit.py',
              'apps/msp_marketplace_reports/wb_worker_adapter.py','apps/msp_marketplace_reports/existing_worker_bridge.py']
out['source_inventory']={
 'standard_vps_checkout':git_inventory('/opt/mcp/projects/msp-server-stack',source_files),
 'review_checkout_not_installed':git_inventory('/home/hermes/.hermes/cache/scratch/marketplace-pr99-hermes-fixes',source_files),
 'legacy_source_not_installed':git_inventory('/home/hermes/.hermes/cache/scratch/marketplace-review-20261028/legacy',
  ['core/archive_queue.py','core/archive_tools.py','core/archive_hybrid.py','core/rate_limit.py','core/client.py'])}
out['redis_protocol_commands_executed']=[]
out['reason_no_redis_probe']='no verified existing endpoint/config/executor found; localhost default listener absent; do not guess remote locators'
print(json.dumps(out,ensure_ascii=False,indent=2))
