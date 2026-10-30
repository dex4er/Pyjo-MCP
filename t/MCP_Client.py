import Pyjo.IOLoop
import Pyjo.JSON
import Pyjo.JSON.RPC
import Pyjo.MCP
import Pyjo.MCP.Client
import Pyjo.MCP.Server
import Pyjo.MCP.Tool
import Pyjo.Promise
import Pyjo.SSE
import Pyjo.UserAgent
import Pyjoyment

from Pyjo.Test import *

import base64


# The client of MCP over Streamable HTTP, against the server of the distribution, which checks the headers of MCP

server = Pyjo.MCP.Server.new(name='ExampleServer', version='1.0.0', instructions='Utilities.')


@server.tool
def greet(name: str) -> str:
    """Greet somebody by name."""
    return f'Hello, {name}!'


@server.tool
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


@server.tool
def later(value: str) -> str:
    """Answer later."""
    return Pyjo.Promise.timer(0.01, value)


@server.tool
def divide(a: float, b: float) -> float:
    """Divide."""
    if b == 0:
        raise Pyjo.MCP.Tool.Error.new('Division by zero')
    return a / b


@server.tool(context=True)
def whoami(context) -> str:
    """Who calls."""
    info = context.client_info
    return f'{info.get("name")} {info.get("version")} {context.client_capabilities} {context.protocol_version}'


server.tool(
    'execute_sql',
    lambda region, query, limit=None, dry=None: f'{region}: {query} {limit} {dry}',
    input_schema={
        'type': 'object',
        'properties': {
            'region': {'type': 'string', 'x-mcp-header': 'Region'},
            'limit': {'type': 'integer', 'x-mcp-header': 'Limit'},
            'dry': {'type': 'boolean', 'x-mcp-header': 'Dry'},
            'query': {'type': 'string'},
        },
        'required': ['region', 'query'],
    },
)


@server.prompt
def review(code: str, language: str = 'Python') -> str:
    """Review a piece of code."""
    return f'Review this {language} code:\n{code}'


@server.resource('file:///project/README.md', mime_type='text/markdown')
def readme() -> str:
    """The documentation of the project."""
    return '# Project'


server.resource('file:///project/logo.png', lambda: b'\x89PNG', name='logo', mime_type='image/png')
server.resource('notes://{number}', lambda number: f'Note {number}', name='note')


def application(action):
    app = Pyjoyment.new()
    app.log.level = 'fatal'
    if action is not None:
        app.routes.any('/mcp').to(cb=action)
    return app


app = application(server.to_action())

# The headers of the requests, as the server gets them
sent = []
app.hook('before_dispatch', lambda c: sent.append(c.req.headers.to_dict()))


def client(application=app, **options):
    # The blocking requests on the event loop of the singleton, which the server of the application settles its promises
    # on, as Pyjo.Test.Pyjo has them
    ua = Pyjo.UserAgent.new(ioloop=Pyjo.IOLoop.singleton)
    ua.server.app = application
    return Pyjo.MCP.Client.new('/mcp', ua=ua, **options)


def error(e):
    return e.code, e.message


def failure(cb):
    # The exception that the callback raises, or None
    try:
        cb()
    except Exception as e:
        return e
    return None


