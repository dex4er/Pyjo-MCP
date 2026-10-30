import Pyjo.EventEmitter
import Pyjo.Exception
import Pyjo.IOLoop
import Pyjo.Log
import Pyjo.MCP
import Pyjo.MCP.Client
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

with subtest('Prompts and resources'):
    # A server of its own, with the examples of the specification
    library = Pyjo.MCP.Server.new(name='ExampleServer', version='1.0.0')

    @library.prompt(title='Request Code Review')
    def code_review(code: str) -> str:
        """Asks the LLM to analyze code quality and suggest improvements.

        :param code: The code to review
        """
        return f'Please review this Python code:\n{code}'

    @library.prompt(context=True)
    def greeting(context, name: str = 'World') -> list:
        """Greet with the name of the client."""
        return [
            {'role': 'user', 'content': {'type': 'text', 'text': f'Hello, {name}!'}},
            {'role': 'assistant', 'content': {'type': 'text', 'text': f'Hello from {context.client_info.get("name")}'}},
        ]

    @library.prompt
    def broken_prompt() -> str:
        """Fail."""
        raise ValueError('Secret')

    @library.resource(
        'file:///project/src/main.rs', title='Rust Software Application Main File', mime_type='text/x-rust'
    )
    def main_rs() -> str:
        """Primary application entry point."""
        return 'fn main() {\n    println!("Hello world!");\n}'

    library.resource('file:///project/logo.png', lambda: b'\x89PNG', name='logo', mime_type='image/png')

    @library.resource('config://async')
    async def later_config() -> str:
        await Pyjo.Promise.timer(0.01)
        return 'later'

    library_app = Pyjoyment.new()
    library_app.log.level = 'fatal'
    library_app.routes.any('/mcp').to(cb=library.to_action())
    tl = Pyjo.MCP.Test.new(library_app)
    tl.client.name = 'ExampleClient'

    tl.discover_ok().status_is(200).result_is('/capabilities', {'prompts': {}, 'resources': {}})

    tl.list_prompts_ok().status_is(200)
    tl.result_is('/resultType', 'complete').result_is('/ttlMs', 0).result_is('/cacheScope', 'public')
    tl.result_is('/_meta', SERVER_INFO)
    tl.result_is(
        '/prompts/0',
        {
            'name': 'code_review',
            'title': 'Request Code Review',
            'description': 'Asks the LLM to analyze code quality and suggest improvements.',
            'arguments': [{'name': 'code', 'description': 'The code to review', 'required': True}],
        },
    )
    tl.prompt_is('greeting', '/arguments', [{'name': 'name', 'required': False}])
    tl.mcp_ok('prompts/list', {'cursor': 'next-page-cursor'}).status_is(200)
    tl.error_is({'code': -32602, 'message': 'Invalid cursor'})

    tl.get_prompt_ok('code_review', {'code': "def hello():\n    print('world')"}).status_is(200)
    tl.result_is(
        {
            'resultType': 'complete',
            'messages': [
                {
                    'role': 'user',
                    'content': {
                        'type': 'text',
                        'text': "Please review this Python code:\ndef hello():\n    print('world')",
                    },
                }
            ],
            '_meta': SERVER_INFO,
        }
    )
    tl.get_prompt_ok('greeting', {'name': 'Pyjo'}).status_is(200)
    tl.result_is('/messages/1/content/text', 'Hello from ExampleClient')
    tl.get_prompt_ok('greeting').result_is('/messages/0/content/text', 'Hello, World!')
    tl.get_prompt_ok('code_review').status_is(200)
    tl.error_is({'code': -32602, 'message': 'Missing required argument: code'})
    tl.get_prompt_ok('unknown').status_is(200).error_is({'code': -32602, 'message': 'Unknown prompt: unknown'})
    tl.mcp_ok('prompts/get', {'name': 'code_review', 'arguments': ['x']}).status_is(200)
    tl.error_is({'code': -32602, 'message': 'Invalid arguments'})
    tl.mcp_ok('prompts/get', {'name': 'code_review', 'arguments': {}}, headers={'Mcp-Name': 'foo'}).status_is(400)
    tl.error_message_is("Header mismatch: Mcp-Name header value 'foo' does not match body value 'code_review'")
    tl.get_prompt_ok('broken_prompt').status_is(500).error_is({'code': -32603, 'message': 'Internal error'})

    tl.list_resources_ok().status_is(200)
    tl.result_is('/ttlMs', 0).result_is('/_meta', SERVER_INFO)
    tl.result_is(
        '/resources/0',
        {
            'uri': 'file:///project/src/main.rs',
            'name': 'main_rs',
            'title': 'Rust Software Application Main File',
            'description': 'Primary application entry point.',
            'mimeType': 'text/x-rust',
        },
    )
    logo = {'uri': 'file:///project/logo.png', 'name': 'logo', 'mimeType': 'image/png'}
    tl.resource_is('file:///project/logo.png', logo)
    tl.mcp_ok('resources/list', {'cursor': 'next-page-cursor'}).status_is(200)
    tl.error_is({'code': -32602, 'message': 'Invalid cursor'})

    tl.read_resource_ok('file:///project/src/main.rs').status_is(200)
    tl.result_is(
        {
            'resultType': 'complete',
            'contents': [
                {
                    'uri': 'file:///project/src/main.rs',
                    'mimeType': 'text/x-rust',
                    'text': 'fn main() {\n    println!("Hello world!");\n}',
                }
            ],
            'ttlMs': 0,
            'cacheScope': 'public',
            '_meta': SERVER_INFO,
        }
    )
    blob = base64.b64encode(b'\x89PNG').decode()
    tl.read_resource_ok('file:///project/logo.png').result_is('/contents/0/blob', blob)
    tl.read_resource_ok('config://async').result_is('/contents/0/text', 'later')
    tl.read_resource_ok('file:///nonexistent.txt').status_is(200)
    tl.error_is({'code': -32602, 'message': 'Resource not found', 'data': {'uri': 'file:///nonexistent.txt'}})
    tl.mcp_ok('resources/read', {'uri': 'file:///project/logo.png'}, headers={'Mcp-Name': None}).status_is(400)
    tl.error_message_is('Header mismatch: Missing Mcp-Name header')
    tl.ua.close()

