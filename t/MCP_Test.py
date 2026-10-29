import Pyjo.JSON
import Pyjo.MCP.Client
import Pyjo.MCP.Server
import Pyjo.MCP.Test
import Pyjo.MCP.Tool
import Pyjo.SSE
import Pyjo.Test.Pyjo
import Pyjoyment

from Pyjo.Test import *

import re


# The assertions of the servers of MCP, against the server of the distribution, which checks the headers of MCP

server = Pyjo.MCP.Server.new(name='ExampleServer', version='1.0.0')


@server.tool
def greet(name: str) -> str:
    """Greet somebody by name."""
    return f'Hello, {name}!'


@server.tool
def divide(a: float, b: float) -> float:
    """Divide."""
    if b == 0:
        raise Pyjo.MCP.Tool.Error.new('Division by zero')
    return a / b


@server.tool(context=True)
def whoami(context) -> str:
    """Who calls."""
    return f'{context.client_info.get("name")} {context.client_capabilities}'


server.tool(
    'execute_sql',
    lambda region, query: f'{region}: {query}',
    input_schema={
        'type': 'object',
        'properties': {'region': {'type': 'string', 'x-mcp-header': 'Region'}, 'query': {'type': 'string'}},
        'required': ['region', 'query'],
    },
)


def application(action, path='/mcp'):
    app = Pyjoyment.new()
    app.log.level = 'fatal'
    app.routes.any(path).to(cb=action)
    return app


app = application(server.to_action())

# The headers of the requests, as the server gets them
sent = []
app.hook('before_dispatch', lambda c: sent.append(c.req.headers.to_dict()))


def recorder(t):
    # The calls of the handler, which pass, instead of the functions of Pyjo.Test
    calls = []
    t.handler = lambda name, *args: calls.append((name, *args)) or True
    return calls


with subtest('Construction'):
    t = Pyjo.MCP.Test.new(app)
    isa_ok(t, Pyjo.Test.Pyjo.object, 'Pyjo.Test.Pyjo')
    is_ok(t.response, None, 'no response yet')
    isa_ok(t.client, Pyjo.MCP.Client.object, 'client')
    is_ok(t.client.url, '/mcp', 'endpoint')
    is_ok(t.client.ua, t.ua, 'user agent of the test')
    client = Pyjo.MCP.Client.new('/other')
    t.client = client
    is_ok(t.client, client, 'client')
    t.ua.close()

with subtest('Discovery'):
    t = Pyjo.MCP.Test.new(app)
    t.discover_ok().status_is(200).result_is('/capabilities', {'tools': {}})
    t.result_is('/supportedVersions', ['2026-07-28']).response_is('/id', 1).response_is('/jsonrpc', '2.0')
    is_ok(sent[-1]['Mcp-Method'], 'server/discover', 'Mcp-Method')
    is_ok(sent[-1]['MCP-Protocol-Version'], '2026-07-28', 'MCP-Protocol-Version')
    is_ok(t.response['result']['resultType'], 'complete', 'response')
    t.ua.close()

with subtest('Tools'):
    t = Pyjo.MCP.Test.new(app)
    t.list_tools_ok().status_is(200).tool_exists('greet').tool_exists_not('power')
    t.tool_is('greet', '/description', 'Greet somebody by name.')
    t.tool_is('greet', '/inputSchema/required', ['name'])
    t.tool_is('power', None)
    is_deeply_ok(list(t.client.tools), ['greet', 'divide', 'whoami', 'execute_sql'], 'tools of the client')
    t.ua.close()

with subtest('Calls'):
    t = Pyjo.MCP.Test.new(app)
    t.call_ok('greet', name='Pyjo').status_is(200).text_content_is('Hello, Pyjo!').is_error_is(False)
    is_ok(sent[-1]['Mcp-Name'], 'greet', 'Mcp-Name')
    t.call_ok('greet', {'name': 'Pyjo'}).text_content_like(re.compile(r'^Hello'))
    t.call_ok('greet', {'name': 'x'}, name='Pyjo').text_content_is('Hello, Pyjo!')
    t.call_ok('divide', a=7, b=2).structured_content_is(3.5).result_is('/content/0/text', '3.5')
    t.call_ok('divide', a=1, b=0).is_error_is(True).text_content_is('Division by zero')
    t.call_ok('greet').status_is(200).is_error_is(True).text_content_like(r'/name: Missing property')
    t.call_ok('power').status_is(200).error_code_is(-32602).error_message_is('Unknown tool: power')
    t.error_is({'code': -32602, 'message': 'Unknown tool: power'}).error_is('/code', -32602)
    t.error_message_like(re.compile(r'^Unknown tool'))
    t.ua.close()

with subtest('A tool with an argument name'):
    named = Pyjo.MCP.Server.new()
    named.tool(
        'rename',
        lambda tool, name, arguments: f'{tool} {name} {arguments}',
        input_schema={
            'type': 'object',
            'properties': {'tool': {'type': 'string'}, 'name': {'type': 'string'}, 'arguments': {'type': 'string'}},
        },
    )
    t = Pyjo.MCP.Test.new(application(named.to_action()))
    t.call_ok('rename', tool='a', name='b', arguments='c').text_content_is('a b c')
    t.call_ok('rename', {'tool': 'a', 'name': 'b', 'arguments': 'c'}).text_content_is('a b c')
    t.ua.close()

with subtest('Headers of the arguments'):
    t = Pyjo.MCP.Test.new(app)
    t.call_ok('execute_sql', region='eu', query='SELECT 1').status_is(400)
    t.error_message_is('Header mismatch: Missing Mcp-Param-Region header')
    t.list_tools_ok().call_ok('execute_sql', region='eu', query='SELECT 1').status_is(200)
    t.text_content_is('eu: SELECT 1')
    is_ok(sent[-1]['Mcp-Param-Region'], 'eu', 'Mcp-Param-Region')
    t.call_ok('execute_sql', region='Kraków', query='SELECT 1').text_content_is('Kraków: SELECT 1')
    is_ok(sent[-1]['Mcp-Param-Region'], '=?base64?S3Jha8Ozdw==?=', 'Base64')
    t.ua.close()