with subtest('Requests'):
    c = client()
    request = c.build_request('tools/list')
    is_deeply_ok(
        request,
        {
            'jsonrpc': '2.0',
            'method': 'tools/list',
            'params': {
                '_meta': {
                    'io.modelcontextprotocol/clientCapabilities': {},
                    'io.modelcontextprotocol/clientInfo': {'name': 'Pyjo.MCP', 'version': '1.0.0'},
                    'io.modelcontextprotocol/protocolVersion': '2026-07-28',
                }
            },
            'id': 1,
        },
        'request',
    )
    is_ok(c.build_request('tools/list')['id'], 2, 'next id')
    request = c.build_request(
        'tools/call', {'name': 'add', '_meta': {'progressToken': 'p1', Pyjo.MCP.META_CLIENT_INFO: 1}}
    )
    is_deeply_ok(
        request['params']['_meta'],
        {
            'progressToken': 'p1',
            'io.modelcontextprotocol/clientInfo': {'name': 'Pyjo.MCP', 'version': '1.0.0'},
            'io.modelcontextprotocol/clientCapabilities': {},
            'io.modelcontextprotocol/protocolVersion': '2026-07-28',
        },
        '_meta of the parameters, under the one of the client',
    )
    is_ok(request['params']['name'], 'add', 'parameters')
    is_deeply_ok(
        c.build_notification('notifications/cancelled', {'requestId': 1}),
        {'jsonrpc': '2.0', 'method': 'notifications/cancelled', 'params': {'requestId': 1}},
        'notification',
    )
    is_deeply_ok(c.build_notification('notifications/initialized')['params'], {}, 'notification without parameters')

with subtest('Discovery'):
    c = client()
    result = c.discover()
    is_deeply_ok(result['supportedVersions'], ['2026-07-28'], 'supported versions')
    is_ok(result['instructions'], 'Utilities.', 'instructions')
    is_deeply_ok(
        result['_meta'],
        {'io.modelcontextprotocol/serverInfo': {'name': 'ExampleServer', 'version': '1.0.0'}},
        'server info',
    )
    is_ok(sent[-1]['MCP-Protocol-Version'], '2026-07-28', 'MCP-Protocol-Version')
    is_ok(sent[-1]['Mcp-Method'], 'server/discover', 'Mcp-Method')
    is_ok(sent[-1]['Accept'], 'application/json, text/event-stream', 'Accept')
    is_ok(sent[-1]['Content-Type'], 'application/json', 'Content-Type')
    ok('Mcp-Name' not in sent[-1], 'no Mcp-Name')

with subtest('Tools'):
    c = client()
    is_deeply_ok(c.tools, {}, 'no tools yet')
    result = c.list_tools()
    is_deeply_ok(
        [tool['name'] for tool in result['tools']],
        ['greet', 'add', 'later', 'divide', 'whoami', 'execute_sql'],
        'tools',
    )
    is_ok(result['resultType'], 'complete', 'result')
    is_deeply_ok(list(c.tools), ['greet', 'add', 'later', 'divide', 'whoami', 'execute_sql'], 'tools of the client')
    isa_ok(c.tools['add'], Pyjo.MCP.Tool.object, 'tool')
    is_ok(sent[-1]['Mcp-Method'], 'tools/list', 'Mcp-Method')

with subtest('Calls'):
    c = client()
    result = c.call_tool('greet', {'name': 'Pyjo'})
    is_deeply_ok(result['content'], [{'type': 'text', 'text': 'Hello, Pyjo!'}], 'text')
    is_ok(result['isError'], False, 'no error')
    is_ok(sent[-1]['Mcp-Method'], 'tools/call', 'Mcp-Method')
    is_ok(sent[-1]['Mcp-Name'], 'greet', 'Mcp-Name')
    is_ok(c.call_tool('add', {'a': 1, 'b': 2})['structuredContent'], 3, 'structured content')
    is_ok(c.call_tool('later', {'value': 'later'})['content'][0]['text'], 'later', 'promise of the tool')
    result = c.call_tool('divide', {'a': 1, 'b': 0})
    is_deeply_ok(result['content'], [{'type': 'text', 'text': 'Division by zero'}], 'error of the tool')
    is_ok(result['isError'], True, 'isError')
    result = c.call_tool('greet')
    is_ok(result['isError'], True, 'no arguments')
    e = failure(lambda: c.call_tool('power', {'a': 2}))
    isa_ok(e, Pyjo.JSON.RPC.Error, 'unknown tool')
    is_deeply_ok(error(e), (-32602, 'Unknown tool: power'), 'error of JSON-RPC')

