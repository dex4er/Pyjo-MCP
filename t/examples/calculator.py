import Pyjo.MCP.Test

from Pyjo.File import curfile
from Pyjo.Test import *

import json
import subprocess
import sys


# The application of examples/calculator.py, which the test loads without starting a server
EXAMPLE = curfile().dirname().dirname().sibling('examples', 'calculator.py')
t = Pyjo.MCP.Test.new(EXAMPLE)
t.app.log.level = 'fatal'

META = {'io.modelcontextprotocol/protocolVersion': '2026-07-28', 'io.modelcontextprotocol/clientCapabilities': {}}


with subtest('Discovery'):
    t.discover_ok().status_is(200)
    t.result_is('/instructions', 'Arithmetic of two numbers, without mistakes.')
    t.result_is('/_meta/io.modelcontextprotocol~1serverInfo', {'name': 'calculator', 'version': '1.0.0'})
    t.result_is('/capabilities', {'tools': {}})

with subtest('Tools'):
    t.list_tools_ok().status_is(200)
    names = [tool['name'] for tool in t.response['result']['tools']]
    is_deeply_ok(names, ['add', 'subtract', 'multiply', 'divide'], 'operations')
    t.result_is('/tools/3/description', 'Divide the first number by the second one.')
    t.result_is('/tools/3/annotations', {'readOnlyHint': True})
    t.result_is('/tools/3/outputSchema', {'type': 'number'})

with subtest('Calls'):
    t.call_ok('add', a=7, b=2).status_is(200).structured_content_is(9)
    t.call_ok('subtract', a=7, b=2).status_is(200).structured_content_is(5)
    t.call_ok('multiply', a=1.5, b=2).status_is(200).structured_content_is(3.0)
    t.call_ok('divide', a=7, b=2).status_is(200).structured_content_is(3.5)
    t.call_ok('divide', a=1, b=0).status_is(200).is_error_is(True)
    t.text_content_is('Division by zero')
    t.call_ok('add', a='x', b=0).status_is(200).is_error_is(True)
    t.text_content_is('Invalid arguments:\n/a: Expected number - got string.')

with subtest('Hosts and origins'):
    t.list_tools_ok(headers={'Host': 'evil.com'}).status_is(421)
    t.list_tools_ok(headers={'Origin': 'http://evil.com'}).status_is(403)

with subtest('Standard input and output'):
    # The command stdio in a process of its own, which ends at the end of its input, once the responses are written
    params = {'name': 'divide', 'arguments': {'a': 7, 'b': 2}, '_meta': META}
    lines = [
        json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': params}),
        json.dumps({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list', 'params': {'_meta': META}}),
        'not json',
    ]
    process = subprocess.run(
        [sys.executable, EXAMPLE.to_str(), 'stdio'], input='\n'.join(lines) + '\n', capture_output=True, text=True
    )
    is_ok(process.returncode, 0, 'end of the input')
    responses = {message['id']: message for message in map(json.loads, process.stdout.splitlines())}
    is_deeply_ok(sorted(responses, key=str), [1, 2, None], 'nothing but a response on each line of the standard output')
    is_ok(responses[1]['result']['structuredContent'], 3.5, 'tools/call')
    is_ok(len(responses[2]['result']['tools']), 4, 'tools/list')
    is_ok(responses[None]['error']['code'], -32700, 'parse error')

done_testing()