with subtest('Requests that a client must not send'):
    t = Pyjo.MCP.Test.new(app)
    params = {'name': 'greet', 'arguments': {'name': 'Pyjo'}}
    t.mcp_ok('tools/call', params, headers={'Mcp-Name': None}).status_is(400)
    t.error_code_is(-32020).error_message_is('Header mismatch: Missing Mcp-Name header')
    t.mcp_ok('tools/call', params, headers={'Mcp-Name': 'foo'}).status_is(400)
    t.error_message_is("Header mismatch: Mcp-Name header value 'foo' does not match body value 'greet'")
    t.mcp_ok('tools/list', headers={'Mcp-Method': 'tools/call'}).status_is(400)
    t.mcp_ok('tools/list', meta={'io.modelcontextprotocol/protocolVersion': '1900-01-01'}).status_is(400)
    t.error_code_is(-32022).error_is('/data', {'supported': ['2026-07-28'], 'requested': '1900-01-01'})
    is_ok(sent[-1]['MCP-Protocol-Version'], '1900-01-01', 'header made from the body')
    t.mcp_ok('tools/list', meta={'io.modelcontextprotocol/clientCapabilities': None}).status_is(400)
    t.error_message_is('Missing client capabilities')
    t.discover_ok(headers={'MCP-Protocol-Version': None}).status_is(400)
    t.list_tools_ok(meta={'io.modelcontextprotocol/protocolVersion': None}).status_is(400)
    t.error_message_is('Missing protocol version')
    t.mcp_ok('server/discover', id='discover-1').status_is(200).response_is('/id', 'discover-1')
    t.mcp_ok('tools/foo').status_is(404).error_is({'code': -32601, 'message': 'Method not found'})
    t.mcp_ok('tools/call', {'name': 'whoami'}, headers={'X-Test': 'Test'}).status_is(200)
    is_ok(sent[-1]['X-Test'], 'Test', 'header of its own')
    t.ua.close()

with subtest('Client'):
    t = Pyjo.MCP.Test.new(application(server.to_action(), '/api/mcp'))
    t.client.url = '/api/mcp'
    t.client.name = 'ExampleClient'
    t.client.capabilities = {'elicitation': {}}
    t.call_ok('whoami').text_content_is("ExampleClient {'elicitation': {}}")
    t.ua.close()

with subtest('Response in a stream of events'):

    def events(c):
        def respond(response):
            notification = {'jsonrpc': '2.0', 'method': 'notifications/progress', 'params': {'progress': 1}}
            c.res.headers.content_type = 'text/event-stream'
            data = b''.join(Pyjo.SSE.build_event({'text': Pyjo.JSON.to_json(m)}) for m in (notification, response))
            c.render(data=data)

        c.render_later()
        return server.dispatch_p(c.req.json()).then(respond)

    t = Pyjo.MCP.Test.new(application(events))
    t.call_ok('greet', name='Pyjo').status_is(200).header_is('Content-Type', 'text/event-stream')
    t.text_content_is('Hello, Pyjo!').response_is('/id', t.client._id)
    t.ua.close()

with subtest('No response of JSON-RPC'):
    t = Pyjo.MCP.Test.new(application(lambda c: c.render(text='Not MCP', format='txt', status=400)))
    t.discover_ok().status_is(400).content_is('Not MCP')
    is_ok(t.response, None, 'no response')
    t.ua.close()
    t = Pyjo.MCP.Test.new(application(lambda c: c.rendered(202)))
    t.discover_ok().status_is(202)
    is_ok(t.response, None, 'accepted without a response')
    t.ua.close()

with subtest('Descriptions'):
    t = Pyjo.MCP.Test.new(app)
    t.call_ok('divide', a=1, b=0)
    calls = recorder(t)
    t.is_error_is(True).text_content_is('Division by zero').text_content_like(r'zero')
    t.result_is('/isError', True).result_is({}).response_is('/id', 1).structured_content_is(None)
    t.error_code_is(1).error_message_is('x').error_message_like(r'x').error_is('/code', 1)
    t.tool_exists('greet').tool_exists_not('greet').tool_is('greet', '/name', 'greet', 'right name')
    is_deeply_ok(
        [call[0 :: len(call) - 1] for call in calls],
        [
            ('is', 'isError is true'),
            ('is', 'exact match for text content'),
            ('like', 'similar match for text content'),
            ('is_deeply', 'exact match for result "/isError"'),
            ('is_deeply', 'exact match for result ""'),
            ('is_deeply', 'exact match for response "/id"'),
            ('is_deeply', 'exact match for structured content ""'),
            ('is', 'error code is 1'),
            ('is', 'exact match for error message'),
            ('like', 'similar match for error message'),
            ('is_deeply', 'exact match for error "/code"'),
            ('ok', 'has tool "greet"'),
            ('ok', 'has no tool "greet"'),
            ('is_deeply', 'right name'),
        ],
        'descriptions',
    )
    is_deeply_ok(
        [call[1:-1] for call in calls[:4]],
        [(True, True), ('Division by zero', 'Division by zero'), ('Division by zero', 'zero'), (True, True)],
        'values',
    )
    is_deeply_ok([call[1:-1] for call in calls[7:9]], [(None, 1), (None, 'x')], 'no error')
    is_deeply_ok([call[1] for call in calls[11:]], [False, True, None], 'no tools')
    t.ua.close()

done_testing()