with subtest('Prompts'):
    c = client()
    result = c.list_prompts()
    is_deeply_ok(
        result['prompts'],
        [
            {
                'name': 'review',
                'description': 'Review a piece of code.',
                'arguments': [{'name': 'code', 'required': True}, {'name': 'language', 'required': False}],
            }
        ],
        'prompts',
    )
    is_ok(sent[-1]['Mcp-Method'], 'prompts/list', 'Mcp-Method')
    result = c.get_prompt('review', {'code': 'x = 1'})
    is_deeply_ok(
        result['messages'],
        [{'role': 'user', 'content': {'type': 'text', 'text': 'Review this Python code:\nx = 1'}}],
        'messages',
    )
    is_ok(sent[-1]['Mcp-Method'], 'prompts/get', 'Mcp-Method')
    is_ok(sent[-1]['Mcp-Name'], 'review', 'Mcp-Name')
    e = failure(lambda: c.get_prompt('review'))
    isa_ok(e, Pyjo.JSON.RPC.Error, 'missing argument')
    is_deeply_ok(error(e), (-32602, 'Missing required argument: code'), 'error of JSON-RPC')
    e = failure(lambda: c.get_prompt('unknown'))
    is_deeply_ok(error(e), (-32602, 'Unknown prompt: unknown'), 'unknown prompt')

with subtest('Resources'):
    c = client()
    result = c.list_resources()
    is_deeply_ok(
        [resource['uri'] for resource in result['resources']],
        ['file:///project/README.md', 'file:///project/logo.png'],
        'resources',
    )
    is_ok(sent[-1]['Mcp-Method'], 'resources/list', 'Mcp-Method')
    result = c.read_resource('file:///project/README.md')
    is_deeply_ok(
        result['contents'],
        [{'uri': 'file:///project/README.md', 'mimeType': 'text/markdown', 'text': '# Project'}],
        'contents',
    )
    is_ok(sent[-1]['Mcp-Method'], 'resources/read', 'Mcp-Method')
    is_ok(sent[-1]['Mcp-Name'], 'file:///project/README.md', 'Mcp-Name')
    blob = base64.b64encode(b'\x89PNG').decode()
    is_ok(c.read_resource('file:///project/logo.png')['contents'][0]['blob'], blob, 'blob')
    e = failure(lambda: c.read_resource('file:///nonexistent.txt'))
    isa_ok(e, Pyjo.JSON.RPC.Error, 'resource not found')
    is_deeply_ok(error(e), (-32602, 'Resource not found'), 'error of JSON-RPC')
    result = c.list_resource_templates()
    is_deeply_ok(
        result['resourceTemplates'],
        [{'uriTemplate': 'notes://{number}', 'name': 'note', 'mimeType': 'text/plain'}],
        'templates',
    )
    is_ok(sent[-1]['Mcp-Method'], 'resources/templates/list', 'Mcp-Method')
    is_ok(c.read_resource('notes://1')['contents'][0]['text'], 'Note 1', 'resource of a template')
    is_deeply_ok(e.data, {'uri': 'file:///nonexistent.txt'}, 'data of the error')

