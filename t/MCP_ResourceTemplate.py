import Pyjo.Exception
import Pyjo.MCP.Resource
import Pyjo.MCP.ResourceTemplate

from Pyjo.Test import *


# A resource template of a server of MCP, of a URI Template and a function


def read(resource, context=None):
    results = []
    resource.read_p(context).then(results.append, lambda e: results.append(e)).wait()
    return results[0]


with subtest('Function'):

    def note(number: str) -> str:
        """A note, by its number.

        More about the notes.
        """
        return f'Note {number}'

    template = Pyjo.MCP.ResourceTemplate.new('notes://{number}', note, mime_type='text/markdown')
    is_ok(template.uri, 'notes://{number}', 'URI Template')
    is_ok(template.template.variables, ['number'], 'template')
    is_ok(template.name, 'note', 'name of the function')
    is_ok(template.title, None, 'no title')
    is_ok(template.description, 'A note, by its number.', 'first paragraph of the docstring')
    is_ok(template.mime_type, 'text/markdown', 'media type')
    ok(template.safe, 'safe by default')
    is_deeply_ok(
        template.__json__(),
        {
            'uriTemplate': 'notes://{number}',
            'name': 'note',
            'description': 'A note, by its number.',
            'mimeType': 'text/markdown',
        },
        'definition',
    )
    resource = template.resource('notes://1')
    isa_ok(resource, Pyjo.MCP.Resource.object, 'resource')
    is_ok(resource.uri, 'notes://1', 'URI of the resource')
    is_ok(resource.name, 'note', 'name of the resource')
    is_ok(resource.description, 'A note, by its number.', 'description of the resource')
    is_deeply_ok(
        read(resource), {'contents': [{'uri': 'notes://1', 'mimeType': 'text/markdown', 'text': 'Note 1'}]}, 'text'
    )
    is_ok(template.resource('notes://'), None, 'no value of a variable that the function requires')
    is_ok(template.resource('other://1'), None, 'no match')

with subtest('Options'):
    template = Pyjo.MCP.ResourceTemplate.new(
        'users://{id}', lambda id: id, name='user', title='User', description='A user.', mime_type='application/json'
    )
    is_deeply_ok(
        template.__json__(),
        {
            'uriTemplate': 'users://{id}',
            'name': 'user',
            'title': 'User',
            'description': 'A user.',
            'mimeType': 'application/json',
        },
        'definition',
    )
    is_ok(template.resource('users://1').title, 'User', 'title of the resource')
    is_ok(template.resource('users://1').mime_type, 'application/json', 'media type of the resource')

    def plain(id):
        return ''

    template = Pyjo.MCP.ResourceTemplate.new('users://{id}', plain)
    is_ok(template.description, None, 'no description')
    is_ok(template.mime_type, 'text/plain', 'plain text by default')

with subtest('Variables'):
    template = Pyjo.MCP.ResourceTemplate.new('repo://{owner}/{repo}/blob/{+path}', lambda **values: str(values))
    is_deeply_ok(
        template.match('repo://dex4er/Pyjo-MCP/blob/docs/index.md'),
        {'owner': 'dex4er', 'repo': 'Pyjo-MCP', 'path': 'docs/index.md'},
        'values',
    )
    is_ok(
        read(template.resource('repo://dex4er/Pyjo-MCP/blob/README.md'))['contents'][0]['text'],
        "{'owner': 'dex4er', 'repo': 'Pyjo-MCP', 'path': 'README.md'}",
        'keyword arguments',
    )
    template = Pyjo.MCP.ResourceTemplate.new('file:///project{/path*}', lambda path: '/'.join(path))
    is_ok(read(template.resource('file:///project/docs/index.md'))['contents'][0]['text'], 'docs/index.md', 'list')
    template = Pyjo.MCP.ResourceTemplate.new('search://items{?q}', lambda q=None: q or 'all')
    is_ok(read(template.resource('search://items?q=Hello%20World'))['contents'][0]['text'], 'Hello World', 'decoded')
    is_ok(read(template.resource('search://items'))['contents'][0]['text'], 'all', 'no value of a query')

