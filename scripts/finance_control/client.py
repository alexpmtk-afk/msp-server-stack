"""Unprivileged bounded wake; no secrets, no direct provider calls or sudo."""
import argparse,fcntl,json,os,subprocess,uuid
from pathlib import Path
STATE=Path('/var/lib/msp-finance-control')
def main():
 if os.geteuid()!=1001:raise ValueError('hermes required')
 p=argparse.ArgumentParser();p.add_argument('--cabinet',choices=['wb_laser_master','wb_novokshenov','wb_dmitrieva'],required=True);p.add_argument('--jobs',type=int,choices=[1,2],default=1);p.add_argument('--expect-report',type=int);a=p.parse_args()
 if a.expect_report is not None and (a.expect_report<=0 or a.jobs!=1):p.error('expected report requires positive ID and one job')
 fd=os.open(STATE/'inbox/client.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
 try:
  fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);nonce=uuid.uuid4().hex
  req={'nonce':nonce,'cabinet':a.cabinet,'max_jobs':a.jobs}
  if a.expect_report is not None:req['expected_report_id']=a.expect_report
  target=STATE/'inbox/request.json';tmp=target.with_name(nonce+'.tmp')
  out=os.open(tmp,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600);os.write(out,(json.dumps(req)+'\n').encode());os.fsync(out);os.close(out);os.replace(tmp,target)
  directory=os.open(target.parent,os.O_RDONLY|os.O_DIRECTORY);os.fsync(directory);os.close(directory)
  result=subprocess.run(['/usr/bin/systemctl','--no-ask-password','start','msp-finance-control.service'],env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8'})
  if result.returncode:
   failure=STATE/'results'/(nonce+'-failure.json')
   if failure.exists():print(failure.read_text())
   raise RuntimeError('fixed control start failed; no retry')
  receipt=STATE/'results'/(nonce+'.json')
  print(receipt.read_text() if receipt.exists() else json.dumps({'status':'UNCERTAIN','request_nonce':nonce,'no_auto_retry':True}))
 finally:os.close(fd)
if __name__=='__main__':main()
