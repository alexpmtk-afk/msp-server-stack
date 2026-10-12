"""Opt-in read-only Hermes -> root-fenced msp-devexec Unix-socket adapter.

No write, patch, test execution, Git mutations, command, HTTP or shell tools.
This is a fail-closed integration probe, NOT the mutable development adapter.
"""

import json
import re
import socket
import time
from pathlib import PurePosixPath

SOCKET = '/run/msp-devexec.sock'
TOOLSET = 'operator-devexec-ro'
MAX_RESPONSE = 1_048_576
READ_ONLY = frozenset({'dev.list_files', 'dev.read_file', 'dev.git_status', 'dev.git_diff'})
BLOCKED_NAMES = frozenset({'.git', '.ssh', '.env', '.hermes', '.codex', 'secrets', 'credentials'})


def relative_path(value):
    if not isinstance(value, str) or not value or len(value) > 512 or '\\' in value or '\x00' in value:
        raise ValueError('INVALID_PATH')
    p = PurePosixPath(value)
    if p.is_absolute() or any(part in ('', '.', '..') or part in BLOCKED_NAMES or part.endswith(('.pem', '.key')) for part in value.split('/')):
        raise ValueError('INVALID_PATH')
    return value


def validate_args(operation, arguments):
    if operation not in READ_ONLY or not isinstance(arguments, dict):
        raise ValueError('BLOCKED_CAPABILITY')
    if operation in ('dev.list_files', 'dev.git_status'):
        if arguments:
            raise ValueError('INVALID_CONTRACT')
    elif operation == 'dev.read_file':
        if set(arguments) != {'path'}:
            raise ValueError('INVALID_CONTRACT')
        relative_path(arguments['path'])
    elif operation == 'dev.git_diff':
        if set(arguments) != {'paths'} or not isinstance(arguments['paths'], list) or not 1 <= len(arguments['paths']) <= 32:
            raise ValueError('INVALID_CONTRACT')
        for path in arguments['paths']:
            relative_path(path)
        if len(set(arguments['paths'])) != len(arguments['paths']):
            raise ValueError('INVALID_CONTRACT')


class DevexecReadonly:
    def __init__(self, context, *, socket_path=SOCKET):
        block = context.get('block')
        if not isinstance(block, dict) or block.get('allowed_mutations') != []:
            raise ValueError('MUTATION_PLAN_NOT_READONLY')
        if not isinstance(context.get('task_id'), str) or not re.fullmatch(r'[a-f0-9-]{36}', context['task_id']):
            raise ValueError('INVALID_TASK')
        step = context.get('current_block')
        if type(step) is not int or step < 0:
            raise ValueError('INVALID_STEP')
        self.task_id = context['task_id']
        self.step_id = f'block-{step}'
        self.socket_path = socket_path

    def call(self, operation, arguments):
        validate_args(operation, arguments)
        contract = {
            'task_id': self.task_id,
            'step_id': self.step_id,
            'workspace_id': 'operator',
            'goal': 'read-only examination of isolated development workspace',
            'allowed_operations': [operation],
            'expected_outputs': [],
            'deadline': time.time() + 30,
        }
        request = {'contract': contract, 'operation': operation, 'arguments': arguments}
        wire = (json.dumps(request, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')
        if len(wire) > 32_768:
            raise ValueError('SIZE_LIMIT')
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
            stream.settimeout(5)
            stream.connect(self.socket_path)
            stream.sendall(wire)
            body = bytearray()
            while not body.endswith(b'\n'):
                chunk = stream.recv(min(8192, MAX_RESPONSE + 1 - len(body)))
                if not chunk or len(body) + len(chunk) > MAX_RESPONSE:
                    raise ValueError('INVALID_RESPONSE')
                body.extend(chunk)
        response = json.loads(body)
        if not isinstance(response, dict) or set(response) != {'result'} or not isinstance(response['result'], dict):
            raise ValueError('INVALID_RESPONSE')
        return response['result']

    def register(self):
        from tools.registry import registry
        definitions = [
            ('devexec_list_files', 'dev.list_files', {}, 'List allowed files in the isolated development workspace.'),
            ('devexec_read_file', 'dev.read_file', {'path': {'type': 'string'}}, 'Read an allowed file in the isolated development workspace.'),
            ('devexec_git_status', 'dev.git_status', {}, 'Read local isolated Git object store status.'),
            ('devexec_git_diff', 'dev.git_diff', {'paths': {'type': 'array', 'items': {'type': 'string'}, 'minItems': 1, 'maxItems': 32}}, 'Read local isolated Git diffs for allowed relative paths.'),
        ]
        for name, operation, properties, description in definitions:
            required = list(properties)
            schema = {'name': name, 'description': description,
                      'parameters': {'type': 'object', 'properties': properties, 'required': required, 'additionalProperties': False}}

            def handler(args, *, _operation=operation, **kwargs):
                # Ignore untrusted model-supplied task IDs, workspace IDs, deadlines, and socket paths.
                return json.dumps(self.call(_operation, args), ensure_ascii=False)

            registry.register(name=name, toolset=TOOLSET, schema=schema, handler=handler)
