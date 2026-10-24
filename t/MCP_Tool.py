import Pyjo.JSON.Schema
import Pyjo.MCP.Tool
import Pyjo.Promise

from Pyjo.Test import *

import dataclasses
import datetime
import enum
import re

from typing import TypedDict


# A tool of a server of MCP, of a function


def call(tool, arguments, context=None):
    results = []
    tool.call_p(arguments, context).then(results.append, lambda e: results.append(e)).wait()
    return results[0]


class Forecast(TypedDict):
    temperature: float
    conditions: str


class Color(enum.Enum):
    RED = 'red'
    GREEN = 'green'


@dataclasses.dataclass
class Point:
    x: int
    y: int


with subtest('Function'):

    def get_weather(location: str, days: int = 3) -> Forecast:
        """Get current weather information for a location.

        More about the weather.

        :param location: City name or zip code
        """
        return {'temperature': 22.5, 'conditions': f'Partly cloudy in {location} for {days} days'}

    tool = Pyjo.MCP.Tool.new(get_weather)
    is_ok(tool.name, 'get_weather', 'name of the function')
    is_ok(tool.title, None, 'no title')
    is_ok(tool.description, 'Get current weather information for a location.', 'first paragraph of the docstring')
    is_deeply_ok(
        tool.input_schema.data,
        {
            'type': 'object',
            'properties': {
                'location': {'type': 'string', 'description': 'City name or zip code'},
                'days': {'type': 'integer', 'default': 3},
            },
            'required': ['location'],
            'additionalProperties': False,
        },
        'schema of the parameters, without the description',
    )
    is_deeply_ok(
        tool.output_schema.data,
        {
            'type': 'object',
            'properties': {'temperature': {'type': 'number'}, 'conditions': {'type': 'string'}},
            'required': ['temperature', 'conditions'],
        },
        'schema of what it returns',
    )
    is_deeply_ok(tool.annotations, {}, 'no annotations')
    is_deeply_ok(
        tool.__json__(),
        {
            'name': 'get_weather',
            'description': 'Get current weather information for a location.',
            'inputSchema': tool.input_schema.data,
            'outputSchema': tool.output_schema.data,
        },
        'definition',
    )
    result = call(tool, {'location': 'Warsaw'})
    is_deeply_ok(
        result,
        {
            'content': [
                {'type': 'text', 'text': '{"conditions":"Partly cloudy in Warsaw for 3 days","temperature":22.5}'}
            ],
            'structuredContent': {'temperature': 22.5, 'conditions': 'Partly cloudy in Warsaw for 3 days'},
            'isError': False,
        },
        'structured result',
    )

with subtest('Options'):

    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    tool = Pyjo.MCP.Tool.new(
        add,
        name='math.add',
        title='Addition',
        description='Sum.',
        annotations={'readOnlyHint': True},
        output_schema=False,
    )
    is_deeply_ok(
        tool.__json__(),
        {
            'name': 'math.add',
            'title': 'Addition',
            'description': 'Sum.',
            'inputSchema': {
                'type': 'object',
                'properties': {'a': {'type': 'integer'}, 'b': {'type': 'integer'}},
                'required': ['a', 'b'],
                'additionalProperties': False,
            },
            'annotations': {'readOnlyHint': True},
        },
        'definition',
    )
    is_deeply_ok(call(tool, {'a': 1, 'b': 2}), {'content': [{'type': 'text', 'text': '3'}], 'isError': False}, 'text')
    schema = {'type': 'object', 'properties': {'a': {'type': 'integer', 'minimum': 0}}}
    tool = Pyjo.MCP.Tool.new(lambda **args: args.get('a'), name='given', input_schema=schema, output_schema=schema)
    is_deeply_ok(tool.input_schema.data, schema, 'schema of its own')
    is_deeply_ok(tool.output_schema.data, schema, 'output schema of its own')
    is_ok(tool.description, '', 'no description')
    tool = Pyjo.MCP.Tool.new(
        add, input_schema=Pyjo.JSON.Schema.z.object(a=Pyjo.JSON.Schema.z.int(), b=Pyjo.JSON.Schema.z.int())
    )
    is_ok(tool.description, '', 'no description of the docstring with a schema of its own')
    is_ok(tool.input_schema.data['properties']['a']['type'], 'integer', 'schema of the builder')
    tool = Pyjo.MCP.Tool.new(add, output_schema=Pyjo.JSON.Schema.z.number())
    is_deeply_ok(tool.output_schema.data, {'type': 'number'}, 'output schema of the builder')

