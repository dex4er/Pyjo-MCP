import Pyjo.Test.Pyjo

from Pyjo.File import curfile
from Pyjo.Test import *

import json
import subprocess
import sys


# The application of examples/calculator.py, which the test loads without starting a server
EXAMPLE = curfile().dirname().dirname().sibling('examples', 'calculator.py')
t = Pyjo.Test.Pyjo.new(EXAMPLE)
t.app.log.level = 'fatal'

META = {'io.modelcontextprotocol/protocolVersion': '2026-07-28', 'io.modelcontextprotocol/clientCapabilities': {}}


def call(name, **arguments):
    headers = {'MCP-Protocol-Version': '2026-07-28', 'Mcp-Method': 'tools/call', 'Mcp-Name': name}
    params = {'name': name, 'arguments': arguments, '_meta': META}
    return t.post_ok('/mcp', headers, json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': params})


with subtest('Discovery'):
    headers = {'MCP-Protocol-Version': '2026-07-28', 'Mcp-Method': 'server/discover'}
    message = {'jsonrpc': '2.0', 'id': 1, 'method': 'server/discover', 'params': {'_meta': META}}
    t.post_ok('/mcp', headers, json=message).status_is(200)
    t.json_is('/result/instructions', 'Arithmetic of two numbers, without mistakes.')
    t.json_is('/result/_meta/io.modelcontextprotocol~1serverInfo', {'name': 'calculator', 'version': '1.0.0'})
    t.json_is('/result/capabilities', {'tools': {}})

with subtest('Tools'):
    headers = {'MCP-Protocol-Version': '2026-07-28', 'Mcp-Method': 'tools/list'}
    message = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list', 'params': {'_meta': META}}
    t.post_ok('/mcp', headers, json=message).status_is(200)
    names = [tool['name'] for tool in t.tx.res.json('/result/tools')]
    is_deeply_ok(names, ['add', 'subtract', 'multiply', 'divide'], 'operations')
    t.json_is('/result/tools/3/description', 'Divide the first number by the second one.')
    t.json_is('/result/tools/3/annotations', {'readOnlyHint': True})
    t.json_is('/result/tools/3/outputSchema', {'type': 'number'})

with subtest('Calls'):
    call('add', a=7, b=2).status_is(200).json_is('/result/structuredContent', 9)
    call('subtract', a=7, b=2).status_is(200).json_is('/result/structuredContent', 5)
    call('multiply', a=1.5, b=2).status_is(200).json_is('/result/structuredContent', 3.0)
    call('divide', a=7, b=2).status_is(200).json_is('/result/structuredContent', 3.5)
    call('divide', a=1, b=0).status_is(200).json_is('/result/isError', True)
    t.json_is('/result/content/0/text', 'Division by zero')
    call('add', a='x', b=0).status_is(200).json_is('/result/isError', True)
    t.json_is('/result/content/0/text', 'Invalid arguments:\n/a: Expected number - got string.')

with subtest('Hosts and origins'):
    headers = {'MCP-Protocol-Version': '2026-07-28', 'Mcp-Method': 'tools/list', 'Host': 'evil.com'}
    t.post_ok('/mcp', headers, json={}).status_is(421)
    headers = {'MCP-Protocol-Version': '2026-07-28', 'Mcp-Method': 'tools/list', 'Origin': 'http://evil.com'}
    t.post_ok('/mcp', headers, json={}).status_is(403)

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