with subtest('Input'):
    # A server of its own, whose tool, prompt and resource ask for input
    asking = Pyjo.MCP.Server.new(name='ExampleServer')
    asking.secrets = ['passw0rd']
    asking.tool('confirm', lambda context, path: context.elicit('ok', f'Delete {path}?')['action'], context=True)
    asking.prompt('haiku', lambda context: context.sample('haiku', 'A haiku.', 50)['content']['text'], context=True)
    asking.resource('roots://all', lambda context: str(len(context.list_roots()['roots'])), context=True)
    c = client(application(asking.to_action()))
    c.capabilities = {'elicitation': {}, 'sampling': {}, 'roots': {}}
    result = c.call_tool('confirm', {'path': 'a.txt'})
    is_ok(result['resultType'], 'input_required', 'input required')
    is_ok(result['inputRequests']['ok']['params']['message'], 'Delete a.txt?', 'request of the input')
    result = c.call_tool('confirm', {'path': 'a.txt'}, input_responses={'ok': {'action': 'accept'}})
    is_ok(result['content'][0]['text'], 'accept', 'input responses')
    result = c.get_prompt('haiku')
    sampled = {'role': 'assistant', 'content': {'type': 'text', 'text': 'Drops'}, 'model': 'test'}
    result = c.get_prompt('haiku', input_responses={'haiku': sampled}, request_state=result.get('requestState'))
    is_ok(result['messages'][0]['content']['text'], 'Drops', 'prompt')
    is_ok(c.read_resource('roots://all')['inputRequests']['roots']['method'], 'roots/list', 'resource')
    result = c.read_resource('roots://all', input_responses={'roots': {'roots': []}})
    is_ok(result['contents'][0]['text'], '0', 'resource with input')
    e = failure(lambda: c.call_tool('confirm', {'path': 'a.txt'}, request_state='nonsense'))
    is_deeply_ok(error(e), (-32602, 'Invalid or expired requestState'), 'request state')
    results = []
    c.call_tool_p('confirm', {'path': 'a.txt'}, input_responses={'ok': {'action': 'decline'}}).then(
        lambda result: results.append(result['content'][0]['text'])
    ).wait()
    c.get_prompt_p('haiku', input_responses={'haiku': sampled}).then(
        lambda result: results.append(result['messages'][0]['content']['text'])
    ).wait()
    c.read_resource_p('roots://all', input_responses={'roots': {'roots': [{'uri': 'file:///a'}]}}).then(
        lambda result: results.append(result['contents'][0]['text'])
    ).wait()
    is_deeply_ok(results, ['decline', 'Drops', '1'], 'promises')

with subtest('Subscriptions'):
    c = client()
    messages = []

    # The application changes the server after the acknowledgment, and the client closes the subscription after the
    # update of the resource
    def changes(message):
        messages.append(message)
        if message['method'] == 'notifications/subscriptions/acknowledged':
            Pyjo.IOLoop.next_tick(
                lambda loop: (
                    server.notify_list_changed('tools'),
                    server.notify_resource_updated('file:///project/README.md'),
                )
            )
        return message['method'] != 'notifications/resources/updated'

    notifications = {'toolsListChanged': True, 'resourceSubscriptions': ['file:///project/README.md']}
    is_ok(c.listen(notifications, changes), None, 'closed by the function')
    is_ok(sent[-1]['Mcp-Method'], 'subscriptions/listen', 'Mcp-Method')
    is_deeply_ok(
        [message['method'] for message in messages],
        [
            'notifications/subscriptions/acknowledged',
            'notifications/tools/list_changed',
            'notifications/resources/updated',
        ],
        'messages',
    )
    is_deeply_ok(messages[0]['params']['notifications'], notifications, 'acknowledged')
    is_ok(messages[2]['params']['uri'], 'file:///project/README.md', 'resource')
    is_ok(messages[2]['params']['_meta'][Pyjo.MCP.META_SUBSCRIPTION_ID], c._id, 'subscription')
    Pyjo.Promise.timer(0.01).wait()
    is_ok(server.notify_list_changed('tools'), 0, 'closed')

    # The server ends the subscription when its event loop stops gracefully
    def stop(message):
        Pyjo.IOLoop.next_tick(lambda loop: loop.emit('finish'))

    result = c.listen({'promptsListChanged': True}, stop)
    is_deeply_ok(
        result,
        {
            'resultType': 'complete',
            '_meta': {
                Pyjo.MCP.META_SUBSCRIPTION_ID: c._id,
                Pyjo.MCP.META_SERVER_INFO: {'name': 'ExampleServer', 'version': '1.0.0'},
            },
        },
        'ended by the server',
    )
    results = []
    c.listen_p({'promptsListChanged': True}, stop).then(results.append).wait()
    is_ok(results[0]['_meta'][Pyjo.MCP.META_SUBSCRIPTION_ID], c._id, 'non-blocking')
    c.listen_p({}, lambda message: False).then(lambda result=None: results.append(result)).wait()
    is_ok(results[1], None, 'non-blocking, closed by the function')

    # A server that drops the subscription, and one that does not have it
    def drop(c):
        c.res.headers.content_type = 'text/event-stream'
        c.write_chunk(Pyjo.SSE.build_event({'text': '{"jsonrpc": "2.0", "method": "notifications/message"}'}))
        c.write_chunk(b'')

    c = client(application(drop))
    e = failure(lambda: c.listen({}, lambda message: None))
    isa_ok(e, Pyjo.Exception.object, 'dropped')
    like_ok(e.message, r'No response', 'message')
    c = client(application(None))
    errors = []
    c.listen_p({}, lambda message: None).catch(errors.append).wait()
    is_ok(errors[0].message, '/mcp: 404 Not Found', 'error of HTTP')

