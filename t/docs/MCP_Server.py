import Pyjo.IOLoop
import Pyjo.MCP.Test
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

    @server.prompt
    def explain(expression: str) -> str:
        """Explain an arithmetic expression step by step."""
        return f'Explain step by step how to compute {expression}.'

    @server.resource('calculator://precision', mime_type='application/json')
    def precision() -> dict:
        """The precision of the numbers of the calculator."""
        return {'digits': 15}

    is_ok(
        dispatch(server, request('tools/call', name='add', arguments={'a': 1, 'b': 2}))['result']['structuredContent'],
        3,
        'add',
    )
    is_ok(
        dispatch(server, request('prompts/get', name='explain', arguments={'expression': '1 + 2'}))['result'][
            'messages'
        ][0]['content']['text'],
        'Explain step by step how to compute 1 + 2.',
        'explain',
    )
    is_ok(
        dispatch(server, request('resources/read', uri='calculator://precision'))['result']['contents'][0]['text'],
        '{"digits":15}',
        'precision',
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
    t = Pyjo.MCP.Test.new(app)
    t.discover_ok().status_is(200).result_is('/instructions', 'Arithmetic for the model.')
    t.discover_ok(headers={'Origin': 'https://evil.com'}).status_is(403)
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

with subtest('Context cancelled'):
    context = Pyjo.MCP.Server.Context.new()
    got = []

    @context.on('cancelled')
    def cancelled(context):
        got.append(context.is_cancelled)

    id = Pyjo.IOLoop.recurring(1, lambda: ...)
    context.on('cancelled', lambda context: Pyjo.IOLoop.remove(id))
    context.cancel()
    is_deeply_ok(got, [True], 'cancelled')

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
    id = context.id
    is_ok(id, 1, 'id')
    level = context.log_level
    is_ok(level, None, 'level')
    meta = context.meta
    is_deeply_ok(meta, META, 'meta')
    token = context.progress_token
    is_ok(token, None, 'token')
    version = context.protocol_version
    is_ok(version, '2026-07-28', 'version')
    status = context.status
    is_ok(status, None, 'status')
    cb = context.stream
    is_ok(cb, None, 'stream')
    sent = []
    context.stream = lambda notification: sent.append(notification)
    context.notify('notifications/message', {'level': 'info', 'data': 'Hello'})
    is_deeply_ok(
        sent, [{'jsonrpc': '2.0', 'method': 'notifications/message', 'params': {'level': 'info', 'data': 'Hello'}}]
    )
    context = Pyjo.MCP.Server.Context.new()
    meta = {**META, 'progressToken': 'p1', 'io.modelcontextprotocol/logLevel': 'warning'}
    dispatch(server, {**request('tools/list'), 'params': {'_meta': meta}}, context)
    is_deeply_ok((context.log_level, context.progress_token), ('warning', 'p1'), 'from the _meta')

with subtest('Context.is_cancelled'):
    context = Pyjo.MCP.Server.Context.new()
    boolean = context.is_cancelled
    ok(not boolean, 'not cancelled')

with subtest('Context.cancel'):
    context = context.cancel()
    ok(context.is_cancelled, 'cancelled')
    is_ok(context.notify('notifications/message'), False, 'no notification of an abandoned request')

with subtest('Context.notify'):
    context = Pyjo.MCP.Server.Context.new()
    is_ok(context.notify('notifications/message', {'level': 'info', 'data': 'Hello'}), False, 'no stream')
    sent = []
    context.stream = sent.append
    boolean = context.notify('notifications/message', {'level': 'info', 'data': 'Hello'})
    ok(boolean, 'sent')
    is_deeply_ok(sent[0]['params'], {'level': 'info', 'data': 'Hello'}, 'notification')

with subtest('Context.notify_log'):
    is_ok(context.notify_log('info', 'Fetching the forecast'), False, 'no level')
    context.log_level = 'info'
    boolean = context.notify_log('info', 'Fetching the forecast')
    ok(boolean, 'sent')
    boolean = context.notify_log('error', {'code': 23})
    ok(boolean, 'sent')
    is_ok(context.notify_log('debug', 'Detail'), False, 'below the level')
    is_deeply_ok(
        [message['params'] for message in sent[1:]],
        [{'level': 'info', 'data': 'Fetching the forecast'}, {'level': 'error', 'data': {'code': 23}}],
        'log messages',
    )

with subtest('Context.notify_progress'):
    is_ok(context.notify_progress(1), False, 'no token')
    context.progress_token = 7
    boolean = context.notify_progress(1)
    ok(boolean, 'sent')
    boolean = context.notify_progress(1, 3, 'Fetched the first page')
    is_deeply_ok(
        [message['params'] for message in sent[3:]],
        [
            {'progressToken': 7, 'progress': 1},
            {'progressToken': 7, 'progress': 1, 'total': 3, 'message': 'Fetched the first page'},
        ],
        'progress',
    )

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
    interval = server.heartbeat
    is_ok(interval, 30, 'interval')
    server.heartbeat = 15
    instructions = server.instructions
    server.instructions = 'Arithmetic for the model.'
    boolean = server.list_changed
    is_ok(boolean, False, 'list_changed')
    server.list_changed = True
    name = server.name
    is_ok(name, 'calculator', 'name')
    server.name = 'calculator'
    prompts = server.prompts
    is_deeply_ok(prompts, [], 'prompts')
    resources = server.resources
    is_deeply_ok(resources, [], 'resources')
    boolean = server.subscribe
    is_ok(boolean, False, 'subscribe')
    server.subscribe = True
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
    server.tool('add', lambda a, b: a + b)
    server.resource('file:///project/README.md', lambda: '# Project')
    is_deeply_ok(
        dispatch(server, request('server/discover'))['result']['capabilities'],
        {'tools': {'listChanged': True}, 'resources': {'listChanged': True, 'subscribe': True}},
        'capabilities',
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


def subscription(server, notifications):
    # A subscription of a context of its own, whose notifications the test gets
    context = Pyjo.MCP.Server.Context.new()
    sent = []
    context.stream = sent.append
    server.dispatch_p(request('subscriptions/listen', notifications=notifications), context)
    return context, sent


with subtest('notify_list_changed'):
    server = Pyjo.MCP.Server.new()
    server.tool('add', lambda a, b: a + b)
    context, sent = subscription(server, {'toolsListChanged': True})
    count = server.notify_list_changed('tools')
    is_ok(count, 1, 'count')
    count = server.notify_list_changed('prompts')
    is_ok(count, 0, 'count')
    count = server.notify_list_changed('resources')
    is_ok(count, 0, 'count')

    server.tools = [tool for tool in server.tools if tool.name != 'add']
    server.notify_list_changed('tools')
    is_deeply_ok(
        [message['method'] for message in sent],
        [
            'notifications/subscriptions/acknowledged',
            'notifications/tools/list_changed',
            'notifications/tools/list_changed',
        ],
        'notifications',
    )
    context.cancel()

with subtest('notify_resource_updated'):
    server = Pyjo.MCP.Server.new()
    context, sent = subscription(server, {'resourceSubscriptions': ['file:///project/README.md']})
    count = server.notify_resource_updated('file:///project/README.md')
    is_ok(count, 1, 'count')
    is_deeply_ok(
        sent[1]['params'],
        {'_meta': {'io.modelcontextprotocol/subscriptionId': 1}, 'uri': 'file:///project/README.md'},
        'notification',
    )
    context.cancel()

with subtest('prompt'):
    server = Pyjo.MCP.Server.new()
    cb = server.prompt('review', lambda code: f'Review this code:\n{code}')
    is_ok(cb('x'), 'Review this code:\nx', 'cb')
    cb = server.prompt('review', lambda context, code: ..., context=True)

    @server.prompt
    def review(code: str, language: str = 'Python') -> str:
        """Review a piece of code."""
        return f'Review this {language} code:\n{code}'

    @server.prompt('code_review', title='Code review')
    def code_review(code: str) -> str:
        """Review a piece of code."""
        return f'Review this code:\n{code}'

    is_deeply_ok([prompt.name for prompt in server.prompts], ['review', 'review', 'review', 'code_review'], 'prompts')
    ok(server.prompts[1].context, 'context')
    is_ok(server.prompts[3].title, 'Code review', 'title')

with subtest('resource'):
    server = Pyjo.MCP.Server.new()
    cb = server.resource('file:///project/README.md', lambda: '# Project', mime_type='text/markdown')
    is_ok(cb(), '# Project', 'cb')
    cb = server.resource('config://app', lambda context: ..., context=True)

    @server.resource('file:///project/README.md', mime_type='text/markdown')
    def readme() -> str:
        """The documentation of the project."""
        return '# Project'

    is_deeply_ok(
        [(resource.uri, resource.name) for resource in server.resources],
        [
            ('file:///project/README.md', '<lambda>'),
            ('config://app', '<lambda>'),
            ('file:///project/README.md', 'readme'),
        ],
        'resources',
    )
    ok(server.resources[1].context, 'context')
    is_ok(server.resources[2].description, 'The documentation of the project.', 'description')

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
