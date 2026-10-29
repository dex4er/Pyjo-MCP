import Pyjo.EventEmitter
import Pyjo.Log
import Pyjo.MCP
import Pyjo.MCP.Server
import Pyjo.MCP.Test
import Pyjo.MCP.Tool
import Pyjo.Promise
import Pyjoyment

from Pyjo.Test import *

import base64
import json
import re


# The server of MCP of the revision 2026-07-28 over Streamable HTTP, with the examples of its specification

META = {
    'io.modelcontextprotocol/protocolVersion': '2026-07-28',
    'io.modelcontextprotocol/clientInfo': {'name': 'ExampleClient', 'version': '1.0.0'},
    'io.modelcontextprotocol/clientCapabilities': {},
}
SERVER_INFO = {'io.modelcontextprotocol/serverInfo': {'name': 'ExampleServer', 'version': '1.0.0'}}

server = Pyjo.MCP.Server.new(
    name='ExampleServer', version='1.0.0', instructions='This server provides weather and resource utilities.'
)
exceptions = []
server.on('exception', lambda server, e, context: exceptions.append(e))


@server.tool(title='Weather Information Provider')
def get_weather(location: str) -> str:
    """Get current weather information for a location.

    :param location: City name or zip code
    """
    return f'Current weather in {location}:\nTemperature: 72°F\nConditions: Partly cloudy'


@server.tool
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


@server.tool
def later(value: str) -> str:
    """Answer later."""
    return Pyjo.Promise.timer(0.01, value)


@server.tool
async def twice(value: int) -> int:
    """Answer twice later."""
    await Pyjo.Promise.timer(0.01)
    return value * 2


@server.tool
def book(date: str) -> str:
    """Book a flight."""
    raise Pyjo.MCP.Tool.Error.new('Invalid departure date: must be in the future.')


@server.tool
def fails() -> None:
    """Fail."""
    raise ValueError('Secret')


@server.tool(context=True)
def whoami(context) -> str:
    """Who calls."""
    return f'{context.client_info.get("name")} {context.protocol_version} {context.controller.req.headers.header("X-Test")}'


@server.tool(
    'execute_sql',
    description='Execute SQL on Google Cloud Spanner',
    input_schema={
        'type': 'object',
        'properties': {
            'region': {'type': 'string', 'description': 'The region to execute the query in', 'x-mcp-header': 'Region'},
            'limit': {'type': 'integer', 'x-mcp-header': 'Limit'},
            'dry': {'type': 'boolean', 'x-mcp-header': 'Dry'},
            'query': {'type': 'string', 'description': 'The SQL query to execute'},
        },
        'required': ['region', 'query'],
    },
)
def execute_sql(region, query, limit=None, dry=None):
    return f'{region}: {query}'


app = Pyjoyment.new()
app.log.level = 'error'
app.log.unsubscribe('message')
logged = []
app.log.on('message', lambda log, level, *lines: logged.append((level, str(lines[-1]))))
app.routes.any('/mcp').to(cb=server.to_action())
t = Pyjo.MCP.Test.new(app)
t.client.name = 'ExampleClient'

with subtest('Discovery'):
    t.mcp_ok('server/discover', id='discover-1').status_is(200).header_is(
        'Content-Type', 'application/json;charset=UTF-8'
    )
    t.json_is(
        {
            'jsonrpc': '2.0',
            'id': 'discover-1',
            'result': {
                'resultType': 'complete',
                'supportedVersions': ['2026-07-28'],
                'capabilities': {'tools': {}},
                '_meta': SERVER_INFO,
                'instructions': 'This server provides weather and resource utilities.',
                'ttlMs': 0,
                'cacheScope': 'public',
            },
        }
    )
    other = Pyjo.MCP.Server.new()
    other.cache_ttl, other.cache_scope = 3600000, 'private'
    discover = other.dispatch_p({'jsonrpc': '2.0', 'id': 1, 'method': 'server/discover', 'params': {'_meta': META}})
    results = []
    discover.then(results.append).wait()
    is_deeply_ok(
        results[0]['result'],
        {
            'resultType': 'complete',
            'supportedVersions': ['2026-07-28'],
            'capabilities': {},
            '_meta': {'io.modelcontextprotocol/serverInfo': {'name': 'Pyjo.MCP', 'version': '1.0.0'}},
            'ttlMs': 3600000,
            'cacheScope': 'private',
        },
        'server without tools and instructions',
    )

