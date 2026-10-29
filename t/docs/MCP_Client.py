import Pyjo.IOLoop
import Pyjo.JSON
import Pyjo.MCP.Server
import Pyjo.MCP.Tool
import Pyjo.SSE
import Pyjo.Test.Pyjo
import Pyjo.UserAgent
import Pyjoyment

from Pyjo.Test import *

import contextlib
import io


# The server of the examples, the calculator of the synopsis of Pyjo.MCP.Server with greet and divide
server = Pyjo.MCP.Server.new(name='calculator', version='1.0.0')


@server.tool
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


@server.tool
def greet(name: str = 'stranger') -> str:
    """Greet somebody by name."""
    return f'Hello, {name}!'


@server.tool
def divide(a: float, b: float) -> float:
    """Divide the first number by the second one."""
    if b == 0:
        raise Pyjo.MCP.Tool.Error.new('Division by zero')
    return a / b


app = Pyjoyment.new()
app.log.level = 'fatal'
app.routes.any('/mcp').to(cb=server.to_action())


def local(client, application=app):
    # The requests of the client to the application, on the event loop of the singleton, as Pyjo.Test.Pyjo has them
    client.url = '/mcp'
    client.ua = Pyjo.UserAgent.new(ioloop=Pyjo.IOLoop.singleton)
    client.ua.server.app = application
    return client


with subtest('Synopsis'):
    from Pyjo.MCP.Client import Client

    client = local(Client('http://127.0.0.1:3000/mcp'))
    tools = client.list_tools()['tools']
    is_deeply_ok([tool['name'] for tool in tools], ['add', 'greet', 'divide'], 'tools')

    # Or import the module, as in Google Python Style Guide

    import Pyjo.MCP.Client

    client = local(Pyjo.MCP.Client.new('http://127.0.0.1:3000/mcp', name='calculator-client'))
    result = client.call_tool('add', {'a': 1, 'b': 2})
    with contextlib.redirect_stdout(io.StringIO()) as stdout:
        print(result['structuredContent'])

        # Non-blocking
        client.call_tool_p('add', {'a': 1, 'b': 2}).then(lambda result: print(result['structuredContent'])).wait()
    is_ok(stdout.getvalue(), '3\n3\n', 'printed')

with subtest('invalid_tool'):
    definitions = [{'name': 'bad', 'inputSchema': {'properties': {'n': {'type': 'number', 'x-mcp-header': 'N'}}}}]
    listing = Pyjoyment.new()
    listing.log.level = 'fatal'
    listing.routes.post('/mcp').to(
        cb=lambda c: c.render(json={'jsonrpc': '2.0', 'id': c.req.json()['id'], 'result': {'tools': definitions}})
    )
    client = local(Pyjo.MCP.Client.new(), listing)
    got = []

    @client.on('invalid_tool')
    def invalid_tool(client, definition, e):
        got.append((definition['name'], e))

    client.on('invalid_tool', lambda client, definition, e: print(f'{definition["name"]}: {e.message}'))
    with contextlib.redirect_stdout(io.StringIO()) as stdout:
        result = client.list_tools()
    is_deeply_ok(result['tools'], [], 'left out')
    is_ok(got[0][0], 'bad', 'definition')
    like_ok(stdout.getvalue(), r'^bad: .*x-mcp-header', 'printed')


# A server that answers with a stream of events, with a notification of the progress before the response
def streams(c):
    def respond(response):
        notification = {'jsonrpc': '2.0', 'method': 'notifications/progress', 'params': {'progress': 1}}
        c.res.headers.content_type = 'text/event-stream'
        c.render(data=b''.join(Pyjo.SSE.build_event({'text': Pyjo.JSON.to_json(m)}) for m in (notification, response)))

    c.render_later()
    return server.dispatch_p(c.req.json()).then(respond)


with subtest('notification'):
    streamer = Pyjoyment.new()
    streamer.log.level = 'fatal'
    streamer.routes.post('/mcp').to(cb=streams)
    client = local(Pyjo.MCP.Client.new(), streamer)
    got = []

    @client.on('notification')
    def notification(client, message):
        got.append(message)

    client.on('notification', lambda client, message: print(message['method']))
    with contextlib.redirect_stdout(io.StringIO()) as stdout:
        result = client.call_tool('greet')
    is_ok(result['content'][0]['text'], 'Hello, stranger!', 'response')
    is_deeply_ok(got, [{'jsonrpc': '2.0', 'method': 'notifications/progress', 'params': {'progress': 1}}], 'message')
    is_ok(stdout.getvalue(), 'notifications/progress\n', 'printed')

with subtest('new'):
    client = Pyjo.MCP.Client.new()
    is_ok(client.url, 'http://localhost:3000/mcp', 'url')
    client = Pyjo.MCP.Client.new('http://127.0.0.1:3000/mcp', name='calculator-client', version='2.0.0')
    is_deeply_ok((client.url, client.name, client.version), ('http://127.0.0.1:3000/mcp', 'calculator-client', '2.0.0'))
    t = Pyjo.Test.Pyjo.new(app)
    client = Pyjo.MCP.Client.new('/mcp', ua=t.ua)
    is_ok(client.discover()['supportedVersions'], ['2026-07-28'], 'user agent of the test')
    t.ua.close()