with subtest('Context'):

    def whoami(context, greeting: str) -> str:
        return f'{greeting} {context}'

    tool = Pyjo.MCP.Tool.new(whoami, context=True)
    is_deeply_ok(list(tool.input_schema.data['properties']), ['greeting'], 'context is not an argument')
    is_ok(call(tool, {'greeting': 'Hello'}, 'context')['content'][0]['text'], 'Hello context', 'context first')

with subtest('Results'):
    tool = Pyjo.MCP.Tool.new(lambda: None, name='none')
    is_deeply_ok(call(tool, {}), {'content': [], 'isError': False}, 'None')
    is_ok(tool.output_schema, None, 'no output schema without an annotation')
    image = {'content': [{'type': 'image', 'data': 'aGVsbG8=', 'mimeType': 'image/png'}], 'isError': False}
    tool = Pyjo.MCP.Tool.new(lambda: image, name='image')
    is_deeply_ok(call(tool, {}), image, 'result as it is')
    tool = Pyjo.MCP.Tool.new(lambda: [1, 'two', {'three': 3}], name='list')
    is_ok(call(tool, {})['content'][0]['text'], '[1,"two",{"three":3}]', 'JSON')

    def nothing() -> None:
        pass

    is_ok(Pyjo.MCP.Tool.new(nothing).output_schema, None, 'no output schema of None')

    def point() -> Point:
        return Point(1, 2)

    is_deeply_ok(call(Pyjo.MCP.Tool.new(point), {})['structuredContent'], {'x': 1, 'y': 2}, 'dataclass')

    def color() -> Color:
        return Color.GREEN

    is_deeply_ok(call(Pyjo.MCP.Tool.new(color), {}), Pyjo.MCP.Tool.text_result('green'), 'enum of strings')

    def today() -> datetime.date:
        return datetime.date(2026, 7, 28)

    is_deeply_ok(call(Pyjo.MCP.Tool.new(today), {}), Pyjo.MCP.Tool.text_result('2026-07-28'), 'date')

    def points() -> tuple[Point, ...]:
        return (Point(1, 2), Point(3, 4))

    is_deeply_ok(
        call(Pyjo.MCP.Tool.new(points), {})['structuredContent'], [{'x': 1, 'y': 2}, {'x': 3, 'y': 4}], 'tuple'
    )
    is_deeply_ok(
        Pyjo.MCP.Tool.text_result('Sunny'),
        {'content': [{'type': 'text', 'text': 'Sunny'}], 'isError': False},
        'text_result',
    )
    is_deeply_ok(
        Pyjo.MCP.Tool.error_result('Oops'),
        {'content': [{'type': 'text', 'text': 'Oops'}], 'isError': True},
        'error_result',
    )

with subtest('Promises and coroutines'):

    def later(value: int) -> int:
        return Pyjo.Promise.timer(0.01, value)

    is_ok(call(Pyjo.MCP.Tool.new(later), {'value': 1})['structuredContent'], 1, 'promise')

    async def twice(value: int) -> int:
        await Pyjo.Promise.timer(0.01)
        return value * 2

    is_ok(call(Pyjo.MCP.Tool.new(twice), {'value': 21})['structuredContent'], 42, 'coroutine')

    async def failing() -> int:
        await Pyjo.Promise.timer(0.01)
        raise Pyjo.MCP.Tool.Error.new('Later')

    is_deeply_ok(call(Pyjo.MCP.Tool.new(failing), {}), Pyjo.MCP.Tool.error_result('Later'), 'error of a coroutine')

    async def broken() -> int:
        raise ValueError('Secret')

    isa_ok(call(Pyjo.MCP.Tool.new(broken), {}), ValueError, 'exception of a coroutine rejects')

