import unittest,json,time,sys,tempfile
from pathlib import Path
from unittest.mock import patch
P=Path(__file__).parent/'payload';sys.path.insert(0,str(P))
import controller as c
import start_root as s
class ControllerTests(unittest.TestCase):
 def test_nonroot_install_refuses_before_reads(self):
  with patch.object(s.os,'geteuid',return_value=1001),patch.object(s.r,'trust') as trust:
   with self.assertRaises(PermissionError):s.main()
   trust.assert_not_called()
 def test_no_stop_during_live_cleanup(self):
  with patch.object(c,'trusted_context',return_value={'cabinet':'ozon_novokshenov'}),patch.object(c,'state',return_value={'ActiveState':'activating'}),patch.object(c.r,'run') as run:
   with self.assertRaises(c.OwnershipUncertain):c.close_inactive()
   run.assert_not_called()
 def test_cooperative_root_stop_during_child_verifier_is_pause_not_hold(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as tmp:
   base=Path(tmp);p=base/'progress.json';p.write_text('{"completed_cabinets":[{"cabinet":"ozon_dmitrieva"}],"current_cabinet":"ozon_novokshenov"}')
   with patch.object(c,'STOP',True),patch.object(c,'PUBLIC',p),patch.object(c,'LEDGER',base),patch.object(c,'progress') as progress:
    self.assertEqual(c.fail_recovery(RuntimeError('child terminated')),75)
    self.assertEqual(progress.call_args.args[0],'PAUSED_CONTROLLER_LINK')
   self.assertFalse((base/'HOLD').exists())
 def test_manager_disconnect_is_recoverable_pause(self):
  with patch.object(c.r,'run',side_effect=RuntimeError('fixture')):
   with self.assertRaises(c.ManagerUnavailable):c.state()
 def test_persistent_service_recovers_but_holds_unknowns(self):
  text=s.service_text().decode()
  self.assertIn('Restart=on-failure',text);self.assertIn('RestartPreventExitStatus=2',text)
  self.assertIn('/DONE',text);self.assertIn('/HOLD',text);self.assertNotIn('ExecStopPost',text)
 def test_controller_restart_skips_completed_cabinet_and_reattaches(self):
  with tempfile.TemporaryDirectory(dir='/home/hermes/.hermes/cache/scratch') as tmp:
   base=Path(tmp);ledger=base/'ledger';ledger.mkdir();root=base/'root';root.mkdir();lock=base/'lock';lock.write_bytes(b'')
   claims={x:{'nonce':str(i)*32,'deadline':time.time()+600} for i,x in enumerate(c.CABINETS,1)}
   (ledger/'claims.json').write_text(json.dumps(claims));(root/'setup-ownership.json').write_text('{"rule_sha256":"fixture"}')
   for x in c.CABINETS:
    d=base/x/c.PERIOD;d.mkdir(parents=True);(d/'worker-result.json').write_text(json.dumps({'nonce':claims[x]['nonce']}))
   active=[{'cabinet':'ozon_novokshenov','phase':'working'}];verified=[];calls=[]
   def close():active[0]=None;calls.append('close')
   def check(x,result):verified.append(x);return {'cabinet':x,'verification':'PASS'}
   def save(p,raw,*args):p.write_bytes(raw)
   original_open=Path.open
   def open_path(p,*args,**kwargs):
    if str(p)=='/var/lib/msp-finance-control/controller.lock':return original_open(lock,*args,**kwargs)
    return original_open(p,*args,**kwargs)
   with patch.object(c,'RULE',base/'policy.rules'),patch.object(c,'ROOT',root),patch.object(c,'LEDGER',ledger),patch.object(c.os,'geteuid',return_value=0),patch.object(c.r,'trust'),patch.object(c.r,'verify_payload'),patch.object(c,'finish_intent'),patch.object(c,'trusted_context',side_effect=lambda:active[0]),patch.object(c,'history',side_effect=lambda x:base/x),patch.object(c,'verify_cabinet',side_effect=check),patch.object(c,'wait_worker',return_value='receipt') as wait,patch.object(c,'state',return_value={'ActiveState':'inactive'}),patch.object(c,'close_inactive',side_effect=close),patch.object(c,'progress'),patch.object(c.r,'save',side_effect=save),patch.object(Path,'open',open_path):
    self.assertEqual(c.run_campaign(),0)
   self.assertEqual(verified,list(c.CABINETS));self.assertEqual(wait.call_count,1);self.assertEqual(calls,['close'])
if __name__=='__main__':
 def deny(event,args):
  if event in ('socket.connect','socket.bind','socket.getaddrinfo'):raise RuntimeError('NETWORK DENIED')
 sys.addaudithook(deny);unittest.main(verbosity=2)
