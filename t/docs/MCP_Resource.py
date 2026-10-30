from Pyjo.Test import *

import contextlib
import io


def output():
    return contextlib.redirect_stdout(io.StringIO())


with subtest('Synopsis'):
    from Pyjo.MCP.Resource import Resource

    def readme() -> str:
        """The documentation of the project."""
        return '# Pyjo-MCP'

    resource = Resource('file:///project/README.md', readme, mime_type='text/markdown')
    with output() as stdout:
        print(resource.uri, resource.name, resource.description)
    is_ok(stdout.getvalue(), 'file:///project/README.md readme The documentation of the project.\n', 'resource')

    # Or import the module, as in Google Python Style Guide

    import Pyjo.MCP.Resource

    resource = Pyjo.MCP.Resource.new('file:///project/logo.png', lambda: b'\x89PNG', mime_type='image/png')
    with output() as stdout:
        resource.read_p().then(print).wait()
    is_ok(
        stdout.getvalue(),
        "{'contents': [{'uri': 'file:///project/logo.png', 'mimeType': 'image/png', 'blob': 'iVBORw=='}]}\n",
        'read_p',
    )

with subtest('new'):
    resource = Pyjo.MCP.Resource.new('file:///project/README.md', readme)
    resource = Pyjo.MCP.Resource.new('file:///project/README.md', readme, mime_type='text/markdown')
    is_ok(resource.mime_type, 'text/markdown', 'mime_type')
    resource = Pyjo.MCP.Resource.new('config://app', lambda context: ..., context=True)
    ok(resource.context, 'context')

with subtest('Attributes'):
    resource = Pyjo.MCP.Resource.new('file:///project/README.md', readme, mime_type='text/markdown')
    cb = resource.cb
    is_ok(cb, readme, 'cb')
    boolean = resource.context
    is_ok(boolean, False, 'boolean')
    description = resource.description
    is_ok(description, 'The documentation of the project.', 'description')
    type = resource.mime_type
    is_ok(type, 'text/markdown', 'type')
    name = resource.name
    is_ok(name, 'readme', 'name')
    title = resource.title
    is_ok(title, None, 'title')
    uri = resource.uri
    is_ok(uri, 'file:///project/README.md', 'uri')

with subtest('__json__'):
    definition = resource.__json__()
    is_deeply_ok(list(definition), ['uri', 'name', 'description', 'mimeType'], 'definition')

with subtest('read_p'):
    results = []
    promise = resource.read_p()
    promise.then(results.append).wait()
    promise = resource.read_p(None)
    promise.then(results.append).wait()
    is_deeply_ok(results[0], results[1], 'promise')

    with output() as stdout:
        resource.read_p().then(print).wait()
    is_ok(
        stdout.getvalue(),
        "{'contents': [{'uri': 'file:///project/README.md', 'mimeType': 'text/markdown', 'text': '# Pyjo-MCP'}]}\n",
        'printed',
    )

with subtest('result'):
    result = resource.result('# Pyjo-MCP')
    is_ok(result['contents'][0]['text'], '# Pyjo-MCP', 'text')
    result = resource.result(b'\x89PNG')
    is_ok(result['contents'][0]['blob'], 'iVBORw==', 'blob')

done_testing()
