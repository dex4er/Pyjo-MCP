from Pyjo.Test import *

import contextlib
import io


def output():
    return contextlib.redirect_stdout(io.StringIO())


with subtest('Synopsis'):
    from Pyjo.MCP.Tool import Tool

    def add(a: int, b: int) -> int:
        """Add two numbers.

        :param a: The first number.
        :param b: The second number.
        """
        return a + b

    tool = Tool(add)
    with output() as stdout:
        print(tool.name, tool.description, tool.input_schema)
    like_ok(stdout.getvalue(), r'^add Add two numbers\. ', 'tool')

    # Or import the module, as in Google Python Style Guide

    import Pyjo.MCP.Tool

    tool = Pyjo.MCP.Tool.new(add, name='math.add', title='Addition')
    with output() as stdout:
        tool.call_p({'a': 1, 'b': 2}).then(print).wait()
    is_ok(
        stdout.getvalue(),
        "{'content': [{'type': 'text', 'text': '3'}], 'structuredContent': 3, 'isError': False}\n",
        'call_p',
    )

with subtest('Error'):

    def book():
        raise Pyjo.MCP.Tool.Error.new('Invalid departure date: must be in the future')

    throws_ok(book, Pyjo.MCP.Tool.Error, 'raise')

with subtest('new'):

    def report() -> dict[str, int]:
        return {'total': 1}

    tool = Pyjo.MCP.Tool.new(add)
    tool = Pyjo.MCP.Tool.new(add, name='math.add', title='Addition')
    is_ok(tool.title, 'Addition', 'title')
    tool = Pyjo.MCP.Tool.new(lambda c, **args: ..., input_schema={'type': 'object'}, context=True)
    ok(tool.context, 'context')
    tool = Pyjo.MCP.Tool.new(report, output_schema=False)
    is_ok(tool.output_schema, None, 'no output schema')

with subtest('Attributes'):
    tool = Pyjo.MCP.Tool.new(add, annotations={'readOnlyHint': True})
    annotations = tool.annotations
    is_deeply_ok(annotations, {'readOnlyHint': True}, 'annotations')
    cb = tool.cb
    is_ok(cb, add, 'cb')
    boolean = tool.context
    is_ok(boolean, False, 'boolean')
    description = tool.description
    is_ok(description, 'Add two numbers.', 'description')
    schema = tool.input_schema
    is_deeply_ok(list(schema.data['properties']), ['a', 'b'], 'schema')
    name = tool.name
    is_ok(name, 'add', 'name')
    schema = tool.output_schema
    is_deeply_ok(schema.data, {'type': 'integer'}, 'schema')
    title = tool.title
    is_ok(title, None, 'title')

with subtest('__json__'):
    definition = tool.__json__()
    is_deeply_ok(list(definition), ['name', 'description', 'inputSchema', 'outputSchema', 'annotations'], 'definition')

with subtest('call_p'):
    results = []
    promise = tool.call_p({'a': 1, 'b': 2})
    promise.then(results.append).wait()
    promise = tool.call_p({'a': 1, 'b': 2}, None)
    promise.then(results.append).wait()
    is_deeply_ok(results[0], results[1], 'promise')

    with output() as stdout:
        tool.call_p({'a': 1, 'b': 2}).then(print).wait()
    is_ok(
        stdout.getvalue(),
        "{'content': [{'type': 'text', 'text': '3'}], 'structuredContent': 3, 'isError': False}\n",
        'printed',
    )

with subtest('header_params'):
    schema = {'type': 'object', 'properties': {'region': {'type': 'string', 'x-mcp-header': 'Region'}}}
    tool = Pyjo.MCP.Tool.new(lambda region: region, name='sql', input_schema=schema)
    params = tool.header_params
    is_deeply_ok(params, [('Region', ['region'], 'string')], 'params')

with subtest('result'):
    tool = Pyjo.MCP.Tool.new(add)
    result = tool.result(3)
    is_ok(result['structuredContent'], 3, 'result')
    tool = Pyjo.MCP.Tool.new(add, output_schema=False)
    result = tool.result('Three')
    is_deeply_ok(result, {'content': [{'type': 'text', 'text': 'Three'}], 'isError': False}, 'result')

with subtest('error_result'):
    result = Pyjo.MCP.Tool.error_result('Invalid departure date')
    is_deeply_ok(result, {'content': [{'type': 'text', 'text': 'Invalid departure date'}], 'isError': True}, 'result')

with subtest('text_result'):
    result = Pyjo.MCP.Tool.text_result('Sunny')
    is_deeply_ok(result, {'content': [{'type': 'text', 'text': 'Sunny'}], 'isError': False}, 'result')

done_testing()
