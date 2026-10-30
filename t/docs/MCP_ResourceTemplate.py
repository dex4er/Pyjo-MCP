from Pyjo.Test import *

import contextlib
import io


def output():
    return contextlib.redirect_stdout(io.StringIO())


with subtest('Synopsis'):
    from Pyjo.MCP.ResourceTemplate import ResourceTemplate

    def note(number: str) -> str:
        """A note, by its number."""
        return f'Note {number}'

    template = ResourceTemplate('notes://{number}', note)
    with output() as stdout:
        print(template.uri, template.name, template.description)
    is_ok(stdout.getvalue(), 'notes://{number} note A note, by its number.\n', 'resource template')

    # Or import the module, as in Google Python Style Guide

    import Pyjo.MCP.ResourceTemplate

    template = Pyjo.MCP.ResourceTemplate.new('file:///project/{+path}', lambda path: path.upper())
    with output() as stdout:
        template.resource('file:///project/README.md').read_p().then(print).wait()
    is_ok(
        stdout.getvalue(),
        "{'contents': [{'uri': 'file:///project/README.md', 'mimeType': 'text/plain', 'text': 'README.MD'}]}\n",
        'read_p',
    )

with subtest('new'):

    def read(path):
        return path

    template = Pyjo.MCP.ResourceTemplate.new('notes://{number}', note)
    template = Pyjo.MCP.ResourceTemplate.new('file:///project/{+path}', read, mime_type='text/markdown')
    is_ok(template.mime_type, 'text/markdown', 'mime_type')
    template = Pyjo.MCP.ResourceTemplate.new('users://{id}', lambda context, id: ..., context=True)
    ok(template.context, 'context')
    template = Pyjo.MCP.ResourceTemplate.new('notes://{number}', note, complete={'number': ['1', '2']})
    is_deeply_ok(template.complete, {'number': ['1', '2']}, 'complete')

with subtest('Attributes'):
    template = Pyjo.MCP.ResourceTemplate.new('notes://{number}', note)
    cb = template.cb
    is_ok(cb, note, 'cb')
    completions = template.complete
    is_deeply_ok(completions, {}, 'completions')
    notes = ['Buy milk', 'Write']
    template.complete['number'] = lambda value, arguments: [str(n) for n in range(1, len(notes) + 1)]
    is_deeply_ok(template.complete['number']('', {}), ['1', '2'], 'function')
    boolean = template.context
    is_ok(boolean, False, 'boolean')
    description = template.description
    is_ok(description, 'A note, by its number.', 'description')
    type = template.mime_type
    is_ok(type, 'text/plain', 'type')
    name = template.name
    is_ok(name, 'note', 'name')
    boolean = template.safe
    is_ok(boolean, True, 'safe')
    tpl = template.template
    is_ok(tpl.template, 'notes://{number}', 'tpl')
    title = template.title
    is_ok(title, None, 'title')
    uri = template.uri
    is_ok(uri, 'notes://{number}', 'uri')

with subtest('__json__'):
    definition = template.__json__()
    is_deeply_ok(list(definition), ['uriTemplate', 'name', 'description', 'mimeType'], 'definition')

with subtest('match'):
    variables = template.match('notes://1')
    is_deeply_ok(variables, {'number': '1'}, 'variables')

    files = Pyjo.MCP.ResourceTemplate.new('file:///project/{+path}', lambda path: '')

    # {'path': 'docs/index.md'}
    is_deeply_ok(files.match('file:///project/docs/index.md'), {'path': 'docs/index.md'}, 'match')

    # None
    is_ok(files.match('file:///project/../etc/passwd'), None, 'no match')

with subtest('resource'):
    resource = template.resource('notes://1')
    is_ok(resource.uri, 'notes://1', 'resource')

    with output() as stdout:
        Pyjo.MCP.ResourceTemplate.new('notes://{number}', note).resource('notes://1').read_p().then(print).wait()
    is_ok(
        stdout.getvalue(),
        "{'contents': [{'uri': 'notes://1', 'mimeType': 'text/plain', 'text': 'Note 1'}]}\n",
        'printed',
    )

done_testing()
