import Pyjo.File
import Pyjo.MCP.Test

from Pyjo.Test import *

import datetime
import json
import os
import re
import subprocess
import sys


# The examples of docs/guides/tutorial.rst, which includes them
EXAMPLES = Pyjo.File.curfile().dirname().dirname().sibling('docs', 'guides', 'tutorial')

META = {
    'io.modelcontextprotocol/protocolVersion': '2026-07-28',
    'io.modelcontextprotocol/clientInfo': {'name': 'ExampleClient', 'version': '1.0.0'},
    'io.modelcontextprotocol/clientCapabilities': {},
}


# The inputSchema of the tool search of schemas.py, of its type hints and its docstring
SEARCH = {
    'type': 'object',
    'properties': {
        'query': {'type': 'string', 'description': 'Part of the name of an item, in any case.'},
        'limit': {
            'type': 'integer',
            'minimum': 1,
            'maximum': 10,
            'default': 5,
            'description': 'How many items at most.',
        },
        'sort': {'type': 'string', 'enum': ['name', 'price'], 'default': 'name', 'description': 'Order of the items.'},
        'in_stock': {'type': 'boolean', 'default': False, 'description': 'Only the items that are in stock.'},
    },
    'required': ['query'],
    'additionalProperties': False,
}


def tutorial(name):
    t = Pyjo.MCP.Test.new(EXAMPLES.child(f'{name}.py'))
    t.app.log.level = 'fatal'
    t.client.name = 'ExampleClient'
    return t


with subtest('A first server'):
    t = tutorial('hello')
    t.discover_ok().status_is(200).result_is('/capabilities', {'tools': {}})
    t.result_is('/_meta/io.modelcontextprotocol~1serverInfo', {'name': 'hello', 'version': '1.0.0'})
    t.list_tools_ok().status_is(200)
    t.result_is(
        '/tools',
        [
            {
                'name': 'greet',
                'description': 'Greet somebody by name.',
                'inputSchema': {
                    'type': 'object',
                    'properties': {'name': {'type': 'string', 'description': 'Name of the person to greet.'}},
                    'required': ['name'],
                    'additionalProperties': False,
                },
            }
        ],
    )
    t.call_ok('greet', name='Pyjo').status_is(200)
    t.result_is('/content', [{'type': 'text', 'text': 'Hello, Pyjo!'}]).is_error_is(False)
    t.get_ok('/mcp').status_is(405)
    t.post_ok('/mcp', {'Origin': 'https://evil.example'}, json={}).status_is(403)

with subtest('Schemas'):
    t = tutorial('schemas')
    t.list_tools_ok().status_is(200)
    t.tool_is('search', '/inputSchema', SEARCH)
    t.tool_is('search', '/inputSchema/properties/limit/maximum', 10)
    t.tool_is('search', '/inputSchema/properties/sort/enum', ['name', 'price'])
    t.tool_is('search', '/inputSchema/required', ['query'])
    t.tool_is('search', '/outputSchema/type', 'array')
    t.tool_is('search', '/outputSchema/items/properties/price', {'type': 'number', 'description': 'Price in EUR'})
    t.tool_is('search', '/annotations', {'readOnlyHint': True})
    t.call_ok('search', query='PYJO', sort='price').status_is(200)
    names = [item['name'] for item in t.response['result']['structuredContent']]
    is_deeply_ok(names, ['Pyjo sticker', 'Pyjo mug', 'Pyjo shirt'], 'sorted by price')
    t.text_content_like(re.compile(r'^\[\{"name":"Pyjo sticker",'))
    t.call_ok('search', query='pyjo', in_stock=True, limit=1).status_is(200)
    t.structured_content_is([{'name': 'Pyjo mug', 'price': 12.5, 'stock': 3}])
    t.call_ok('search', query='pyjo', sort='stock').status_is(200).is_error_is(True)
    t.text_content_is('Invalid arguments:\n/sort: Not in enum: "name", "price".')

