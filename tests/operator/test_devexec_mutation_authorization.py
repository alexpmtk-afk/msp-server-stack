import hashlib
import json
import os
import socket
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path

from apps.operator_layer.devexec_approval import GrantStore, block_hash
from apps.operator_layer.devexec_mutation import DevexecMutation,check_arguments
from apps.operator_layer.tasks import Journal
from apps.operator_layer.hermes_executor import HermesExecutor


class FakeSocket:
    def __init__(self, path, *, drop_response=False, record=False):
        self.path=path;self.drop_response=drop_response;self.record=record
        self.pending={};self.calls=[];self.closed=False;self.contents={}
        self.sock=socket.socket(socket.AF_UNIX)
        self.sock.bind(path);self.sock.listen(12);self.sock.settimeout(.1)
        self.thread=threading.Thread(target=self.serve,daemon=True);self.thread.start()

    def serve(self):
        while not self.closed:
            try:c,_=self.sock.accept()
            except socket.timeout:continue
            except OSError:break
            with c:
                b=bytearray()
                while not b.endswith(b'\n'):
                    part=c.recv(4096)
                    if not part:break
                    b.extend(part)
                if not b:continue
                q=json.loads(b);op=q['operation'];a=q['arguments'];self.calls.append(op)
                if op=='dev.write_file':
                    path=a['relative_path'];content=a['content'];self.contents[path]=content
                    result={'status':'PASS','before_sha256':None,'after_sha256':hashlib.sha256(content.encode()).hexdigest(),'relative_paths':[path]}
                    if self.record:self.pending[a['request_id']]=result
                    if self.drop_response:continue
                elif op=='dev.get_receipt':
                    result={'state':'COMPLETE','result':self.pending[a['request_id']]} if a['request_id'] in self.pending else {'state':'NOT_FOUND'}
                elif op=='dev.read_file':
                    content=self.contents[a['path']]
                    result={'status':'PASS','sha256':hashlib.sha256(content.encode()).hexdigest(),'content':content}
                else:result={'status':'DENIED','reason':'BLOCKED_CAPABILITY'}
                try:c.sendall(json.dumps({'result':result}).encode()+b'\n')
                except OSError:pass

    def close(self):
        self.closed=True;self.sock.close();self.thread.join(timeout=1)


class ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=str(Path.home()));self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.grants_dir=self.root/'grants';self.grants_dir.mkdir(mode=0o700)
        self.work=self.root/'work';self.work.mkdir(mode=0o700)
        self.task=str(uuid.uuid4());self.path='test_owner_approved.py'
        self.context={'task_id':self.task,'current_block':0,'requires_decomposition':False,'budget':{'soft_deadline':time.time()+300},
                      'block':{'goal':'write approved test','acceptance':['verified'],'allowed_mutations':['dev.write_file'],
                               'expected_output':'test','dependencies':[],'rollback':'none','readback':'receipt'}}
        self.grant={'schema_version':1,'task_id':self.task,'block_index':0,
                    'block_sha256':block_hash(self.context['block']),'workspace_id':'operator',
                    'operation':'dev.write_file','paths':[self.path],'expires_at':time.time()+600}
        self.owner=GrantStore(self.grants_dir,trusted_uid={0,os.getuid(),Path.home().stat().st_uid})
        self.file=self.grants_dir/(self.task+'.json')
        self.save()

    def save(self):
        self.file.write_text(json.dumps(self.grant))
        self.file.chmod(0o600)

    def test_approval_exact_task_block_plan_and_expiry(self):
        self.assertEqual(self.owner.read(self.context)['operation'],'dev.write_file')
        for change in [lambda c:c.update(task_id=str(uuid.uuid4())),
                       lambda c:c.update(current_block=1),
                       lambda c:c['block'].update(goal='new plan'),
                       lambda c:c.update(requires_decomposition=True),
                       lambda c:c['block'].update(allowed_mutations=['dev.git_commit'])]:
            import copy
            context=copy.deepcopy(self.context);change(context)
            with self.assertRaises(ValueError):self.owner.read(context)
        self.grant['expires_at']=time.time()-1;self.save()
        with self.assertRaises(ValueError):self.owner.read(self.context)

    def test_protects_grant_file_symlink_and_permissions(self):
        self.file.chmod(0o666)
        with self.assertRaises(ValueError):self.owner.read(self.context)
        self.file.chmod(0o600);other=self.root/'other';other.write_text(json.dumps(self.grant))
        self.file.unlink();self.file.symlink_to(other)
        with self.assertRaises(ValueError):self.owner.read(self.context)

    def test_soft_deadline_rejects_without_socket(self):
        context=dict(self.context,budget={'soft_deadline':time.time()+2})
        action=DevexecMutation(context,self.work,grants=self.owner,socket_path=str(self.root/'nonexistent.sock'))
        with self.assertRaisesRegex(ValueError,'SOFT_DEADLINE'):action.execute({'relative_path':self.path,'create_only':True,'expected_sha256':None,'content':'ok'})
        self.assertFalse(action.db_path.exists())

    def test_unknown_unapproved_paths_and_wrong_shape(self):
        for a in [dict(relative_path='../outside',create_only=True,expected_sha256=None,content='ok'),
                  dict(relative_path=self.path,create_only=True,expected_sha256=None,content='ghp_test'),
                  dict(relative_path=self.path,create_only=True,expected_sha256='0'*64,content='ok')]:
            with self.assertRaises(ValueError):check_arguments('dev.write_file',a,[self.path])
        for op in ('dev.git_push','dev.run_shell','dev.read_file'):
            with self.assertRaises(ValueError):check_arguments(op,{},[self.path])

    def test_disabled_by_default(self):
        j=Journal(self.work)
        try:self.assertFalse(HermesExecutor(j.root,profile='default').devexec_write_enabled)
        finally:j.close()

    def test_persist_and_independent_readback(self):
        path=str(self.root/'socket');backend=FakeSocket(path,record=True);self.addCleanup(backend.close)
        obj=DevexecMutation(self.context,self.work,grants=self.owner,socket_path=path)
        args={'relative_path':self.path,'create_only':True,'expected_sha256':None,'content':'def test_ok():\n assert True\n'}
        first=obj.execute(args)
        self.assertEqual(first['status'],'PASS')
        self.assertEqual(obj.verified_result(),first)
        second=obj.execute(args)
        self.assertEqual(first,second)
        self.assertEqual(backend.calls.count('dev.write_file'),1)
        with self.assertRaises(ValueError):obj.execute(args|{'content':'different'})
        self.assertEqual(backend.calls.count('dev.write_file'),1)

    def test_lost_response_after_success_recovers_via_receipt(self):
        path=str(self.root/'socket');backend=FakeSocket(path,record=True,drop_response=True);self.addCleanup(backend.close)
        obj=DevexecMutation(self.context,self.work,grants=self.owner,socket_path=path)
        args={'relative_path':self.path,'create_only':True,'expected_sha256':None,'content':'test\n'}
        self.assertEqual(obj.execute(args)['status'],'PASS')
        self.assertEqual(backend.calls.count('dev.write_file'),1)
        self.assertEqual(obj.verified_result()['status'],'PASS')

    def test_expired_grant_can_reconcile_prior_admitted_receipt_without_resending(self):
        path=str(self.root/'socket');backend=FakeSocket(path,record=True);self.addCleanup(backend.close)
        obj=DevexecMutation(self.context,self.work,grants=self.owner,socket_path=path)
        args={'relative_path':self.path,'create_only':True,'expected_sha256':None,'content':'approved before expiry'}
        self.assertEqual(obj.execute(args)['status'],'PASS')
        # Expiration is passage of time, not an owner edit of the signed grant content.
        from unittest.mock import patch
        with patch('apps.operator_layer.devexec_approval.time.time', return_value=self.grant['expires_at']+1):
            with self.assertRaises(ValueError):DevexecMutation(self.context,self.work,grants=self.owner,socket_path=path)
            recovered=DevexecMutation(self.context,self.work,grants=self.owner,socket_path=path,recovery=True)
            self.assertEqual(recovered.verified_result()['status'],'PASS')
            with self.assertRaises(ValueError):recovered.execute(args)
        self.assertEqual(backend.calls.count('dev.write_file'),1)

    def test_expired_grant_without_prior_ledger_cannot_admit_operation(self):
        self.grant['expires_at']=time.time()-1;self.save()
        recovered=DevexecMutation(self.context,self.work,grants=self.owner,socket_path='nonexistent',recovery=True)
        with self.assertRaises(ValueError):recovered.verified_result()
        with self.assertRaises(ValueError):recovered.execute({'relative_path':self.path,'create_only':True,'expected_sha256':None,'content':'not allowed'})

    def test_unknown_not_resent_without_backend_receipt(self):
        path=str(self.root/'socket');backend=FakeSocket(path,record=False,drop_response=True);self.addCleanup(backend.close)
        obj=DevexecMutation(self.context,self.work,grants=self.owner,socket_path=path)
        args={'relative_path':self.path,'create_only':True,'expected_sha256':None,'content':'test\n'}
        self.assertEqual(obj.execute(args)['status'],'RECONCILIATION_REQUIRED')
        self.assertEqual(obj.execute(args)['status'],'RECONCILIATION_REQUIRED')
        self.assertIsNone(obj.verified_result())
        self.assertEqual(backend.calls.count('dev.write_file'),1)

    def test_verifier_completed_after_grant_expiry_requires_prior_ledger_and_receipt(self):
        from unittest.mock import patch
        path=str(self.root/'socket');backend=FakeSocket(path,record=True);self.addCleanup(backend.close)
        args={'relative_path':self.path,'create_only':True,'expected_sha256':None,'content':'verified after expiry'}
        client=DevexecMutation(self.context,self.work,grants=self.owner,socket_path=path)
        self.assertEqual(client.execute(args)['status'],'PASS')
        ex=HermesExecutor(self.work,profile='default',devexec_write_enabled=True)
        actual=DevexecMutation
        with patch('apps.operator_layer.devexec_approval.GrantStore',return_value=self.owner), patch('apps.operator_layer.devexec_mutation.DevexecMutation',side_effect=lambda ctx,root,recovery=False:actual(ctx,root,grants=self.owner,socket_path=path,recovery=recovery)):
            with patch('apps.operator_layer.devexec_approval.time.time',return_value=self.grant['expires_at']+1):
                self.assertFalse(ex.approval_for(self.context))
                self.assertTrue(ex.verify(self.context,{'kind':'complete','evidence':{'verified':True}}))
        self.assertEqual(backend.calls.count('dev.write_file'),1)

    def test_verifier_rejects_expired_grant_without_prior_intent(self):
        from unittest.mock import patch
        ex=HermesExecutor(self.work,profile='default',devexec_write_enabled=True)
        actual=DevexecMutation
        with patch('apps.operator_layer.devexec_approval.GrantStore',return_value=self.owner), patch('apps.operator_layer.devexec_mutation.DevexecMutation',side_effect=lambda ctx,root,recovery=False:actual(ctx,root,grants=self.owner,socket_path='nonexistent',recovery=recovery)):
            with patch('apps.operator_layer.devexec_approval.time.time',return_value=self.grant['expires_at']+1):
                self.assertFalse(ex.verify(self.context,{'kind':'complete','evidence':{'verified':True}}))
                self.assertFalse(ex.verify(self.context,{'kind':'checkpoint'}))

    def test_verifier_allows_pending_checkpoint_with_live_grant_no_intent(self):
        from unittest.mock import patch
        ex=HermesExecutor(self.work,profile='default',devexec_write_enabled=True)
        actual=DevexecMutation
        with patch('apps.operator_layer.devexec_approval.GrantStore',return_value=self.owner), patch('apps.operator_layer.devexec_mutation.DevexecMutation',side_effect=lambda ctx,root,recovery=False:actual(ctx,root,grants=self.owner,socket_path='nonexistent',recovery=recovery)):
            self.assertTrue(ex.approval_for(self.context))
            self.assertTrue(ex.verify(self.context,{'kind':'checkpoint'}))
            self.assertFalse(ex.verify(self.context,{'kind':'complete','evidence':{'verified':True}}))



if __name__=='__main__':unittest.main()