with subtest('Resource templates'):
    # A server of its own, with resource templates only, and a resource that a template matches too
    files = Pyjo.MCP.Server.new(name='ExampleServer', version='1.0.0')

    @files.resource('file:///project/{+path}', title='Project Files', mime_type='application/octet-stream')
    def project_file(path: str) -> str:
        """Access files in the project directory."""
        return f'File {path}'

    @files.resource('file:///project/README.md')
    def readme() -> str:
        """The documentation of the project."""
        return '# Project'

    @files.resource('users://{id}', context=True)
    async def user(context, id: str) -> str:
        await Pyjo.Promise.timer(0.01)
        return f'User {id} of {context.client_info.get("name")}'

    files.resource('users://{id}/raw', lambda id: f'Raw {id}', name='raw_user')
    files.resource('unsafe:///{+path}', lambda path: f'Unsafe {path}', name='unsafe', safe=False)

    files_app = Pyjoyment.new()
    files_app.log.level = 'fatal'
    files_app.routes.any('/mcp').to(cb=files.to_action())
    tf = Pyjo.MCP.Test.new(files_app)
    tf.client.name = 'ExampleClient'
    is_deeply_ok([resource.uri for resource in files.resources], ['file:///project/README.md'], 'resources')
    is_deeply_ok(
        [template.uri for template in files.resource_templates],
        ['file:///project/{+path}', 'users://{id}', 'users://{id}/raw', 'unsafe:///{+path}'],
        'resource templates',
    )

    tf.discover_ok().status_is(200).result_is('/capabilities', {'resources': {}})
    templates_only = Pyjo.MCP.Server.new(name='ExampleServer')
    templates_only.resource('users://{id}', lambda id: id)
    templates_app = Pyjoyment.new()
    templates_app.routes.any('/mcp').to(cb=templates_only.to_action())
    tt = Pyjo.MCP.Test.new(templates_app)
    tt.discover_ok().status_is(200).result_is('/capabilities', {'resources': {}}, 'resource templates only')
    tt.ua.close()

    tf.list_resource_templates_ok().status_is(200)
    tf.result_is('/ttlMs', 0).result_is('/cacheScope', 'public').result_is('/_meta', SERVER_INFO)
    tf.result_is(
        '/resourceTemplates/0',
        {
            'uriTemplate': 'file:///project/{+path}',
            'name': 'project_file',
            'title': 'Project Files',
            'description': 'Access files in the project directory.',
            'mimeType': 'application/octet-stream',
        },
    )
    tf.resource_template_is(
        'users://{id}/raw', {'uriTemplate': 'users://{id}/raw', 'name': 'raw_user', 'mimeType': 'text/plain'}
    )
    tf.mcp_ok('resources/templates/list', {'cursor': 'next-page-cursor'}).status_is(200)
    tf.error_is({'code': -32602, 'message': 'Invalid cursor'})
    tf.list_resources_ok().status_is(200).result_is('/resources/0/uri', 'file:///project/README.md')
    tf.result_is('/resources/1', None)

    tf.read_resource_ok('file:///project/src/main.rs').status_is(200)
    tf.result_is(
        {
            'resultType': 'complete',
            'contents': [
                {
                    'uri': 'file:///project/src/main.rs',
                    'mimeType': 'application/octet-stream',
                    'text': 'File src/main.rs',
                }
            ],
            'ttlMs': 0,
            'cacheScope': 'public',
            '_meta': SERVER_INFO,
        }
    )
    tf.read_resource_ok('file:///project/README.md').result_is('/contents/0/text', '# Project')
    tf.read_resource_ok('users://1').result_is('/contents/0/text', 'User 1 of ExampleClient')
    tf.read_resource_ok('users://1/raw').result_is('/contents/0/text', 'Raw 1')
    tf.read_resource_ok('users://').status_is(200)
    tf.error_is({'code': -32602, 'message': 'Resource not found', 'data': {'uri': 'users://'}})
    tf.read_resource_ok('file:///project/../etc/passwd').status_is(200)
    tf.error_is({'code': -32602, 'message': 'Resource not found', 'data': {'uri': 'file:///project/../etc/passwd'}})
    tf.read_resource_ok('file:///project//etc/passwd').status_is(200).error_message_is('Resource not found')
    tf.read_resource_ok('unsafe:///../etc/passwd').result_is('/contents/0/text', 'Unsafe ../etc/passwd')
    tf.ua.close()

