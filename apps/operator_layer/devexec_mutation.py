"""NOT DEPLOYED. Opt-in, owner-approved, one operation per durable block.

Root-owned, exact-block approval controls admission. SQLite records UNKNOWN before
network I/O; an unknown call is never resubmitted, only reconciled via receipt.
"""
import hashlib
import contextlib
import json
import os
import re
import socket
import sqlite3
import time
from pathlib import Path

from .devexec_approval import GrantStore, canonical, check_context, relative

SOCKET = '/run/msp-devexec.sock'
TOOLSET = 'operator-devexec-write'
SCHEMAS = {
    'dev.write_file': {'relative_path': {'type':'string'}, 'create_only': {'type':'boolean'}, 'expected_sha256': {'type':['string','null']}, 'content': {'type':'string'}},
    'dev.apply_patch': {'relative_path': {'type':'string'}, 'create_only': {'type':'boolean'}, 'expected_sha256': {'type':'string'}, 'edits': {'type':'array'}},
    'dev.run_tests': {'test_paths': {'type':'array','items': {'type':'string'}}, 'timeout_seconds': {'type':'integer'}},
    'dev.git_add': {'paths': {'type':'array','items': {'type':'string'}}, 'expected_sha256': {'type':'object'}},
    'dev.git_commit': {'message': {'type':'string'}},
}
HEX64 = re.compile(r'^[0-9a-f]{64}$')


def check_arguments(operation, args, paths):
    if operation not in SCHEMAS or not isinstance(args, dict) or set(args) != set(SCHEMAS[operation]):
        raise ValueError('INVALID_CONTRACT')
    allowed = set(paths)
    if operation in ('dev.write_file','dev.apply_patch'):
        path = relative(args['relative_path'])
        if path not in allowed or type(args['create_only']) is not bool:
            raise ValueError('PATH_NOT_APPROVED')
        if operation == 'dev.write_file':
            if not isinstance(args['content'], str) or len(args['content'].encode('utf-8')) > 65536 or any(x in args['content'] for x in ('-----BEGIN ', 'ghp_', 'github_pat_')):
                raise ValueError('SIZE_LIMIT')
            if args['create_only']:
                if args['expected_sha256'] is not None:raise ValueError('INVALID_CONTRACT')
            elif not isinstance(args['expected_sha256'], str) or not HEX64.fullmatch(args['expected_sha256']):
                raise ValueError('INVALID_CONTRACT')
        else:
            if args['create_only'] or not isinstance(args['expected_sha256'], str) or not HEX64.fullmatch(args['expected_sha256']):
                raise ValueError('INVALID_CONTRACT')
            edits = args['edits']
            if not isinstance(edits,list) or not 1 <= len(edits) <= 8 or len(canonical(edits)) > 65536:
                raise ValueError('INVALID_CONTRACT')
            if any(not isinstance(e,dict) or set(e) != {'old','new'} or not all(isinstance(e[v],str) for v in ('old','new')) or not e['old'] for e in edits):
                raise ValueError('INVALID_CONTRACT')
    elif operation in ('dev.run_tests','dev.git_add'):
        selected = args['test_paths'] if operation == 'dev.run_tests' else args['paths']
        if not isinstance(selected,list) or not 1 <= len(selected) <= 32 or not all(isinstance(x,str) for x in selected) or len(set(selected)) != len(selected):
            raise ValueError('INVALID_CONTRACT')
        for path in selected:
            if relative(path) not in allowed:raise ValueError('PATH_NOT_APPROVED')
        if operation == 'dev.run_tests':
            if not all(p.endswith('.py') for p in selected) or type(args['timeout_seconds']) is not int or not 1 <= args['timeout_seconds'] <= 60:
                raise ValueError('INVALID_CONTRACT')
        else:
            hashes = args['expected_sha256']
            if not isinstance(hashes,dict) or set(hashes) != set(selected) or any(not isinstance(v,str) or not HEX64.fullmatch(v) for v in hashes.values()):
                raise ValueError('INVALID_CONTRACT')
    elif operation == 'dev.git_commit':
        if not isinstance(args['message'],str) or not 1 <= len(args['message'].encode()) <= 150 or '\x00' in args['message']:
            raise ValueError('INVALID_CONTRACT')