with subtest('Safe'):
    template = Pyjo.MCP.ResourceTemplate.new('file:///project/{+path}', lambda path: path)
    is_deeply_ok(template.match('file:///project/docs/index.md'), {'path': 'docs/index.md'}, 'relative path')
    is_deeply_ok(template.match('file:///project/docs/..md'), {'path': 'docs/..md'}, 'two dots in a name')
    is_deeply_ok(template.match('file:///project/docs/.../a'), {'path': 'docs/.../a'}, 'three dots')
    is_ok(template.match('file:///project/../etc/passwd'), None, 'parent')
    is_ok(template.match('file:///project/docs/../../etc/passwd'), None, 'parent in the middle')
    is_ok(template.match('file:///project/docs/..'), None, 'parent at the end')
    is_ok(template.match('file:///project/..'), None, 'parent alone')
    is_ok(template.match('file:///project/%2E%2E/etc/passwd'), None, 'encoded parent')
    is_ok(template.match('file:///project/docs\\..\\..\\secret'), None, 'parent of Windows')
    is_ok(template.match('file:///project//etc/passwd'), None, 'absolute path')
    is_ok(template.match('file:///project/\\etc\\passwd'), None, 'absolute path of Windows')
    is_ok(template.match('file:///project/C:/Windows'), None, 'drive of Windows')
    is_ok(template.match('file:///project/c:secret'), None, 'relative path of a drive of Windows')
    is_ok(template.match('file:///project/docs/index.md%00.txt'), None, 'NUL')
    is_ok(template.resource('file:///project/../etc/passwd'), None, 'no resource')
    template = Pyjo.MCP.ResourceTemplate.new('notes://{id}', lambda id: id)
    is_ok(template.match('notes://%2Fetc%2Fpasswd'), None, 'encoded absolute path of a simple expansion')
    is_ok(template.match('notes://..'), None, 'parent of a simple expansion')
    template = Pyjo.MCP.ResourceTemplate.new('file:///project{/path*}', lambda path: path)
    is_ok(template.match('file:///project/docs/../../etc'), None, 'parent in a list')
    template = Pyjo.MCP.ResourceTemplate.new('search://items{?params*}', lambda params: params)
    is_deeply_ok(template.match('search://items?a=1&b=2'), {'params': {'a': '1', 'b': '2'}}, 'dict')
    is_ok(template.match('search://items?a=1&b=..'), None, 'parent in a dict')

    template = Pyjo.MCP.ResourceTemplate.new('file:///project/{+path}', lambda path: path, safe=False)
    ok(not template.safe, 'not safe')
    is_deeply_ok(template.match('file:///project/../etc/passwd'), {'path': '../etc/passwd'}, 'parent')
    is_deeply_ok(template.match('file:///project//etc/passwd'), {'path': '/etc/passwd'}, 'absolute path')
    is_ok(read(template.resource('file:///project/a%00b'))['contents'][0]['text'], 'a\0b', 'NUL')

with subtest('Completions'):
    template = Pyjo.MCP.ResourceTemplate.new('notes://{number}', lambda number: number, complete={'number': ['1', '2']})
    is_deeply_ok(template.complete, {'number': ['1', '2']}, 'completions')
    is_deeply_ok(Pyjo.MCP.ResourceTemplate.new('notes://{number}', lambda number: number).complete, {}, 'none')

with subtest('Context'):
    template = Pyjo.MCP.ResourceTemplate.new('users://{id}', lambda context, id: f'{id} of {context}', context=True)
    is_ok(read(template.resource('users://1'), 'context')['contents'][0]['text'], '1 of context', 'context')
    template = Pyjo.MCP.ResourceTemplate.new('users://{id}', lambda id: id)
    is_ok(read(template.resource('users://1'), 'context')['contents'][0]['text'], '1', 'no context')

with subtest('Errors'):

    def broken(id):
        raise ValueError('Secret')

    template = Pyjo.MCP.ResourceTemplate.new('users://{id}', broken)
    isa_ok(read(template.resource('users://1')), ValueError, 'exception of a function rejects')
    template = Pyjo.MCP.ResourceTemplate.new('users://{id}', lambda: '')
    is_ok(template.resource('users://1'), None, 'function without the variable')
    template = Pyjo.MCP.ResourceTemplate.new('users://{id}', lambda **values: str(values))
    is_ok(read(template.resource('users://'))['contents'][0]['text'], '{}', 'no value of a function with keywords')
    template = Pyjo.MCP.ResourceTemplate.new('users://{id}', dict)
    is_ok(read(template.resource('users://1'))['contents'][0]['text'], '{"id":"1"}', 'function without a signature')

    try:
        Pyjo.MCP.ResourceTemplate.new('users://{id', lambda id: id)
    except Pyjo.Exception.object as e:
        is_ok(e.message, 'Unmatched brace in URI template: users://{id', 'not valid')
    else:
        fail_ok('not valid')
    try:
        Pyjo.MCP.ResourceTemplate.new('users://{id}{name}', lambda id, name: id)
    except Pyjo.Exception.object as e:
        is_ok(e.message, 'Expressions without a literal between them: users://{id}{name}', 'ambiguous')
    else:
        fail_ok('ambiguous')

with subtest('Python constructor'):
    from Pyjo.MCP.ResourceTemplate import ResourceTemplate

    template = ResourceTemplate('users://{id}', lambda id: id, name='user')
    isa_ok(template, Pyjo.MCP.ResourceTemplate.object, 'resource template')

done_testing()