with subtest('Notifications'):
    # A server of its own, whose tools notify the client before their results
    notifying = Pyjo.MCP.Server.new(name='ExampleServer')
    cancelled = []
    sent = []

    @notifying.tool(context=True)
    def steps(context) -> str:
        sent.append(context.notify_log('debug', 'Too detailed'))
        sent.append(context.notify_log('info', 'Starting'))
        sent.append(context.notify_progress(1, 2, 'Half'))
        return 'Done'

    @notifying.tool(context=True)
    def later_steps(context) -> str:
        context.notify_progress(1)
        return Pyjo.Promise.timer(0.01).then(lambda: context.notify_progress(2) and 'Later')

    @notifying.tool(context=True)
    def endless(context) -> str:
        context.on('cancelled', lambda context: cancelled.append(context.is_cancelled))
        context.notify_progress(0)
        return Pyjo.Promise.timer(0.5).then(lambda: 'Too late')

    @notifying.tool
    def quiet() -> str:
        return 'Quiet'

    streams = Pyjoyment.new()
    streams.log.level = 'fatal'
    streams.routes.any('/mcp').to(cb=notifying.to_action())
    n = Pyjo.MCP.Test.new(streams)
    meta = {'progressToken': 'p1', 'io.modelcontextprotocol/logLevel': 'info'}

    n.mcp_ok('tools/call', {'name': 'steps'}, meta=meta).status_is(200)
    n.header_is('Content-Type', 'text/event-stream').header_is('X-Accel-Buffering', 'no')
    n.text_content_is('Done').response_is('/id', n.client._id)
    is_deeply_ok(
        n.notifications,
        [
            {'jsonrpc': '2.0', 'method': 'notifications/message', 'params': {'level': 'info', 'data': 'Starting'}},
            {
                'jsonrpc': '2.0',
                'method': 'notifications/progress',
                'params': {'progressToken': 'p1', 'progress': 1, 'total': 2, 'message': 'Half'},
            },
        ],
        'notifications before the response',
    )
    is_deeply_ok(sent, [False, True, True], 'below the level of the client')

    n.mcp_ok('tools/call', {'name': 'later_steps'}, meta=meta).status_is(200).text_content_is('Later')
    is_deeply_ok([m['params']['progress'] for m in n.notifications], [1, 2], 'notifications of an asynchronous tool')

    sent.clear()
    n.call_ok('steps').status_is(200).header_like('Content-Type', re.compile(r'^application/json'))
    n.text_content_is('Done')
    is_deeply_ok((n.notifications, sent), ([], [False, False, False]), 'no notifications without _meta')

    n.mcp_ok('tools/call', {'name': 'steps'}, meta=meta, headers={'Accept': 'application/json'}).status_is(200)
    n.header_like('Content-Type', re.compile(r'^application/json')).text_content_is('Done')
    is_deeply_ok((n.notifications, sent[3:]), ([], [False, False, False]), 'no stream for a client without one')

    n.mcp_ok('tools/call', {'name': 'quiet'}, meta=meta).status_is(200)
    n.header_like('Content-Type', re.compile(r'^application/json')).text_content_is('Quiet')

    # A client that closes the connection at the first event abandons the request
    request = n.client.build_request('tools/call', {'name': 'endless', 'arguments': {}, '_meta': meta})
    tx = n.client.build_tx(request)

    @tx.res.content.on('sse')
    def interrupt(content, event):
        if event:
            tx.res.error = {'message': 'Interrupted'}

    n.ua.start(tx)
    Pyjo.Promise.timer(0.1).wait()
    is_deeply_ok(cancelled, [True], 'cancelled')
    Pyjo.Promise.timer(0.5).wait()
    is_deeply_ok(cancelled, [True], 'once')
    n.ua.close()

    # The transport stdio, whose notifications are messages of the stream before the response
    class Messages(Pyjo.EventEmitter.object):
        def __init__(self):
            super().__init__()
            self.sent = []

        def close_gracefully(self):
            pass

        def send(self, message):
            self.sent.append(json.loads(message))
            return self

    peer = Messages()
    notifying.serve(peer)
    params = {'name': 'steps', 'arguments': {}, '_meta': {**META, **meta}}
    peer.emit('message', json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': params}))
    Pyjo.Promise.timer(0.01).wait()
    is_deeply_ok(
        [message.get('method') or message['result']['content'][0]['text'] for message in peer.sent],
        ['notifications/message', 'notifications/progress', 'Done'],
        'notifications over stdio',
    )

with subtest('Subscriptions'):
    # A server of its own, whose application changes its lists and its resources
    listening = Pyjo.MCP.Server.new(name='ExampleServer')
    listening.tool('add', add)
    listening.resource('file:///project/config.json', lambda: {'debug': False})
    listening.heartbeat = 0.05
    subscribed = Pyjoyment.new()
    subscribed.log.level = 'fatal'
    subscribed.routes.any('/mcp').to(cb=listening.to_action())
    s = Pyjo.MCP.Test.new(subscribed)

    s.discover_ok().status_is(200).result_is('/capabilities', {'tools': {}, 'resources': {}})
    listening.list_changed = listening.subscribe = True
    s.discover_ok().status_is(200)
    s.result_is(
        '/capabilities', {'tools': {'listChanged': True}, 'resources': {'listChanged': True, 'subscribe': True}}
    )

    # The example of the specification
    notifications = {'toolsListChanged': True, 'resourceSubscriptions': ['file:///project/config.json']}
    s.listen_ok(notifications).status_is(200)
    s.header_is('Content-Type', 'text/event-stream').header_is('X-Accel-Buffering', 'no')
    id = s.client._id
    s.notification_ok().notification_is(
        {
            'jsonrpc': '2.0',
            'method': 'notifications/subscriptions/acknowledged',
            'params': {'_meta': {'io.modelcontextprotocol/subscriptionId': id}, 'notifications': notifications},
        }
    )
    is_ok(listening.notify_list_changed('tools'), 1, 'one subscription')
    is_ok(listening.notify_list_changed('prompts'), 0, 'not asked for')
    is_ok(listening.notify_resource_updated('file:///project/other.json'), 0, 'another resource')
    is_ok(listening.notify_resource_updated('file:///project/config.json'), 1, 'resource')
    s.notification_ok().notification_is(
        {
            'jsonrpc': '2.0',
            'method': 'notifications/tools/list_changed',
            'params': {'_meta': {'io.modelcontextprotocol/subscriptionId': id}},
        }
    )
    s.notification_ok().notification_is('/method', 'notifications/resources/updated')
    s.notification_is(
        '/params',
        {'_meta': {'io.modelcontextprotocol/subscriptionId': id}, 'uri': notifications['resourceSubscriptions'][0]},
    )
    s.sse_finish_ok()
    Pyjo.Promise.timer(0.01).wait()
    is_ok(listening.notify_list_changed('tools'), 0, 'closed by the client')

    try:
        listening.notify_list_changed('templates')
    except Pyjo.Exception.object as e:
        is_ok(e.message, 'Unknown list: templates', 'unknown list')
    else:
        fail_ok('unknown list')

    # A subscription that the server ends gracefully, when its event loop stops, with the comments that keep it open
    client = Pyjo.MCP.Client.new('/mcp', ua=s.ua)
    request = client.build_request(
        'subscriptions/listen',
        {'notifications': {'promptsListChanged': True, 'toolsListChanged': 'yes', 'resourceSubscriptions': ['a', 1]}},
    )
    tx = client.build_tx(request)
    read = []
    events = []
    tx.on('connection', lambda tx, id: s.ua.ioloop.stream(id).on('read', lambda stream, chunk: read.append(chunk)))
    tx.res.content.on('sse', lambda content, event=None: event and events.append(json.loads(event['text'])))
    s.ua.start(tx, lambda ua, tx: None)
    Pyjo.Promise.timer(0.2).wait()
    ok(b''.join(read).count(b'\r\n: keepalive\r\n') > 1, 'comments of the stream of events')
    is_deeply_ok(
        events[0]['params']['notifications'], {'promptsListChanged': True, 'resourceSubscriptions': ['a']}, 'honored'
    )
    Pyjo.IOLoop.singleton.emit('finish')
    Pyjo.Promise.timer(0.05).wait()
    is_deeply_ok(
        events[-1],
        {
            'jsonrpc': '2.0',
            'id': request['id'],
            'result': {
                'resultType': 'complete',
                '_meta': {'io.modelcontextprotocol/subscriptionId': request['id'], **SERVER_INFO},
            },
        },
        'response at the end',
    )
    ok(tx.is_finished, 'stream closed')
    is_ok(listening.notify_list_changed('prompts'), 0, 'ended by the server')

    s.mcp_ok('subscriptions/listen', {'notifications': {}}, headers={'Accept': 'application/json'}).status_is(400)
    s.error_is({'code': -32600, 'message': 'Subscriptions need a stream of events'})
    s.mcp_ok('subscriptions/listen', meta={'io.modelcontextprotocol/protocolVersion': None}).status_is(400)
    s.error_message_is('Missing protocol version')
    s.ua.close()

    # The transport stdio, whose subscriptions share the stream, and whose client cancels its requests
    peer = Messages()
    listening.serve(peer)
    waiting = []

    @listening.tool(context=True)
    def wait(context) -> str:
        promise = Pyjo.Promise.new()
        waiting.append((context, promise))
        return promise

    def listen(id, notifications):
        params = {'_meta': META, 'notifications': notifications}
        return {'jsonrpc': '2.0', 'id': id, 'method': 'subscriptions/listen', 'params': params}

    peer.emit('message', json.dumps(listen(1, {'toolsListChanged': True})))
    peer.emit('message', json.dumps(listen('two', {'resourcesListChanged': True})))
    Pyjo.Promise.timer(0.01).wait()
    is_ok(listening.notify_list_changed('tools'), 1, 'first subscription')
    is_ok(listening.notify_list_changed('resources'), 1, 'second subscription')
    is_deeply_ok(
        [
            (message['method'], message['params']['_meta']['io.modelcontextprotocol/subscriptionId'])
            for message in peer.sent
        ],
        [
            ('notifications/subscriptions/acknowledged', 1),
            ('notifications/subscriptions/acknowledged', 'two'),
            ('notifications/tools/list_changed', 1),
            ('notifications/resources/list_changed', 'two'),
        ],
        'messages of each subscription',
    )
    cancel = {'jsonrpc': '2.0', 'method': 'notifications/cancelled', 'params': {'requestId': 1}}
    peer.emit('message', json.dumps(cancel))
    Pyjo.Promise.timer(0.01).wait()
    is_ok(listening.notify_list_changed('tools'), 0, 'cancelled')

    params = {'name': 'wait', 'arguments': {}, '_meta': META}
    peer.emit('message', json.dumps({'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': params}))
    peer.emit('message', json.dumps({**cancel, 'params': {'requestId': 3, 'reason': 'Too long'}}))
    peer.emit('message', json.dumps({**cancel, 'params': {'requestId': 4}}))
    waiting[0][1].resolve('Done')
    Pyjo.Promise.timer(0.01).wait()
    ok(waiting[0][0].is_cancelled, 'tool cancelled')
    is_ok(len(peer.sent), 4, 'no responses of cancelled requests')

    peer.emit('end')
    Pyjo.Promise.timer(0.01).wait()
    is_deeply_ok(
        peer.sent[4],
        {
            'jsonrpc': '2.0',
            'id': 'two',
            'result': {
                'resultType': 'complete',
                '_meta': {'io.modelcontextprotocol/subscriptionId': 'two', **SERVER_INFO},
            },
        },
        'response at the end of the input',
    )
    is_ok(listening.notify_list_changed('resources'), 0, 'ended')

    # A stream that closes abandons its subscriptions
    peer = Messages()
    listening.serve(peer)
    peer.emit('message', json.dumps(listen(1, {'toolsListChanged': True})))
    Pyjo.Promise.timer(0.01).wait()
    peer.emit('close')
    is_ok(listening.notify_list_changed('tools'), 0, 'closed')
    is_ok(len(peer.sent), 1, 'only the acknowledgment')

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
