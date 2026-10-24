import Pyjo.Test.Pyjo

from Pyjo.File import curfile
from Pyjo.Test import *


# The application of examples/calculator.py, which the test loads without starting a server
t = Pyjo.Test.Pyjo.new(curfile().dirname().dirname().sibling('examples', 'calculator.py'))
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

done_testing()