with subtest('Attributes'):
    client = local(Pyjo.MCP.Client.new())
    capabilities = client.capabilities
    is_deeply_ok(capabilities, {}, 'capabilities')
    client.capabilities = {'elicitation': {}}
    headers = client.headers
    is_deeply_ok(headers, {}, 'headers')
    client.headers = {'Authorization': 'Bearer abc123'}
    name = client.name
    is_ok(name, 'Pyjo.MCP', 'name')
    client.name = 'calculator-client'
    version = client.protocol_version
    is_ok(version, '2026-07-28', 'protocol version')
    client.protocol_version = '2026-07-28'
    tools = client.tools
    is_deeply_ok(tools, {}, 'tools')
    url = client.url
    is_ok(url, '/mcp', 'url')
    client.url = 'http://127.0.0.1:3000/mcp'
    version = client.version
    is_ok(version, '1.0.0', 'version')
    client.version = '2.0.0'
    ua = client.ua
    isa_ok(ua, Pyjo.UserAgent.object, 'ua')
    client.ua = Pyjo.UserAgent.new()
    meta = client.build_request('tools/list')['params']['_meta']
    is_deeply_ok(
        meta,
        {
            'io.modelcontextprotocol/clientCapabilities': {'elicitation': {}},
            'io.modelcontextprotocol/clientInfo': {'name': 'calculator-client', 'version': '2.0.0'},
            'io.modelcontextprotocol/protocolVersion': '2026-07-28',
        },
        '_meta',
    )
    is_ok(client.build_tx(client.build_request('tools/list')).req.headers.authorization, 'Bearer abc123', 'header')
    client.ua.close()

with subtest('build_notification'):
    client = Pyjo.MCP.Client.new()
    notification = client.build_notification('notifications/cancelled', {'requestId': 1})
    is_deeply_ok(
        notification,
        {'jsonrpc': '2.0', 'method': 'notifications/cancelled', 'params': {'requestId': 1}},
        'notification',
    )

with subtest('build_request'):
    request = client.build_request('tools/call', {'name': 'add', 'arguments': {'a': 1, 'b': 2}})
    is_deeply_ok(
        [request['id'], request['method'], request['params']['arguments']],
        [1, 'tools/call', {'a': 1, 'b': 2}],
        'request',
    )

with subtest('build_tx'):
    client = local(Pyjo.MCP.Client.new())
    request = client.build_request('tools/call', {'name': 'add', 'arguments': {'a': 1, 'b': 2}})
    tx = client.build_tx(request)
    is_ok(tx.req.headers.header('Mcp-Name'), 'add', 'Mcp-Name')

    # The request without its header Mcp-Name
    t = Pyjo.Test.Pyjo.new(app)
    tx = client.build_tx(client.build_request('tools/call', {'name': 'add', 'arguments': {}}))
    tx.req.headers.remove('Mcp-Name')
    t.request_ok(tx).status_is(400)
    t.json_is('/error/message', 'Header mismatch: Missing Mcp-Name header')
    t.ua.close()

with subtest('call_tool'):
    result = client.call_tool('greet')
    is_ok(result['content'][0]['text'], 'Hello, stranger!', 'without arguments')
    result = client.call_tool('greet', {'name': 'Pyjo'})
    is_ok(result['content'][0]['text'], 'Hello, Pyjo!', 'arguments')

    result = client.call_tool('divide', {'a': 1, 'b': 0})
    with contextlib.redirect_stdout(io.StringIO()) as stdout:
        if result['isError']:
            print(result['content'][0]['text'])
    is_ok(stdout.getvalue(), 'Division by zero\n', 'printed')

with subtest('call_tool_p'):
    promise = client.call_tool_p('greet', {'name': 'Pyjo'})
    results = []
    promise.then(results.append).wait()
    is_ok(results[0]['content'][0]['text'], 'Hello, Pyjo!', 'result')

with subtest('discover'):
    result = client.discover()
    is_deeply_ok(result['supportedVersions'], ['2026-07-28'], 'result')

with subtest('discover_p'):
    promise = client.discover_p()
    results = []
    promise.then(results.append).wait()
    is_deeply_ok(results[0]['capabilities'], {'tools': {}}, 'result')

with subtest('list_tools'):
    result = client.list_tools()
    is_ok(len(result['tools']), 3, 'result')

    with contextlib.redirect_stdout(io.StringIO()) as stdout:
        for tool in client.list_tools()['tools']:
            print(tool['name'], tool.get('description'))
    is_ok(
        stdout.getvalue(),
        'add Add two numbers.\ngreet Greet somebody by name.\ndivide Divide the first number by the second one.\n',
        'printed',
    )

with subtest('list_tools_p'):
    promise = client.list_tools_p()
    results = []
    promise.then(results.append).wait()
    is_ok(len(results[0]['tools']), 3, 'result')

with subtest('send_request'):
    request = client.build_request('server/discover')
    response = client.send_request(request)
    is_ok(response['id'], request['id'], 'response')

    with contextlib.redirect_stdout(io.StringIO()) as stdout:
        response = client.send_request(client.build_request('tools/list'))
        print(response['result']['tools'][0]['name'])
    is_ok(stdout.getvalue(), 'add\n', 'printed')

with subtest('send_request_p'):
    promise = client.send_request_p(request)
    results = []
    promise.then(results.append).wait()
    is_ok(results[0]['result']['supportedVersions'], ['2026-07-28'], 'response')

done_testing()