class DevexecMutation:
    def __init__(self, context, root, *, grants=None, socket_path=SOCKET, recovery=False):
        self.context = context
        self.grants = grants if grants is not None else GrantStore()
        self.grant = self.grants.read(context, allow_expired=recovery)
        self.task, self.index, self.op = check_context(context)
        self.root = Path(root)
        self.socket_path = socket_path
        self.request_id = hashlib.sha256(canonical([self.task,self.index,self.op,self.grant['block_sha256']])).hexdigest()
        self.db_path = self.root/'devexec_mutation_ledger.sqlite'

    def _db(self):
        st = self.root.lstat()
        if self.root.is_symlink() or st.st_uid != os.getuid() or st.st_mode & 0o077:
            raise ValueError('UNTRUSTED_LEDGER_DIR')
        fd = os.open(self.db_path, os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW, 0o600)
        try:
            meta = os.fstat(fd)
            if meta.st_uid != os.getuid() or meta.st_mode & 0o077 or meta.st_nlink != 1:
                raise ValueError('UNTRUSTED_LEDGER')
        finally:
            os.close(fd)
        conn = sqlite3.connect(self.db_path, timeout=3)
        conn.execute('PRAGMA synchronous=FULL')
        conn.execute('CREATE TABLE IF NOT EXISTS calls (request_id TEXT PRIMARY KEY, task_id TEXT, block_index INTEGER, operation TEXT, digest TEXT, state TEXT, result TEXT, admitted_at REAL, grant_sha256 TEXT)')
        conn.commit()
        return conn

    def _authorize_recovery(self):
        # The expired grant may only support independent receipt readback, never a new write.
        grant = self.grants.read(self.context, allow_expired=True)
        with contextlib.closing(self._db()) as db:
            row = db.execute('SELECT task_id,block_index,operation,admitted_at,grant_sha256 FROM calls WHERE request_id=?',(self.request_id,)).fetchone()
        if (not row or row[:3] != (self.task,self.index,self.op) or type(row[3]) not in (int,float)
                or row[3] > grant['expires_at'] or row[3] <= 0
                or row[4] != hashlib.sha256(canonical(grant)).hexdigest()):
            raise ValueError('UNAUTHORIZED_RECOVERY')
        self.grant = grant

    def _wire(self, operation, arguments, timeout=5):
        contract = {'task_id':self.task, 'step_id':f'block-{self.index}', 'workspace_id':'operator',
                    'goal':'owner-approved isolated development block', 'allowed_operations':[operation],
                    'expected_outputs':self.grant['paths'], 'deadline':time.time()+120}
        q = {'contract':contract, 'operation':operation, 'arguments':arguments}
        body = canonical(q) + b'\n'
        if len(body) > 110000:raise ValueError('SIZE_LIMIT')
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(self.socket_path)
            s.sendall(body)
            reply = bytearray()
            while not reply.endswith(b'\n'):
                chunk = s.recv(min(8192, 131073-len(reply)))
                if not chunk or len(reply)+len(chunk)>131072:raise ValueError('INVALID_RESPONSE')
                reply.extend(chunk)
        response = json.loads(reply)
        if not isinstance(response,dict) or set(response) != {'result'} or not isinstance(response['result'],dict):
            raise ValueError('INVALID_RESPONSE')
        return response['result']

    def _receipt(self):
        return self._wire('dev.get_receipt', {'task_id':self.task,'step_id':f'block-{self.index}', 'request_id':self.request_id})

    def reconcile(self):
        with contextlib.closing(self._db()) as db, db:
            row = db.execute('SELECT state,result FROM calls WHERE request_id=?',(self.request_id,)).fetchone()
            if not row:return None
            self._authorize_recovery()
            if row[0]=='COMPLETE':return json.loads(row[1])
            try:receipt=self._receipt()
            except (TimeoutError, OSError, ValueError, KeyError, json.JSONDecodeError):return None
            if receipt.get('state')!='COMPLETE' or not isinstance(receipt.get('result'),dict):return None
            result=receipt['result']
            db.execute('UPDATE calls SET state=?,result=? WHERE request_id=? AND state=?',('COMPLETE',json.dumps(result),self.request_id,'UNKNOWN'))
            return result

    def execute(self, args):
        soft=self.context.get('budget',{}).get('soft_deadline')
        if type(soft) not in (int,float) or time.time()+30 >= soft:
            raise ValueError('SOFT_DEADLINE')
        # Never permit a different version of the plan or expired grant between registration and call.
        self.grant=self.grants.read(self.context)
        check_arguments(self.op,args,self.grant['paths'])
        if self.op=='dev.git_commit':
            status=self._wire('dev.git_status',{})
            tracked=status.get('tracked_files')
            if status.get('status')!='PASS' or not isinstance(tracked,dict) or not tracked or set(tracked)!=set(self.grant['paths']) or any(v!='CLEAN' for v in tracked.values()):
                raise ValueError('GIT_INDEX_NOT_APPROVED')
        # Digest is over the full, bounded arguments; a replay with different inputs is rejected.
        digest=hashlib.sha256(canonical(args)).hexdigest()
        with contextlib.closing(self._db()) as db, db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT digest,state,result FROM calls WHERE request_id=?',(self.request_id,)).fetchone()
            if row:
                if row[0]!=digest:raise ValueError('REQUEST_CONFLICT')
                if row[1]=='COMPLETE':return json.loads(row[2])
                return {'status':'RECONCILIATION_REQUIRED','request_id':self.request_id}
            db.execute('INSERT INTO calls VALUES (?,?,?,?,?,?,NULL,?,?)',(self.request_id,self.task,self.index,self.op,digest,'UNKNOWN',time.time(),hashlib.sha256(canonical(self.grant)).hexdigest()))
        wire_args = dict(args,task_id=self.task,step_id=f'block-{self.index}',workspace_id='operator',request_id=self.request_id)
        try:self._wire(self.op,wire_args,timeout=8)
        except (OSError,ValueError,TimeoutError,KeyError):pass  # Do NOT blindly send the operation again.
        result=self.reconcile()
        return result if result is not None else {'status':'RECONCILIATION_REQUIRED','request_id':self.request_id}

    def verified_result(self):
        # Independently query protected backend rather than relying on a model statement.
        self._authorize_recovery()
        r=self.reconcile()
        if not isinstance(r,dict) or r.get('status')!='PASS':return None
        try:receipt=self._receipt()
        except (TimeoutError,OSError,ValueError,KeyError):return None
        if receipt.get('state')!='COMPLETE' or receipt.get('result')!=r:return None
        if self.op in ('dev.write_file','dev.apply_patch'):
            path=r.get('relative_paths')
            if path!=[self.grant['paths'][0]] or not isinstance(r.get('after_sha256'),str):return None
            try:read=self._wire('dev.read_file',{'path':path[0]})
            except (OSError,ValueError,TimeoutError):return None
            if read.get('status')!='PASS' or read.get('sha256')!=r['after_sha256']:return None
        if self.op=='dev.git_add':
            try:status=self._wire('dev.git_status',{})
            except (OSError,ValueError,TimeoutError):return None
            tracked=status.get('tracked_files')
            if status.get('status')!='PASS' or not isinstance(tracked,dict) or any(tracked.get(path)!='CLEAN' for path in self.grant['paths']):return None
        if self.op=='dev.git_commit' and (not isinstance(r.get('commit_sha'),str) or not re.fullmatch(r'[0-9a-f]{40}',r['commit_sha'])):return None
        return r

    def register(self):
        from tools.registry import registry
        properties=SCHEMAS[self.op]
        schema={'name':'devexec_'+self.op.split('.')[1], 'description':'One root-approved isolated Development Executor operation; durable receipt required.',
                'parameters':{'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}}
        def handler(args,**kwargs):return json.dumps(self.execute(args),ensure_ascii=False)
        registry.register(name=schema['name'],toolset=TOOLSET,schema=schema,handler=handler)