with subtest('Meta of the client'):
    c = client(name='ExampleClient', version='2.0.0')
    c.capabilities = {'elicitation': {}}
    is_ok(
        c.call_tool('whoami')['content'][0]['text'],
        "ExampleClient 2.0.0 {'elicitation': {}} 2026-07-28",
        'name, version and capabilities',
    )

with subtest('Headers of the arguments'):
    c = client()
    e = failure(lambda: c.call_tool('execute_sql', {'region': 'eu', 'query': 'SELECT 1'}))
    isa_ok(e, Pyjo.JSON.RPC.Error, 'tool not listed yet')
    is_deeply_ok(error(e), (-32020, 'Header mismatch: Missing Mcp-Param-Region header'), 'missing header')
    c.list_tools()
    result = c.call_tool('execute_sql', {'region': 'eu', 'query': 'SELECT 1', 'limit': 5, 'dry': True})
    is_ok(result['content'][0]['text'], 'eu: SELECT 1 5 True', 'result')
    is_ok(sent[-1]['Mcp-Param-Region'], 'eu', 'string')
    is_ok(sent[-1]['Mcp-Param-Limit'], '5', 'integer')
    is_ok(sent[-1]['Mcp-Param-Dry'], 'true', 'boolean')
    result = c.call_tool('execute_sql', {'region': 'Hello, 世界', 'query': 'SELECT 1'})
    is_ok(result['content'][0]['text'], 'Hello, 世界: SELECT 1 None None', 'result')
    is_ok(sent[-1]['Mcp-Param-Region'], f'=?base64?{base64.b64encode("Hello, 世界".encode()).decode()}?=', 'Base64')
    ok('Mcp-Param-Limit' not in sent[-1], 'no header without the argument')
    c.call_tool('execute_sql', {'region': ' eu', 'query': 'x'})
    is_ok(sent[-1]['Mcp-Param-Region'], '=?base64?IGV1?=', 'Base64 of a space at the start')
    c.call_tool('execute_sql', {'region': '=?base64?ZXU=?=', 'query': 'x'})
    is_ok(
        sent[-1]['Mcp-Param-Region'],
        f'=?base64?{base64.b64encode(b"=?base64?ZXU=?=").decode()}?=',
        'Base64 of what looks like Base64',
    )
    c.headers = {'Authorization': 'Bearer abc123', 'Mcp-Method': 'tools/list'}
    c.call_tool('greet', {'name': 'Pyjo'})
    is_ok(sent[-1]['Authorization'], 'Bearer abc123', 'header of the client')
    is_ok(sent[-1]['Mcp-Method'], 'tools/call', 'under the headers of MCP')

with subtest('Transaction'):
    c = client()
    tx = c.build_tx(c.build_request('tools/call', {'name': 'greet', 'arguments': {'name': 'Pyjo'}}))
    is_ok(tx.req.method, 'POST', 'method')
    is_ok(tx.req.url.to_str(), '/mcp', 'url')
    is_ok(tx.req.headers.header('Mcp-Name'), 'greet', 'Mcp-Name')
    is_ok(tx.req.json()['params']['name'], 'greet', 'body')
    tx.req.headers.remove('Mcp-Name')
    tx = c.ua.start(tx)
    is_ok(tx.res.code, 400, 'status')
    is_ok(tx.res.json()['error']['message'], 'Header mismatch: Missing Mcp-Name header', 'error')
    tx = c.build_tx(c.build_request('tools/call', {'name': 'Zoë'}))
    is_ok(tx.req.headers.header('Mcp-Name'), '=?base64?Wm/Dqw==?=', 'Base64 of Mcp-Name')