with subtest('Errors'):

    def book(date: str) -> str:
        raise Pyjo.MCP.Tool.Error.new('Invalid departure date: must be in the future.')

    tool = Pyjo.MCP.Tool.new(book)
    error = Pyjo.MCP.Tool.error_result('Invalid departure date: must be in the future.')
    is_deeply_ok(call(tool, {'date': '2025-08-08'}), error, 'error of the execution')
    error = Pyjo.MCP.Tool.error_result('Invalid arguments:\n/date: Expected string - got integer.')
    is_deeply_ok(call(tool, {'date': 1}), error, 'invalid arguments')
    tool = Pyjo.MCP.Tool.new(book, input_schema={'type': 'object'})
    result = call(tool, {'when': 'now'})
    ok(result['isError'], 'arguments that the function does not take')
    like_ok(
        result['content'][0]['text'], re.compile(r"^Invalid arguments: missing a required argument: 'date'"), 'message'
    )

    def wrong() -> int:
        return 'one'

    isa_ok(call(Pyjo.MCP.Tool.new(wrong), {}), Pyjo.Exception.object, 'result that the output schema rejects')
    like_ok(
        str(call(Pyjo.MCP.Tool.new(wrong), {})), re.compile(r'^The result of the tool wrong is not valid'), 'message'
    )

    def broken():
        raise ValueError('Secret')

    isa_ok(call(Pyjo.MCP.Tool.new(broken), {}), ValueError, 'exception of a function rejects')

with subtest('x-mcp-header'):

    def schema(**properties):
        return {'type': 'object', 'properties': properties}

    tool = Pyjo.MCP.Tool.new(
        lambda **args: None,
        name='sql',
        input_schema=schema(
            region={'type': 'string', 'x-mcp-header': 'Region'},
            options=schema(limit={'type': 'integer', 'x-mcp-header': 'Limit'}),
            dry={'type': 'boolean', 'x-mcp-header': 'Dry'},
        ),
    )
    is_deeply_ok(
        tool.header_params,
        [('Region', ['region'], 'string'), ('Limit', ['options', 'limit'], 'integer'), ('Dry', ['dry'], 'boolean')],
        'headers of the properties',
    )
    invalid = [
        (schema(a={'type': 'number', 'x-mcp-header': 'A'}), r'not of an integer, a string or a boolean'),
        (
            schema(a={'type': 'array', 'items': {'type': 'string', 'x-mcp-header': 'A'}}),
            r'not of a property of the root',
        ),
        (schema(a={'anyOf': [{'type': 'string', 'x-mcp-header': 'A'}]}), r'not of a property of the root'),
        ({'type': 'string', 'x-mcp-header': 'A'}, r'not of a property of the root'),
        (schema(a={'type': 'string', 'x-mcp-header': 'A B'}), r"'A B' is not a name of a header"),
        (schema(a={'type': 'string', 'x-mcp-header': ''}), r"'' is not a name of a header"),
        (
            schema(a={'type': 'string', 'x-mcp-header': 'A'}, b={'type': 'string', 'x-mcp-header': 'a'}),
            r'are not unique',
        ),
    ]
    for input_schema, message in invalid:
        throws_ok(
            lambda input_schema=input_schema: Pyjo.MCP.Tool.new(
                lambda **args: None, name='bad', input_schema=input_schema
            ),
            re.compile(message),
            message,
        )

with subtest('Python constructor'):
    from Pyjo.MCP.Tool import Tool

    tool = Tool(lambda: None, name='python')
    isa_ok(tool, Pyjo.MCP.Tool.object, 'tool')

done_testing()