with subtest('Listing tools'):
    t.mcp_ok('tools/list').status_is(200)
    t.json_is('/result/resultType', 'complete').json_is('/result/ttlMs', 0).json_is('/result/cacheScope', 'public')
    t.json_is('/result/_meta', SERVER_INFO).json_hasnt('/result/nextCursor')
    t.json_is(
        '/result/tools/0',
        {
            'name': 'get_weather',
            'title': 'Weather Information Provider',
            'description': 'Get current weather information for a location.',
            'inputSchema': {
                'type': 'object',
                'properties': {'location': {'type': 'string', 'description': 'City name or zip code'}},
                'required': ['location'],
                'additionalProperties': False,
            },
        },
    )
    t.json_is('/result/tools/1/name', 'add').json_is('/result/tools/1/outputSchema', {'type': 'integer'})
    t.json_is('/result/tools/7/name', 'execute_sql')
    t.json_is('/result/tools/7/inputSchema/properties/region/x-mcp-header', 'Region')
    names = [tool['name'] for tool in t.tx.res.json('/result/tools')]
    is_deeply_ok(names, [tool.name for tool in server.tools], 'tools in a deterministic order')
    t.mcp_ok('tools/list', {'cursor': 'next-page-cursor'}).status_is(200)
    t.json_is('/error', {'code': -32602, 'message': 'Invalid cursor'})

with subtest('Calling tools'):
    t.mcp_ok('tools/call', {'name': 'get_weather', 'arguments': {'location': 'New York'}}, id=2).status_is(200)
    t.json_is(
        {
            'jsonrpc': '2.0',
            'id': 2,
            'result': {
                'resultType': 'complete',
                'content': [
                    {
                        'type': 'text',
                        'text': 'Current weather in New York:\nTemperature: 72°F\nConditions: Partly cloudy',
                    }
                ],
                'isError': False,
                '_meta': SERVER_INFO,
            },
        }
    )
    t.mcp_ok('tools/call', {'name': 'add', 'arguments': {'a': 1, 'b': 2}}).status_is(200)
    t.json_is('/result/structuredContent', 3).json_is('/result/content', [{'type': 'text', 'text': '3'}])
    t.json_hasnt('/result/ttlMs')
    t.mcp_ok('tools/call', {'name': 'later', 'arguments': {'value': 'async'}}).status_is(200)
    t.json_is('/result/content/0/text', 'async')
    t.mcp_ok('tools/call', {'name': 'twice', 'arguments': {'value': 21}}).status_is(200)
    t.json_is('/result/structuredContent', 42)
    t.mcp_ok('tools/call', {'name': 'whoami'}, headers={'X-Test': 'Test'}).status_is(200)
    t.json_is('/result/content/0/text', 'ExampleClient 2026-07-28 Test')

with subtest('Tool execution errors'):
    t.mcp_ok('tools/call', {'name': 'book', 'arguments': {'date': '2025-08-08'}}, id=4).status_is(200)
    t.json_is(
        {
            'jsonrpc': '2.0',
            'id': 4,
            'result': {
                'resultType': 'complete',
                'content': [{'type': 'text', 'text': 'Invalid departure date: must be in the future.'}],
                'isError': True,
                '_meta': SERVER_INFO,
            },
        }
    )
    t.mcp_ok('tools/call', {'name': 'add', 'arguments': {'a': 1, 'b': 'x'}}).status_is(200)
    t.json_is('/result/isError', True).json_is(
        '/result/content/0/text', 'Invalid arguments:\n/b: Expected integer - got string.'
    )
    t.mcp_ok('tools/call', {'name': 'add', 'arguments': {'a': 1}}).status_is(200)
    t.json_is('/result/isError', True).json_is('/result/content/0/text', 'Invalid arguments:\n/b: Missing property.')