with subtest('Notifications'):
    c = client()
    is_ok(c.send_request(c.build_notification('notifications/cancelled', {'requestId': 1})), None, 'no response')
    is_ok(sent[-1]['Mcp-Method'], 'notifications/cancelled', 'Mcp-Method')
    response = c.send_request(c.build_request('tools/list'))
    is_ok(response['id'], c._id, 'response')
    is_ok(response['result']['tools'][0]['name'], 'greet', 'result')


# Servers that answer with a stream of events, a notification of their own before the response, as Streamable HTTP
# allows, with a Content-Length, whose events the user agent parses, or chunked, whose events stay in the body
def streamer(chunked):
    def events(c):
        def respond(response):
            notification = {'jsonrpc': '2.0', 'method': 'notifications/progress', 'params': {'progress': 1}}
            other = {'jsonrpc': '2.0', 'id': 'other', 'result': {}}
            data = b''.join(
                Pyjo.SSE.build_event({'text': Pyjo.JSON.to_json(m)}) for m in (notification, other, response)
            )
            data += Pyjo.SSE.build_event({'text': 'not JSON'})
            c.res.headers.content_type = 'text/event-stream'
            if chunked:
                c.write_chunk(data).write_chunk(b'')
            else:
                c.render(data=data)

        c.render_later()
        return server.dispatch_p(c.req.json()).then(respond)

    return application(events)


with subtest('Streams of events'):
    for name, chunked in (('Content-Length', False), ('chunked', True)):
        c = client(streamer(chunked))
        notifications = []
        c.on('notification', lambda client, message, notifications=notifications: notifications.append(message))
        result = c.call_tool('greet', {'name': 'Pyjo'})
        is_ok(result['content'][0]['text'], 'Hello, Pyjo!', f'response of a stream, {name}')
        is_deeply_ok(
            notifications,
            [
                {'jsonrpc': '2.0', 'method': 'notifications/progress', 'params': {'progress': 1}},
                {'jsonrpc': '2.0', 'id': 'other', 'result': {}},
            ],
            f'notifications, {name}',
        )

with subtest('Invalid tools'):
    definitions = [
        {
            'name': 'good',
            'inputSchema': {'type': 'object', 'properties': {'a': {'type': 'string', 'x-mcp-header': 'A'}}},
        },
        {
            'name': 'bad',
            'inputSchema': {'type': 'object', 'properties': {'n': {'type': 'number', 'x-mcp-header': 'N'}}},
        },
        {'name': 'plain'},
    ]
    listing = application(
        lambda c: c.render(json={'jsonrpc': '2.0', 'id': c.req.json()['id'], 'result': {'tools': definitions}})
    )
    c = client(listing)
    invalid = []
    c.on('invalid_tool', lambda client, definition, e: invalid.append((definition['name'], str(e.message))))
    result = c.list_tools()
    is_deeply_ok([tool['name'] for tool in result['tools']], ['good', 'plain'], 'invalid tool left out')
    is_deeply_ok(list(c.tools), ['good', 'plain'], 'tools of the client')
    is_ok(len(invalid), 1, 'event')
    is_ok(invalid[0][0], 'bad', 'definition')
    like_ok(invalid[0][1], r'x-mcp-header', 'exception')
    is_deeply_ok(definitions[1]['name'], 'bad', 'definitions as they are')


# A server of another revision, which rejects the one of the request, and tells the ones it supports
def revisions(supported):
    def action(c):
        request = c.req.json()
        version = request['params']['_meta'][Pyjo.MCP.META_PROTOCOL_VERSION]
        if version not in supported:
            data = {'supported': supported, 'requested': version}
            error = {'code': -32022, 'message': 'Unsupported protocol version', 'data': data}
            return c.render(json={'jsonrpc': '2.0', 'id': request['id'], 'error': error}, status=400)
        header = c.req.headers.header('MCP-Protocol-Version')
        c.render(json={'jsonrpc': '2.0', 'id': request['id'], 'result': {'version': f'{version} {header}'}})

    return application(action)