with subtest('Errors'):
    t = tutorial('errors')
    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    t.call_ok('book', date=tomorrow, seats=2).status_is(200).text_content_is(f'Booked 2 seats on {tomorrow}.')
    t.call_ok('book', date='2020-01-01').status_is(200).is_error_is(True)
    t.text_content_is('Invalid date 2020-01-01: the flight has to be in the future.')
    t.call_ok('book', date='tomorrow').status_is(200).is_error_is(True)
    t.text_content_is('Invalid date tomorrow: expected YYYY-MM-DD.')
    t.call_ok('book', date=tomorrow, seats=0).status_is(200).is_error_is(True)
    t.text_content_is('Invalid arguments:\n/seats: Less than the minimum 1.')
    t.call_ok('cancel').status_is(200).error_is({'code': -32602, 'message': 'Unknown tool: cancel'})
    t.call_ok('book', date=tomorrow, seats=10).status_is(500)
    t.error_is({'code': -32603, 'message': 'Internal error'}).content_unlike(re.compile(r'booking system'))

with subtest('Asynchronous tools'):
    t = tutorial('title')
    t.app.routes.get('/page', {'data': b'<html><head><title>Pyjo &amp; MCP</title></head></html>'})
    t.app.routes.get('/untitled', {'data': b'<p>No title</p>'})

    # The requests of the pages go to the routes of the test, on the server of the user agent of the application
    t.app.ua.server.app = t.app

    @t.app.ua.on('start')
    def start(ua, tx):
        url, base = tx.req.url, ua.server.nb_url()
        if url.host == 'example.com':
            url.scheme, url.host, url.port = base.scheme, base.host, base.port

    t.call_ok('title', url='https://example.com/page').status_is(200).text_content_is('Pyjo & MCP')
    t.call_ok('title', url='https://example.com/untitled').status_is(200).is_error_is(True)
    t.text_content_is('The page has no title')
    t.call_ok('title', url='https://example.com/missing').status_is(200).is_error_is(True)
    t.text_content_is('The page answered 404 Not Found')
    t.ua.close()

with subtest('Context'):
    t = tutorial('context')
    t.client.headers = {'User-Agent': 'Test'}
    t.call_ok('whoami').status_is(200).text_content_is('ExampleClient 2026-07-28, with Test')

with subtest('Security'):
    os.environ['MCP_TOKEN'] = 'sesame'
    try:
        t = tutorial('security')
    finally:
        del os.environ['MCP_TOKEN']
    t.get_ok('/').status_is(200).content_is('The MCP endpoint is /mcp.')
    t.get_ok('/', {'Host': 'evil.example'}).status_is(200)
    t.client.headers = {'Authorization': 'Bearer sesame'}
    t.call_ok('secret').status_is(200).text_content_is('The cake is a lie.')
    t.client.headers = {'Authorization': 'Bearer sesame', 'Host': 'mcp.example.com'}
    t.call_ok('secret').status_is(200)
    t.client.headers = {}
    t.call_ok('secret').status_is(401).header_is('WWW-Authenticate', 'Bearer').json_is({'error': 'Unauthorized'})
    t.client.headers = {'Authorization': 'Bearer open'}
    t.call_ok('secret').status_is(401)
    t.client.headers = {'Authorization': 'Bearer sesame', 'Host': 'evil.example'}
    t.call_ok('secret').status_is(421)
    t.client.headers = {'Authorization': 'Bearer sesame', 'Origin': 'https://evil.example'}
    t.call_ok('secret').status_is(403)

with subtest('Standard input and output'):
    params = {'name': 'greet', 'arguments': {'name': 'Pyjo'}, '_meta': META}
    result = subprocess.run(
        [sys.executable, EXAMPLES.child('stdio.py').to_str(), 'stdio'],
        input=json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': params}) + '\n',
        capture_output=True,
        text=True,
        env={**os.environ, 'PYJO_LOG_LEVEL': 'info'},
        timeout=60,
    )
    is_ok(result.returncode, 0, 'end of the input')
    is_ok(json.loads(result.stdout)['result']['content'][0]['text'], 'Hello, Pyjo!', 'response on the standard output')
    like_ok(result.stderr, re.compile(r'Greeting Pyjo'), 'log on the standard error')
    t = tutorial('stdio')
    t.call_ok('greet', name='Pyjo').status_is(200).text_content_is('Hello, Pyjo!')

with subtest('Testing'):
    result = subprocess.run(
        [sys.executable, EXAMPLES.child('hello_test.py').to_str()],
        capture_output=True,
        text=True,
        env={**os.environ, 'PYJO_LOG_LEVEL': 'fatal'},
        timeout=60,
    )
    is_ok(result.returncode, 0, 'test passes')
    like_ok(result.stdout, re.compile(r'^ok 3 - Tools$', re.M), 'subtests')

done_testing()