with subtest('Protocol errors'):
    t.mcp_ok('tools/call', {'name': 'invalid_tool_name', 'arguments': {}}, id=3).status_is(200)
    t.json_is({'jsonrpc': '2.0', 'id': 3, 'error': {'code': -32602, 'message': 'Unknown tool: invalid_tool_name'}})
    t.mcp_ok('tools/call', {'name': 'add', 'arguments': [1, 2]}).status_is(200)
    t.json_is('/error', {'code': -32602, 'message': 'Invalid arguments'})
    t.mcp_ok('tools/foo').status_is(404).json_is('/error', {'code': -32601, 'message': 'Method not found'})
    t.mcp_ok('initialize').status_is(404).json_is('/error/code', -32601)
    is_deeply_ok(exceptions, [], 'no exceptions')
    t.mcp_ok('tools/call', {'name': 'fails'}).status_is(500)
    t.json_is('/error', {'code': -32603, 'message': 'Internal error'}).content_unlike(re.compile(r'Secret'))
    is_ok(len(exceptions), 1, 'exception emitted')
    is_ok(len(logged), 1, 'exception logged')
    is_ok(logged[0][0], 'error', 'right level')
    like_ok(str(logged[0][1]), re.compile(r'^Secret at '), 'right message')

with subtest('Request metadata'):
    headers = {'MCP-Protocol-Version': '2026-07-28', 'Mcp-Method': 'tools/list'}
    t.post_ok('/mcp', headers, json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}).status_is(400).json_is(
        '/error', {'code': -32602, 'message': 'Missing protocol version'}
    )
    meta = {'io.modelcontextprotocol/protocolVersion': None, 'io.modelcontextprotocol/clientInfo': None}
    t.mcp_ok('tools/list', meta=meta).status_is(400).json_is('/error/code', -32602)
    meta = {'io.modelcontextprotocol/clientCapabilities': None, 'io.modelcontextprotocol/clientInfo': None}
    t.mcp_ok('tools/list', meta=meta).status_is(400)
    t.json_is('/error', {'code': -32602, 'message': 'Missing client capabilities'})
    t.mcp_ok('tools/list', id=1, meta={'io.modelcontextprotocol/protocolVersion': '1900-01-01'}).status_is(400)
    t.json_is(
        {
            'jsonrpc': '2.0',
            'id': 1,
            'error': {
                'code': -32022,
                'message': 'Unsupported protocol version',
                'data': {'supported': ['2026-07-28'], 'requested': '1900-01-01'},
            },
        }
    )
    t.mcp_ok('tools/call', {'name': 'whoami'}, meta={'io.modelcontextprotocol/clientInfo': None}).status_is(200)
    t.json_is('/result/content/0/text', 'None 2026-07-28 None', 'without clientInfo')

