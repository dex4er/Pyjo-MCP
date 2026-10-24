import Pyjo.Test.Pyjo

from Pyjo.File import curfile
from Pyjo.Test import *


t = Pyjo.Test.Pyjo.new(curfile().sibling('hello.py'))

META = {'io.modelcontextprotocol/protocolVersion': '2026-07-28', 'io.modelcontextprotocol/clientCapabilities': {}}


def call(tool, /, **arguments):
    # A request of tools/call, with the headers and the _meta that every request of MCP has; the name of the tool is
    # positional only, as a tool may have an argument name
    headers = {'MCP-Protocol-Version': '2026-07-28', 'Mcp-Method': 'tools/call', 'Mcp-Name': tool}
    params = {'name': tool, 'arguments': arguments, '_meta': META}
    return t.post_ok('/mcp', headers, json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': params})


with subtest('Greeting'):
    call('greet', name='Pyjo').status_is(200)
    t.json_is('/result/content/0/text', 'Hello, Pyjo!').json_is('/result/isError', False)

with subtest('Without a name'):
    call('greet').status_is(200).json_is('/result/isError', True)
    t.json_like('/result/content/0/text', r'/name: Missing property')

done_testing()