with subtest('Revisions'):
    c = client(revisions(['2026-07-28']))
    c.protocol_version = '2025-11-25'
    is_ok(c.discover()['version'], '2026-07-28 2026-07-28', 'newest revision that both support')
    is_ok(c.protocol_version, '2026-07-28', 'kept')
    c = client(revisions(['2030-01-01']))
    e = failure(lambda: c.discover())
    isa_ok(e, Pyjo.JSON.RPC.Error, 'no revision that both support')
    is_ok(e.code, -32022, 'error')
    is_deeply_ok(e.data, {'supported': ['2030-01-01'], 'requested': '2026-07-28'}, 'data')
    is_ok(c.protocol_version, '2026-07-28', 'not changed')
    c = client(revisions(['2026-07-28']))
    c.protocol_version = '2025-11-25'
    results = []
    c.discover_p().then(results.append).wait()
    is_ok(results[0]['version'], '2026-07-28 2026-07-28', 'non-blocking')

with subtest('Errors of HTTP'):
    c = client(application(None))
    e = failure(lambda: c.discover())
    isa_ok(e, Pyjo.Exception.object, 'not a server of MCP')
    is_ok(e.message, '/mcp: 404 Not Found', 'message')
    legacy = application(
        lambda c: c.render(
            text='Bad Request: Unsupported protocol version (supported versions: 2025-11-25)', format='txt', status=400
        )
    )
    c = client(legacy)
    e = failure(lambda: c.list_tools())
    isa_ok(e, Pyjo.Exception.object, 'server of an older revision')
    is_ok(
        e.message,
        '/mcp: 400 Bad Request: Bad Request: Unsupported protocol version (supported versions: 2025-11-25)',
        'text of the error',
    )
    c = client(application(lambda c: c.rendered(202)))
    e = failure(lambda: c.discover())
    isa_ok(e, Pyjo.Exception.object, 'request without a response')
    is_ok(e.message, 'No response', 'message')

with subtest('Non-blocking'):
    c = client()
    results, errors = [], []
    c.discover_p().then(lambda result: results.append(result['instructions'])).wait()
    c.list_tools_p().then(lambda result: results.append(len(result['tools']))).wait()
    is_ok(len(c.tools), 6, 'tools of the client')
    c.call_tool_p('add', {'a': 1, 'b': 2}).then(lambda result: results.append(result['structuredContent'])).wait()
    c.call_tool_p('later', {'value': 'later'}).then(lambda result: results.append(result['content'][0]['text'])).wait()
    c.send_request_p(c.build_notification('notifications/cancelled')).then(
        lambda response=None: results.append(response)
    ).wait()
    c.list_prompts_p().then(lambda result: results.append(len(result['prompts']))).wait()
    c.get_prompt_p('review', {'code': 'x'}).then(lambda result: results.append(len(result['messages']))).wait()
    c.list_resources_p().then(lambda result: results.append(len(result['resources']))).wait()
    c.list_resource_templates_p().then(lambda result: results.append(len(result['resourceTemplates']))).wait()
    c.read_resource_p('file:///project/README.md').then(
        lambda result: results.append(result['contents'][0]['text'])
    ).wait()
    is_deeply_ok(results, ['Utilities.', 6, 3, 'later', None, 1, 1, 2, 1, '# Project'], 'results')
    c.call_tool_p('power').catch(errors.append).wait()
    is_deeply_ok(error(errors[0]), (-32602, 'Unknown tool: power'), 'error of JSON-RPC')
    c = client(application(None))
    c.discover_p().catch(errors.append).wait()
    is_ok(errors[1].message, '/mcp: 404 Not Found', 'error of HTTP')

done_testing()