with subtest('Request headers'):
    t.mcp_ok('tools/list', headers={'MCP-Protocol-Version': None}).status_is(400)
    t.json_is('/error', {'code': -32020, 'message': 'Header mismatch: Missing MCP-Protocol-Version header'})
    t.mcp_ok('tools/list', headers={'MCP-Protocol-Version': '2025-11-25'}).status_is(400)
    message = "Header mismatch: MCP-Protocol-Version header value '2025-11-25' does not match body value '2026-07-28'"
    t.json_is('/error', {'code': -32020, 'message': message})
    t.mcp_ok('tools/list', headers={'Mcp-Method': None}).status_is(400)
    t.json_is('/error/message', 'Header mismatch: Missing Mcp-Method header')
    t.mcp_ok('tools/list', headers={'Mcp-Method': 'tools/call'}).status_is(400)
    t.json_is(
        '/error/message', "Header mismatch: Mcp-Method header value 'tools/call' does not match body value 'tools/list'"
    )
    t.mcp_ok('tools/call', {'name': 'add', 'arguments': {'a': 1, 'b': 2}}, headers={'Mcp-Name': None}).status_is(400)
    t.json_is('/error/message', 'Header mismatch: Missing Mcp-Name header')
    t.mcp_ok('tools/call', {'name': 'add', 'arguments': {'a': 1, 'b': 2}}, headers={'Mcp-Name': 'foo'}).status_is(400)
    t.json_is(
        '/error',
        {'code': -32020, 'message': "Header mismatch: Mcp-Name header value 'foo' does not match body value 'add'"},
    )
    encoded = '=?base64?' + base64.b64encode(b'add').decode() + '?='
    t.mcp_ok('tools/call', {'name': 'add', 'arguments': {'a': 1, 'b': 2}}, headers={'Mcp-Name': encoded}).status_is(200)
    t.json_is('/result/structuredContent', 3)
    t.mcp_ok('tools/call', {'name': 'add', 'arguments': {}}, headers={'Mcp-Name': '=?base64?***?='}).status_is(400)
    t.json_is('/error/message', 'Header mismatch: Invalid Mcp-Name header')

with subtest('Custom headers from tool parameters'):
    arguments = {'region': 'us-west1', 'query': 'SELECT * FROM users'}
    t.mcp_ok('tools/call', {'name': 'execute_sql', 'arguments': arguments}, headers={'Mcp-Param-Region': 'us-west1'})
    t.status_is(200).json_is('/result/content/0/text', 'us-west1: SELECT * FROM users')
    t.mcp_ok('tools/call', {'name': 'execute_sql', 'arguments': arguments}, headers={'Mcp-Param-Region': None})
    t.status_is(400)
    t.json_is('/error/message', 'Header mismatch: Missing Mcp-Param-Region header')
    t.mcp_ok('tools/call', {'name': 'execute_sql', 'arguments': arguments}, headers={'Mcp-Param-Region': 'eu'})
    t.status_is(400).json_is(
        '/error/message', "Header mismatch: Mcp-Param-Region header value 'eu' does not match body value 'us-west1'"
    )
    greeting = {'region': 'Hello, 世界', 'query': 'x'}
    encoded = '=?base64?SGVsbG8sIOS4lueVjA==?='
    t.mcp_ok('tools/call', {'name': 'execute_sql', 'arguments': greeting}, headers={'Mcp-Param-Region': encoded})
    t.status_is(200).json_is('/result/content/0/text', 'Hello, 世界: x')
    headers = {'Mcp-Param-Region': 'us-west1', 'Mcp-Param-Limit': '42.0', 'Mcp-Param-Dry': 'true'}
    arguments = {'region': 'us-west1', 'query': 'q', 'limit': 42, 'dry': True}
    t.mcp_ok('tools/call', {'name': 'execute_sql', 'arguments': arguments}, headers=headers).status_is(200)
    t.mcp_ok(
        'tools/call', {'name': 'execute_sql', 'arguments': arguments}, headers={**headers, 'Mcp-Param-Dry': 'True'}
    )
    t.status_is(400).json_is(
        '/error/message', "Header mismatch: Mcp-Param-Dry header value 'True' does not match body value 'true'"
    )
    arguments = {'region': 'us-west1', 'query': 'q'}
    t.mcp_ok('tools/call', {'name': 'execute_sql', 'arguments': arguments}, headers={**headers})
    t.status_is(400).json_is('/error/message', 'Header mismatch: Unexpected Mcp-Param-Limit header')

