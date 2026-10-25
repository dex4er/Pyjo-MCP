import Pyjo.File
import Pyjo.Test.Pyjo

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
    t = Pyjo.Test.Pyjo.new(EXAMPLES.child(f'{name}.py'))
    t.app.log.level = 'fatal'
    return t


def request(t, method, headers=None, **params):
    sent = {'MCP-Protocol-Version': '2026-07-28', 'Mcp-Method': method, **(headers or {})}
    if 'name' in params:
        sent['Mcp-Name'] = params['name']
    message = {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': {**params, '_meta': META}}
    return t.post_ok('/mcp', sent, json=message)


def call(t, tool, headers=None, /, **arguments):
    return request(t, 'tools/call', headers, name=tool, arguments=arguments)


with subtest('A first server'):
    t = tutorial('hello')
    request(t, 'server/discover').status_is(200).json_is('/result/capabilities', {'tools': {}})
    t.json_is('/result/_meta/io.modelcontextprotocol~1serverInfo', {'name': 'hello', 'version': '1.0.0'})
    request(t, 'tools/list').status_is(200)
    t.json_is(
        '/result/tools',
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
    call(t, 'greet', name='Pyjo').status_is(200)
    t.json_is('/result/content', [{'type': 'text', 'text': 'Hello, Pyjo!'}]).json_is('/result/isError', False)
    t.get_ok('/mcp').status_is(405)
    t.post_ok('/mcp', {'Origin': 'https://evil.example'}, json={}).status_is(403)

with subtest('Schemas'):
    t = tutorial('schemas')
    request(t, 'tools/list').status_is(200)
    t.json_is('/result/tools/0/inputSchema', SEARCH)
    t.json_is('/result/tools/0/inputSchema/properties/limit/maximum', 10)
    t.json_is('/result/tools/0/inputSchema/properties/sort/enum', ['name', 'price'])
    t.json_is('/result/tools/0/inputSchema/required', ['query'])
    t.json_is('/result/tools/0/outputSchema/type', 'array')
    t.json_is('/result/tools/0/outputSchema/items/properties/price', {'type': 'number', 'description': 'Price in EUR'})
    t.json_is('/result/tools/0/annotations', {'readOnlyHint': True})
    call(t, 'search', query='PYJO', sort='price').status_is(200)
    names = [item['name'] for item in t.tx.res.json('/result/structuredContent')]
    is_deeply_ok(names, ['Pyjo sticker', 'Pyjo mug', 'Pyjo shirt'], 'sorted by price')
    t.json_like('/result/content/0/text', re.compile(r'^\[\{"name":"Pyjo sticker",'))
    call(t, 'search', query='pyjo', in_stock=True, limit=1).status_is(200)
    t.json_is('/result/structuredContent', [{'name': 'Pyjo mug', 'price': 12.5, 'stock': 3}])
    call(t, 'search', query='pyjo', sort='stock').status_is(200).json_is('/result/isError', True)
    t.json_is('/result/content/0/text', 'Invalid arguments:\n/sort: Not in enum: "name", "price".')

with subtest('Errors'):
    t = tutorial('errors')
    tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    call(t, 'book', date=tomorrow, seats=2).status_is(200).json_is(
        '/result/content/0/text', f'Booked 2 seats on {tomorrow}.'
    )
    call(t, 'book', date='2020-01-01').status_is(200).json_is('/result/isError', True)
    t.json_is('/result/content/0/text', 'Invalid date 2020-01-01: the flight has to be in the future.')
    call(t, 'book', date='tomorrow').status_is(200).json_is('/result/isError', True)
    t.json_is('/result/content/0/text', 'Invalid date tomorrow: expected YYYY-MM-DD.')
    call(t, 'book', date=tomorrow, seats=0).status_is(200).json_is('/result/isError', True)
    t.json_is('/result/content/0/text', 'Invalid arguments:\n/seats: Less than the minimum 1.')
    call(t, 'cancel').status_is(200).json_is('/error', {'code': -32602, 'message': 'Unknown tool: cancel'})
    call(t, 'book', date=tomorrow, seats=10).status_is(500)
    t.json_is('/error', {'code': -32603, 'message': 'Internal error'}).content_unlike(re.compile(r'booking system'))

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

    call(t, 'title', url='https://example.com/page').status_is(200).json_is('/result/content/0/text', 'Pyjo & MCP')
    call(t, 'title', url='https://example.com/untitled').status_is(200).json_is('/result/isError', True)
    t.json_is('/result/content/0/text', 'The page has no title')
    call(t, 'title', url='https://example.com/missing').status_is(200).json_is('/result/isError', True)
    t.json_is('/result/content/0/text', 'The page answered 404 Not Found')
    t.ua.close()

with subtest('Context'):
    t = tutorial('context')
    call(t, 'whoami', {'User-Agent': 'Test'}).status_is(200)
    t.json_is('/result/content/0/text', 'ExampleClient 2026-07-28, with Test')

with subtest('Security'):
    os.environ['MCP_TOKEN'] = 'sesame'
    try:
        t = tutorial('security')
    finally:
        del os.environ['MCP_TOKEN']
    t.get_ok('/').status_is(200).content_is('The MCP endpoint is /mcp.')
    t.get_ok('/', {'Host': 'evil.example'}).status_is(200)
    call(t, 'secret', {'Authorization': 'Bearer sesame'}).status_is(200).json_is(
        '/result/content/0/text', 'The cake is a lie.'
    )
    call(t, 'secret', {'Authorization': 'Bearer sesame', 'Host': 'mcp.example.com'}).status_is(200)
    call(t, 'secret').status_is(401).header_is('WWW-Authenticate', 'Bearer').json_is({'error': 'Unauthorized'})
    call(t, 'secret', {'Authorization': 'Bearer open'}).status_is(401)
    call(t, 'secret', {'Authorization': 'Bearer sesame', 'Host': 'evil.example'}).status_is(421)
    call(t, 'secret', {'Authorization': 'Bearer sesame', 'Origin': 'https://evil.example'}).status_is(403)

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
    call(t, 'greet', name='Pyjo').status_is(200).json_is('/result/content/0/text', 'Hello, Pyjo!')

with subtest('Testing'):
    result = subprocess.run(
        [sys.executable, EXAMPLES.child('hello_test.py').to_str()],
        capture_output=True,
        text=True,
        env={**os.environ, 'PYJO_LOG_LEVEL': 'fatal'},
        timeout=60,
    )
    is_ok(result.returncode, 0, 'test passes')
    like_ok(result.stdout, re.compile(r'^ok 2 - Without a name$', re.M), 'subtests')

done_testing()
