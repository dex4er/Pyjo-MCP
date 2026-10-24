import Pyjo.Test.Pyjo
import Pyjoyment

from Pyjo.Test import *

import contextlib
import io


META = {
    'io.modelcontextprotocol/protocolVersion': '2026-07-28',
    'io.modelcontextprotocol/clientInfo': {'name': 'ExampleClient', 'version': '1.0.0'},
    'io.modelcontextprotocol/clientCapabilities': {},
}


def request(method, **params):
    return {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': {**params, '_meta': META}}


def dispatch(server, message, context=None):
    results = []
    server.dispatch_p(message, context).then(results.append).wait()
    return results[0]


with subtest('Synopsis'):
    from Pyjo.MCP.Server import Server

    server = Server(name='calculator', version='1.0.0')

    @server.tool
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    is_ok(
        dispatch(server, request('tools/call', name='add', arguments={'a': 1, 'b': 2}))['result']['structuredContent'],
        3,
        'add',
    )

    # Or import the module, as in Google Python Style Guide

    import Pyjo.MCP.Server

    server = Pyjo.MCP.Server.new(name='calculator', version='1.0.0', instructions='Arithmetic for the model.')
    server.tool('add', lambda a, b: a + b, input_schema={'type': 'object', 'properties': {'a': {}, 'b': {}}})
    is_ok(
        dispatch(server, request('tools/call', name='add', arguments={'a': 1, 'b': 2}))['result']['content'][0]['text'],
        '3',
        'add',
    )

    # Pyjoyment
    app = Pyjoyment.new()
    app.log.level = 'fatal'
    app.plugin('AllowedHosts')
    app.routes.any('/mcp').to(cb=server.to_action())
    t = Pyjo.Test.Pyjo.new(app)
    headers = {'MCP-Protocol-Version': '2026-07-28', 'Mcp-Method': 'server/discover'}
    t.post_ok('/mcp', headers, json=request('server/discover')).status_is(200)
    t.json_is('/result/instructions', 'Arithmetic for the model.')
    t.post_ok('/mcp', {**headers, 'Origin': 'https://evil.com'}, json=request('server/discover')).status_is(403)
    t.ua.close()

with subtest('Context'):
    server = Pyjo.MCP.Server.new()

    @server.tool(context=True)
    def whoami(context) -> str:
        return context.client_info.get('name', 'unknown')

    is_ok(
        dispatch(server, request('tools/call', name='whoami'))['result']['content'][0]['text'],
        'ExampleClient',
        'whoami',
    )

with subtest('Context.new'):
    context = Pyjo.MCP.Server.Context.new()
    is_ok(context.controller, None, 'context')
    c = Pyjoyment.new().build_controller()
    context = Pyjo.MCP.Server.Context.new(c)
    is_ok(context.controller, c, 'context')

with subtest('Context attributes'):
    context = Pyjo.MCP.Server.Context.new()
    dispatch(server, request('tools/list'), context)
    capabilities = context.client_capabilities
    is_deeply_ok(capabilities, {}, 'capabilities')
    info = context.client_info
    is_deeply_ok(info, {'name': 'ExampleClient', 'version': '1.0.0'}, 'info')
    c = context.controller
    is_ok(c, None, 'c')
    meta = context.meta
    is_deeply_ok(meta, META, 'meta')
    version = context.protocol_version
    is_ok(version, '2026-07-28', 'version')
    status = context.status
    is_ok(status, None, 'status')

with subtest('exception'):
    server = Pyjo.MCP.Server.new()
    got = []

    @server.on('exception')
    def exception(server, e, context):
        got.append(e)

    server.tool('fails', lambda: 1 / 0)
    dispatch(server, request('tools/call', name='fails'))
    isa_ok(got[0], ZeroDivisionError, 'e')

    server.on('exception', lambda server, e, context: print(f'Failed: {e}'))
    with contextlib.redirect_stdout(io.StringIO()) as stdout:
        dispatch(server, request('tools/call', name='fails'))
    is_ok(stdout.getvalue(), 'Failed: division by zero\n', 'printed')

with subtest('new'):
    server = Pyjo.MCP.Server.new()
    is_ok(server.name, 'Pyjo.MCP', 'name')
    server = Pyjo.MCP.Server.new(name='calculator', version='1.0.0', instructions='Arithmetic.')
    is_ok(server.instructions, 'Arithmetic.', 'instructions')

with subtest('Attributes'):
    scope = server.cache_scope
    is_ok(scope, 'public', 'scope')
    server.cache_scope = 'private'
    ttl = server.cache_ttl
    is_ok(ttl, 0, 'ttl')
    server.cache_ttl = 300000
    instructions = server.instructions
    server.instructions = 'Arithmetic for the model.'
    name = server.name
    is_ok(name, 'calculator', 'name')
    server.name = 'calculator'
    tools = server.tools
    is_deeply_ok(tools, [], 'tools')
    version = server.version
    is_ok(version, '1.0.0', 'version')
    server.version = '2.0.0'
    result = dispatch(server, request('server/discover'))['result']
    is_deeply_ok(
        [result['ttlMs'], result['cacheScope'], result['instructions'], result['_meta']],
        [
            300000,
            'private',
            'Arithmetic for the model.',
            {'io.modelcontextprotocol/serverInfo': {'name': 'calculator', 'version': '2.0.0'}},
        ],
        'discover',
    )

with subtest('dispatch_p'):
    server = Pyjo.MCP.Server.new()
    server.tool('add', lambda a, b: a + b, input_schema={'type': 'object'})
    promise = server.dispatch_p(request('tools/list'))
    results = []
    promise.then(results.append).wait()
    context = Pyjo.MCP.Server.Context.new()
    promise = server.dispatch_p(
        b'{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {"_meta": {}}}', context
    )
    promise.then(results.append).wait()
    is_ok(results[0]['result']['tools'][0]['name'], 'add', 'request')
    is_ok(results[1]['error']['code'], -32602, 'JSON')
    is_ok(context.status, 400, 'status of the error')
    is_ok(dispatch(server, [request('tools/list')])['error']['code'], -32600, 'batch')
    is_ok(dispatch(server, {**request('tools/list'), 'id': None})['error']['code'], -32600, 'id of null')

with subtest('tool'):
    server = Pyjo.MCP.Server.new()
    cb = server.tool('add', lambda a, b: a + b, input_schema={'type': 'object'})
    is_ok(cb(1, 2), 3, 'cb')
    cb = server.tool('whoami', lambda context: context.client_info.get('name'), context=True)

    @server.tool
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    @server.tool('math.multiply', title='Multiplication', annotations={'readOnlyHint': True})
    def multiply(a: int, b: int) -> int:
        """Multiply two numbers."""
        return a * b

    is_deeply_ok([tool.name for tool in server.tools], ['add', 'whoami', 'add', 'math.multiply'], 'tools')
    is_ok(server.tools[3].title, 'Multiplication', 'title')

with subtest('to_action'):
    action = server.to_action()
    ok(callable(action), 'action')

    # Pyjoyment.Lite
    from Pyjoyment.Lite import any

    any('/mcp', server.to_action())

    # Pyjoyment
    app = Pyjoyment.new()
    app.routes.any('/mcp').to(cb=server.to_action())
    pass_ok('routes')

done_testing()