with subtest('Transport'):
    t.get_ok('/mcp').status_is(405).header_is('Allow', 'POST').json_is('/error/code', -32600)
    t.delete_ok('/mcp').status_is(405)
    t.post_ok('/mcp', b'{"jsonrpc": "2.0", "method"').status_is(400).json_is('/error/code', -32700)
    t.post_ok('/mcp', json=[]).status_is(400).json_is('/error/code', -32600)
    message = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list', 'params': {'_meta': META}}
    t.post_ok('/mcp', json=[message]).status_is(400).json_is('/error', {'code': -32600, 'message': 'Invalid Request'})
    t.post_ok('/mcp', json={**message, 'id': None}).status_is(400).json_is('/error/code', -32600)
    t.post_ok(
        '/mcp', {'MCP-Protocol-Version': '2026-07-28'}, json={'jsonrpc': '2.0', 'method': 'notifications/cancelled'}
    )
    t.status_is(202).content_is('')
    headers = {
        'MCP-Protocol-Version': '2026-07-28',
        'Mcp-Method': 'tools/list',
        'Mcp-Session-Id': 'abc',
        'Last-Event-ID': '1',
    }
    t.post_ok('/mcp', headers, json=message).status_is(200).header_exists_not('Mcp-Session-Id')

with subtest('Other transports'):
    results = []
    server.dispatch_p(b'{"jsonrpc": "2.0", "id": 1, "method": "server/discover", "params": {"_meta": {}}}').then(
        results.append
    ).wait()
    is_ok(results[0]['error']['code'], -32602, 'context of its own')
    server.dispatch_p('{').then(results.append).wait()
    is_ok(results[1]['error']['code'], -32700, 'parse error')

with subtest('Streams of messages'):
    # A peer of serve, as Pyjo.IOLoop.Messages, whose tool answers once the test settles it, the second request first
    class Peer(Pyjo.EventEmitter.object):
        def __init__(self):
            super().__init__()
            self.closed = False
            self.sent = []

        def close_gracefully(self):
            self.closed = True

        def send(self, message):
            self.sent.append(json.loads(message))
            return self

    streamed = Pyjo.MCP.Server.new(name='ExampleServer')
    contexts = []

    @streamed.tool(context=True)
    def who(context) -> str:
        promise = Pyjo.Promise.new()
        contexts.append((context, promise))
        return promise

    @streamed.tool
    def broken() -> str:
        raise RuntimeError('Broken tool')

    logged = []
    log = Pyjo.Log.new(level='error')
    log.unsubscribe('message').on('message', lambda log, level, *lines: logged.append((level, *lines)))
    peer = Peer()
    client = streamed.serve(peer, log=log)
    for id, name in ((1, 'First'), (2, 'Second')):
        meta = {**META, 'io.modelcontextprotocol/clientInfo': {'name': name, 'version': '1.0.0'}}
        params = {'name': 'who', 'arguments': {}, '_meta': meta}
        peer.emit('message', json.dumps({'jsonrpc': '2.0', 'id': id, 'method': 'tools/call', 'params': params}))
    is_ok(len(contexts), 2, 'requests at the same time')
    ok(contexts[0][0] is not contexts[1][0], 'context of its own for each request')
    ok(contexts[0][0].client is client, 'client of the peer')
    for context, promise in reversed(contexts):
        promise.resolve(context.client_info['name'])
    Pyjo.Promise.timer(0.01).wait()
    is_deeply_ok(
        [(message['id'], message['result']['content'][0]['text']) for message in peer.sent],
        [(2, 'Second'), (1, 'First')],
        'responses in the order they are there',
    )
    message = {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/list', 'params': {'_meta': META}}
    peer.emit('message', json.dumps([message]))
    peer.emit('message', json.dumps({**message, 'id': None}))
    Pyjo.Promise.timer(0.01).wait()
    is_deeply_ok([message['error']['code'] for message in peer.sent[2:]], [-32600, -32600], 'no batch and no null id')
    params = {'name': 'broken', 'arguments': {}, '_meta': META}
    peer.emit('message', json.dumps({'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call', 'params': params}))
    Pyjo.Promise.timer(0.01).wait()
    is_ok(peer.sent[4]['error']['code'], -32603, 'error of the server')
    is_ok(logged[0][0], 'error', 'logged')
    like_ok(str(logged[0][1]), re.compile(r'Broken tool'), 'message of the exception')
    ok(not peer.closed, 'open')
    peer.emit('end')
    ok(peer.closed, 'closed at the end of the input')

done_testing()
