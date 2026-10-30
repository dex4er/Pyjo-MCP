import Pyjo.MCP.Resource
import Pyjo.Promise

from Pyjo.Test import *

import base64


# A resource of a server of MCP, of a function


def read(resource, context=None):
    results = []
    resource.read_p(context).then(results.append, lambda e: results.append(e)).wait()
    return results[0]


with subtest('Function'):

    def readme() -> str:
        """The documentation of the project.

        More about the documentation.
        """
        return '# Pyjo-MCP'

    resource = Pyjo.MCP.Resource.new('file:///project/README.md', readme, mime_type='text/markdown')
    is_ok(resource.uri, 'file:///project/README.md', 'URI')
    is_ok(resource.name, 'readme', 'name of the function')
    is_ok(resource.title, None, 'no title')
    is_ok(resource.description, 'The documentation of the project.', 'first paragraph of the docstring')
    is_ok(resource.mime_type, 'text/markdown', 'media type')
    is_deeply_ok(
        resource.__json__(),
        {
            'uri': 'file:///project/README.md',
            'name': 'readme',
            'description': 'The documentation of the project.',
            'mimeType': 'text/markdown',
        },
        'definition',
    )
    is_deeply_ok(
        read(resource),
        {'contents': [{'uri': 'file:///project/README.md', 'mimeType': 'text/markdown', 'text': '# Pyjo-MCP'}]},
        'text',
    )

with subtest('Options'):
    resource = Pyjo.MCP.Resource.new(
        'config://app', lambda: 'debug', name='config', title='Configuration', description='The configuration.'
    )
    is_deeply_ok(
        resource.__json__(),
        {
            'uri': 'config://app',
            'name': 'config',
            'title': 'Configuration',
            'description': 'The configuration.',
            'mimeType': 'text/plain',
        },
        'definition',
    )

    def plain():
        return ''

    resource = Pyjo.MCP.Resource.new('file:///empty', plain)
    is_ok(resource.description, None, 'no description')
    is_ok(resource.mime_type, 'text/plain', 'plain text by default')
    is_deeply_ok(resource.__json__(), {'uri': 'file:///empty', 'name': 'plain', 'mimeType': 'text/plain'}, 'definition')

with subtest('Context'):
    resource = Pyjo.MCP.Resource.new('config://whoami', lambda context: f'Hello {context}', name='w', context=True)
    is_ok(read(resource, 'context')['contents'][0]['text'], 'Hello context', 'context')
    resource = Pyjo.MCP.Resource.new('config://nobody', lambda: 'Hello', name='nobody')
    is_ok(read(resource, 'context')['contents'][0]['text'], 'Hello', 'no context')

with subtest('Results'):
    resource = Pyjo.MCP.Resource.new('file:///logo.png', lambda: b'\x89PNG', name='logo', mime_type='image/png')
    is_deeply_ok(
        read(resource),
        {
            'contents': [
                {'uri': 'file:///logo.png', 'mimeType': 'image/png', 'blob': base64.b64encode(b'\x89PNG').decode()}
            ]
        },
        'blob of bytes',
    )
    resource = Pyjo.MCP.Resource.new('file:///data', lambda: bytearray(b'\x00\x01'), name='data')
    is_ok(read(resource)['contents'][0]['blob'], base64.b64encode(b'\x00\x01').decode(), 'blob of a bytearray')
    contents = {
        'contents': [
            {'uri': 'file:///a.txt', 'mimeType': 'text/plain', 'text': 'a'},
            {'uri': 'file:///b.txt', 'mimeType': 'text/plain', 'text': 'b'},
        ]
    }
    resource = Pyjo.MCP.Resource.new('file:///dir', lambda: contents, name='dir')
    is_deeply_ok(read(resource), contents, 'result as it is')
    resource = Pyjo.MCP.Resource.new(
        'config://precision', lambda: {'digits': 2}, name='precision', mime_type='application/json'
    )
    is_deeply_ok(
        read(resource),
        {'contents': [{'uri': 'config://precision', 'mimeType': 'application/json', 'text': '{"digits":2}'}]},
        'JSON',
    )
    resource = Pyjo.MCP.Resource.new('config://none', lambda: None, name='none')
    is_ok(read(resource)['contents'][0]['text'], 'null', 'JSON of None')

with subtest('Promises and coroutines'):
    resource = Pyjo.MCP.Resource.new('file:///later', lambda: Pyjo.Promise.timer(0.01, 'later'), name='later')
    is_ok(read(resource)['contents'][0]['text'], 'later', 'promise')

    async def twice() -> str:
        await Pyjo.Promise.timer(0.01)
        return 'twice' * 2

    is_ok(read(Pyjo.MCP.Resource.new('file:///twice', twice))['contents'][0]['text'], 'twicetwice', 'coroutine')

    async def broken() -> str:
        raise ValueError('Secret')

    isa_ok(read(Pyjo.MCP.Resource.new('file:///broken', broken)), ValueError, 'exception of a coroutine rejects')

with subtest('Errors'):

    def broken():
        raise ValueError('Secret')

    isa_ok(read(Pyjo.MCP.Resource.new('file:///broken', broken)), ValueError, 'exception of a function rejects')

with subtest('Python constructor'):
    from Pyjo.MCP.Resource import Resource

    resource = Resource('file:///python', lambda: '', name='python')
    isa_ok(resource, Pyjo.MCP.Resource.object, 'resource')

done_testing()
