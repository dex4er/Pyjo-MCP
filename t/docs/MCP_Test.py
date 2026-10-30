import Pyjo.File
import Pyjo.MCP.Client
import Pyjo.MCP.Server
import Pyjoyment

from Pyjo.File import curfile
from Pyjo.Test import *

import contextlib
import re


# The calculator of the examples, and a server of the other examples
EXAMPLES = curfile().dirname().dirname().sibling('examples')

server = Pyjo.MCP.Server.new(name='examples')


@server.tool
def greet(name: str) -> str:
    """Greet somebody by name."""
    return f'Hello, {name}!'


@server.tool
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


@server.tool(context=True)
def count(context, to: int) -> int:
    """Count to a number."""
    for number in range(1, to + 1):
        context.notify_progress(number, to)
    return to


server.tool('weather', lambda: {'temperature': 21.5}, input_schema={'type': 'object'}, output_schema={'type': 'object'})
server.tool(
    'execute_sql',
    lambda region, query: f'{region}: {query}',
    input_schema={
        'type': 'object',
        'properties': {'region': {'type': 'string', 'x-mcp-header': 'Region'}, 'query': {'type': 'string'}},
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


app = Pyjoyment.new()
app.log.level = 'fatal'
app.routes.any('/mcp').to(cb=server.to_action())
app.routes.any('/api/mcp').to(cb=server.to_action())


@contextlib.contextmanager
def recording(t):
    # The calls of the handler in the block, which pass, for the examples whose values are only examples
    handler, calls = t.handler, []
    t.handler = lambda name, *args: calls.append((name, *args)) or True
    try:
        yield calls
    finally:
        t.handler = handler


with subtest('Synopsis'):
    # Instead of curfile().dirname().sibling('calculator.py'), the calculator of the examples
    from Pyjo.MCP.Test import Test

    t = Test(EXAMPLES.child('calculator.py'))

    t.discover_ok().status_is(200).result_is('/capabilities', {'tools': {}})
    t.list_tools_ok().status_is(200).tool_exists('divide')
    t.call_ok('divide', a=7, b=2).status_is(200).structured_content_is(3.5).is_error_is(False)
    t.call_ok('divide', {'a': 1, 'b': 0}).is_error_is(True).text_content_is('Division by zero')
    t.call_ok('power').error_code_is(-32602).error_message_is('Unknown tool: power')

    # Or import the module, as in Google Python Style Guide

    import Pyjo.MCP.Test

    t = Pyjo.MCP.Test.new(EXAMPLES.child('calculator.py'))

    # A request without its header Mcp-Name
    params = {'name': 'add', 'arguments': {'a': 1, 'b': 2}}
    t.mcp_ok('tools/call', params, headers={'Mcp-Name': None}).status_is(400)
    t.error_message_is('Header mismatch: Missing Mcp-Name header')
    t.ua.close()

with subtest('new'):
    t = Pyjo.MCP.Test.new()
    is_ok(t.response, None, 'no response')
    t = Pyjo.MCP.Test.new(Pyjo.File.new(EXAMPLES.child('calculator.py').to_str()))
    t.call_ok('add', a=1, b=2).structured_content_is(3)
    t.ua.close()
    t = Pyjo.MCP.Test.new(app, {'foo': 'bar'})
    is_ok(t.app.config('foo'), 'bar', 'configuration')

with subtest('notifications'):
    t.discover_ok()
    notifications = t.notifications
    is_deeply_ok(notifications, [], 'no notifications')

    params = {'name': 'count', 'arguments': {'to': 3}}
    t.mcp_ok('tools/call', params, meta={'progressToken': 'count-1'}).status_is(200)
    is_ok(t.notifications[0]['method'], 'notifications/progress', 'progress')
    is_ok(len(t.notifications), 3, 'of the last request')

with subtest('response'):
    t.discover_ok()
    response = t.response
    is_ok(response['id'], t.client._id, 'response')
    t.response = {'jsonrpc': '2.0', 'id': 1, 'result': {}}
    t.result_is({})

    # More specific tests
    t.call_ok('greet', name='Pyjo')
    is_ok(t.response['result']['content'][0]['type'], 'text', 'right type')

with subtest('client'):
    client = t.client
    isa_ok(client, Pyjo.MCP.Client.object, 'client')
    t.client = Pyjo.MCP.Client.new('/api/mcp')
    t.discover_ok().status_is(200)

    # Another endpoint, client and capabilities
    t.client.url = '/api/mcp'
    t.client.name = 'ExampleClient'
    t.client.capabilities = {'elicitation': {}}
    t.discover_ok().status_is(200)
    is_ok(t.tx.req.url.path.to_str(), '/api/mcp', 'endpoint')
    t.ua.close()

with subtest('call_ok'):
    t = Pyjo.MCP.Test.new(app)
    t = t.call_ok('greet')
    t.is_error_is(True)
    t = t.call_ok('greet', name='Pyjo')
    t.text_content_is('Hello, Pyjo!')
    t = t.call_ok('greet', {'name': 'Pyjo'})
    t.text_content_is('Hello, Pyjo!')

    t.list_tools_ok().call_ok('execute_sql', region='eu', query='SELECT 1').status_is(200)
    is_ok(t.tx.req.headers.header('Mcp-Param-Region'), 'eu', 'header of the argument')

with subtest('discover_ok'):
    t = t.discover_ok()
    t.status_is(200)
    t = t.discover_ok(headers={'MCP-Protocol-Version': '2025-11-25'})
    t.status_is(400)

with subtest('error_code_is'):
    t.call_ok('power')
    t = t.error_code_is(-32602)
    t = t.error_code_is(-32602, 'invalid params')

with subtest('error_is'):
    t.mcp_ok('tools/foo')
    t = t.error_is({'code': -32601, 'message': 'Method not found'})
    t.mcp_ok('tools/list', meta={'io.modelcontextprotocol/protocolVersion': '1900-01-01'})
    t = t.error_is('/data/supported', ['2026-07-28'])
    t.mcp_ok('tools/foo')
    t = t.error_is('/code', -32601, 'right code')

with subtest('error_message_is'):
    t.call_ok('power')
    t = t.error_message_is('Unknown tool: power')
    t = t.error_message_is('Unknown tool: power', 'right message')

with subtest('error_message_like'):
    t = t.error_message_like(re.compile(r'^Unknown tool'))
    t = t.error_message_like(re.compile(r'^Unknown tool'), 'right message')

with subtest('get_prompt_ok'):
    t = t.get_prompt_ok('review')
    t.error_message_is('Missing required argument: code')
    t = t.get_prompt_ok('review', code='x = 1')
    t.text_content_is('Review this Python code:\nx = 1')
    t = t.get_prompt_ok('review', {'code': 'x = 1'})
    t.text_content_is('Review this Python code:\nx = 1')

    t.get_prompt_ok('review', code='x = 1').status_is(200).text_content_like(r'x = 1')

with subtest('is_error_is'):
    t.call_ok('add', a=1, b=2)
    t = t.is_error_is(False)
    t.call_ok('add', a=1)
    t = t.is_error_is(True, 'error of the tool')

with subtest('list_prompts_ok'):
    t = t.list_prompts_ok()
    t.status_is(200).prompt_exists('review')

with subtest('list_resources_ok'):
    t = t.list_resources_ok()
    t.status_is(200).resource_exists('file:///project/README.md')

with subtest('list_tools_ok'):
    t = t.list_tools_ok()
    t.status_is(200).tool_exists('greet')

with subtest('listen_ok'):
    t = t.listen_ok({'toolsListChanged': True})
    t.notification_ok().notification_is('/params/notifications', {'toolsListChanged': True})
    t.sse_finish_ok()
    t = t.listen_ok({'resourceSubscriptions': ['file:///project/README.md']})
    t.notification_ok().notification_is('/params/notifications/resourceSubscriptions', ['file:///project/README.md'])
    t.sse_finish_ok()

    t.listen_ok({'toolsListChanged': True})
    t.notification_ok().notification_is('/method', 'notifications/subscriptions/acknowledged')
    server.notify_list_changed('tools')
    t.notification_ok().notification_is('/method', 'notifications/tools/list_changed')
    t.sse_finish_ok()

with subtest('mcp_ok'):
    t = t.mcp_ok('tools/list')
    t.status_is(200)
    t = t.mcp_ok('tools/call', {'name': 'add', 'arguments': {'a': 1, 'b': 2}})
    t.structured_content_is(3)
    t = t.mcp_ok('tools/call', {'name': 'add', 'arguments': {}}, headers={'Mcp-Name': 'foo'})
    t.status_is(400)
    t = t.mcp_ok('server/discover', id='discover-1', meta={'io.modelcontextprotocol/clientInfo': None})
    t.status_is(200).response_is('/id', 'discover-1')

    # A revision of the specification that the server does not support
    t.mcp_ok('tools/list', meta={'io.modelcontextprotocol/protocolVersion': '1900-01-01'}).status_is(400)
    t.error_code_is(-32022)

with subtest('notification_is'):
    t.listen_ok({'toolsListChanged': True, 'resourceSubscriptions': ['file:///project/README.md']}).notification_ok()
    server.notify_list_changed('tools')
    server.notify_resource_updated('file:///project/README.md')
    t.notification_ok()
    meta = {'io.modelcontextprotocol/subscriptionId': t.client._id}
    # The _meta of the message is left out of the example
    with recording(t) as calls:
        t = t.notification_is({'jsonrpc': '2.0', 'method': 'notifications/tools/list_changed', 'params': {}})
    is_ok(calls[0][1]['method'], 'notifications/tools/list_changed', 'whole message')
    t.notification_is({'jsonrpc': '2.0', 'method': 'notifications/tools/list_changed', 'params': {'_meta': meta}})
    t.notification_ok()
    t = t.notification_is('/method', 'notifications/resources/updated')
    t = t.notification_is('/params/uri', 'file:///project/README.md', 'right resource')
    t.sse_finish_ok()

with subtest('notification_ok'):
    t.listen_ok({'toolsListChanged': True})
    t = t.notification_ok()
    server.notify_list_changed('tools')
    t = t.notification_ok('got a notification')
    t.sse_finish_ok()

with subtest('prompt_exists'):
    t.list_prompts_ok()
    t = t.prompt_exists('review')
    t = t.prompt_exists('review', 'has a review')

with subtest('prompt_exists_not'):
    t = t.prompt_exists_not('summary')
    t = t.prompt_exists_not('summary', 'no summary')

with subtest('prompt_is'):
    with recording(t) as calls:
        t = t.prompt_is('review', {'name': 'review', 'arguments': []})
    is_ok(calls[0][1]['name'], 'review', 'prompt')
    t = t.prompt_is('review', '/arguments/0/name', 'code')
    t = t.prompt_is('review', '/arguments/0/required', True, 'code required')

with subtest('read_resource_ok'):
    t = t.read_resource_ok('file:///project/README.md')
    t.text_content_is('# Project')

    t.read_resource_ok('file:///project/README.md').status_is(200).text_content_like(r'^# ')

with subtest('resource_exists'):
    t.list_resources_ok()
    t = t.resource_exists('file:///project/README.md')
    t = t.resource_exists('file:///project/README.md', 'has a README')

with subtest('resource_exists_not'):
    t = t.resource_exists_not('file:///etc/passwd')
    t = t.resource_exists_not('file:///etc/passwd', 'no secrets')

with subtest('resource_is'):
    with recording(t) as calls:
        t = t.resource_is('file:///project/README.md', {'uri': 'file:///project/README.md', 'name': 'readme'})
    is_ok(calls[0][1]['mimeType'], 'text/markdown', 'resource')
    t = t.resource_is('file:///project/README.md', '/mimeType', 'text/markdown')
    t = t.resource_is('file:///project/README.md', '/name', 'readme', 'right name')

with subtest('response_is'):
    t.discover_ok()
    with recording(t) as calls:
        t = t.response_is({'jsonrpc': '2.0', 'id': 1, 'result': {}})
        t = t.response_is('/id', 1)
        t = t.response_is('/id', 1, 'right id')
    is_ok(calls[0][1]['id'], t.response['id'], 'response')
    is_deeply_ok(
        [call[1:] for call in calls[1:]],
        [(t.response['id'], 1, 'exact match for response "/id"'), (t.response['id'], 1, 'right id')],
    )

with subtest('result_is'):
    t.list_tools_ok()
    with recording(t) as calls:
        t = t.result_is({'resultType': 'complete', 'tools': []})
    is_ok(len(calls[0][1]['tools']), 5, 'tools')
    t.call_ok('greet', name='Pyjo')
    t = t.result_is('/content/0/text', 'Hello, Pyjo!')
    t = t.result_is('/content/0/text', 'Hello, Pyjo!', 'right text')

with subtest('structured_content_is'):
    t.call_ok('weather')
    with recording(t) as calls:
        t = t.structured_content_is(3.5)
    is_deeply_ok(calls[0][1], {'temperature': 21.5}, 'structured content')
    t = t.structured_content_is('/temperature', 21.5)
    t = t.structured_content_is('/temperature', 21.5, 'right temperature')

with subtest('text_content_is'):
    t.call_ok('greet', name='Pyjo')
    t = t.text_content_is('Hello, Pyjo!')
    t = t.text_content_is('Hello, Pyjo!', 'right text')

    t.get_prompt_ok('review', code='x = 1').text_content_is('Review this Python code:\nx = 1')
    t.read_resource_ok('file:///project/README.md').text_content_is('# Project')

with subtest('text_content_like'):
    t.call_ok('greet')
    t = t.text_content_like(re.compile(r'/name: Missing property'))
    t = t.text_content_like(re.compile(r'/name: Missing property'), 'right error')

with subtest('tool_exists'):
    t.list_tools_ok()
    t = t.tool_exists('greet')
    t = t.tool_exists('greet', 'has a greeting')

with subtest('tool_exists_not'):
    t = t.tool_exists_not('power')
    t = t.tool_exists_not('power', 'no power')

with subtest('tool_is'):
    with recording(t) as calls:
        t = t.tool_is('greet', {'name': 'greet', 'inputSchema': {'type': 'object'}})
    is_ok(calls[0][1]['name'], 'greet', 'tool')
    t = t.tool_is('greet', '/description', 'Greet somebody by name.')
    t = t.tool_is('greet', '/inputSchema/required', ['name'], 'right required arguments')
    t.ua.close()

done_testing()
