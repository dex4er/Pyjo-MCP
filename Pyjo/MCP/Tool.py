"""
Pyjo.MCP.Tool - Tool of a server of MCP
=======================================
::

    from Pyjo.MCP.Tool import Tool

    def add(a: int, b: int) -> int:
        \"\"\"Add two numbers.

        :param a: The first number.
        :param b: The second number.
        \"\"\"
        return a + b

    tool = Tool(add)
    print(tool.name, tool.description, tool.input_schema)

    # Or import the module, as in Google Python Style Guide

    import Pyjo.MCP.Tool

    tool = Pyjo.MCP.Tool.new(add, name='math.add', title='Addition')
    tool.call_p({'a': 1, 'b': 2}).then(print).wait()

:mod:`Pyjo.MCP.Tool` is a tool of :mod:`Pyjo.MCP.Server`, a function that a
language model calls with the arguments of its ``inputSchema``. The name, the
description and the schemas of the tool are those of the function by default:
its name, the first paragraph of its docstring, the schema of its parameters,
with the descriptions of its docstring, and the one of what it returns, of
:mod:`Pyjo.JSON.Schema`.

The function returns the result of the tool, as a value, a :mod:`Pyjo.Promise`
of it or a coroutine, of an ``async def``:

* a value of the ``outputSchema`` of the tool, as of the annotation of what the
  function returns, is the ``structuredContent`` of the result, and its JSON
  the text of its ``content``;
* a string, without an ``outputSchema``, is the text of the ``content``;
* a :class:`dict` with ``content``, without an ``outputSchema``, is the result
  as it is, for the content of another type, as an image;
* ``None`` is a result without content, and another value is its JSON.

Arguments that the ``inputSchema`` does not validate, and a function that
raises :class:`Error`, give a result with ``isError``, whose text the language
model reads to call the tool again, as a tool reports the errors of its
execution. Another exception is an error of the server, which the result does
not tell.

See also
--------

:mod:`Pyjo.MCP.Server`, :mod:`Pyjo.JSON.Schema`, :mod:`Pyjo.MCP`.

Classes
-------
"""

import Pyjo.Base
import Pyjo.Exception
import Pyjo.JSON
import Pyjo.JSON.Schema
import Pyjo.Promise

import builtins
import dataclasses
import datetime
import enum
import inspect
import re
import uuid

from collections.abc import Callable, Mapping
from typing import Any, cast


type Anything = builtins.object

# The characters of a token of a name of a field of HTTP (RFC 9110)
_TOKEN = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")


class Error(Pyjo.Exception.object):
    """
    An error of the execution of a tool, which the result of the call tells
    with ``isError``, so that the language model can correct the arguments. ::

        raise Pyjo.MCP.Tool.Error.new('Invalid departure date: must be in the future')
    """


class Pyjo_MCP_Tool(Pyjo.Base.object):
    """
    :mod:`Pyjo.MCP.Tool` inherits all methods from :mod:`Pyjo.Base` and
    implements the following new ones.
    """

    def __init__(
        self,
        cb: Callable[..., Any],
        *,
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        input_schema: Mapping[str, Any] | Pyjo.JSON.Schema.object | None = None,
        output_schema: Mapping[str, Any] | Pyjo.JSON.Schema.object | bool | None = None,
        annotations: Mapping[str, Any] | None = None,
        context: bool = False,
    ) -> None:
        """::

            tool = Pyjo.MCP.Tool.new(add)
            tool = Pyjo.MCP.Tool.new(add, name='math.add', title='Addition')
            tool = Pyjo.MCP.Tool.new(lambda c, **args: ..., input_schema={'type': 'object'}, context=True)
            tool = Pyjo.MCP.Tool.new(report, output_schema=False)

        Construct a new :mod:`Pyjo.MCP.Tool` object of a function. With
        ``context``, the function gets the :class:`~Pyjo.MCP.Server.Context` of
        the request before its arguments. ``output_schema`` of ``False`` gives
        the tool no ``outputSchema``, also when the function has the annotation
        of what it returns.
        """
        signature = inspect.signature(cb)
        skip = 1 if context else 0

        if input_schema is None:
            schema = Pyjo.JSON.Schema.parameters(cb, skip=skip)
            data = cast(dict[str, Any], schema.data)
            if description is None:
                description = data.pop('description', None)
            else:
                data.pop('description', None)
        elif isinstance(input_schema, Pyjo.JSON.Schema.object):
            schema = input_schema
        else:
            schema = Pyjo.JSON.Schema.new(dict(input_schema))

        output: Pyjo.JSON.Schema.object | None = None
        if output_schema is None or output_schema is True:
            returns = Pyjo.JSON.Schema.returns(cb)
            # A string is the text of the content, and None no content
            if returns is not None and cast(dict[str, Any], returns.data).get('type') not in ('string', 'null'):
                output = returns
        elif isinstance(output_schema, Pyjo.JSON.Schema.object):
            output = output_schema
        elif output_schema is not False:
            output = Pyjo.JSON.Schema.new(dict(output_schema))

        self.annotations: dict[str, Any] = dict(annotations or {})
        """::

            annotations = tool.annotations

        The properties of the behaviour of the tool, as ``readOnlyHint``, which
        a client takes as hints, for the ``annotations`` of the tool.
        """

        self.cb = cb
        """::

            cb = tool.cb

        The function of the tool.
        """

        self.context = context
        """::

            boolean = tool.context

        Whether the function gets the context of the request before its
        arguments.
        """

        self.description = description or ''
        """::

            description = tool.description

        What the tool does, for the language model, the first paragraph of the
        docstring of the function by default.
        """

        self.input_schema: Pyjo.JSON.Schema.object = schema
        """::

            schema = tool.input_schema

        The :mod:`Pyjo.JSON.Schema` of the arguments, the ``inputSchema`` of
        the tool, the one of the parameters of the function by default.
        """

        self.name = name or cb.__name__
        """::

            name = tool.name

        The name of the tool, the one of the function by default.
        """

        self.output_schema = output
        """::

            schema = tool.output_schema

        The :mod:`Pyjo.JSON.Schema` of the ``structuredContent`` of the result,
        the ``outputSchema`` of the tool, the one of what the function returns
        by default, or ``None``.
        """

        self.title = title
        """::

            title = tool.title

        The name of the tool for people, or ``None``.
        """

        self._header_params = _header_params_of(schema.data, self.name)
        self._signature = signature

    def __json__(self) -> dict[str, Any]:
        """::

            definition = tool.__json__()

        The definition of the tool, as ``tools/list`` gives it, with its
        ``name``, ``title``, ``description``, ``inputSchema``,
        ``outputSchema`` and ``annotations``, where it has them.
        """
        definition: dict[str, Any] = {'name': self.name}
        if self.title is not None:
            definition['title'] = self.title
        definition['description'] = self.description
        definition['inputSchema'] = self.input_schema.data
        if self.output_schema is not None:
            definition['outputSchema'] = self.output_schema.data
        if self.annotations:
            definition['annotations'] = self.annotations
        return definition

    def call_p(self, arguments: Mapping[str, Any], context: Any = None) -> Pyjo.Promise.object:
        """::

            promise = tool.call_p({'a': 1, 'b': 2})
            promise = tool.call_p({'a': 1, 'b': 2}, context)

        Call the function with the arguments, and return a :mod:`Pyjo.Promise`
        of the result of the tool, as ``tools/call`` gives it, without its
        ``resultType``, or rejected with an exception of the function that is not an
        :class:`Error`, an error of the server. ::

            # {'content': [{'type': 'text', 'text': '3'}], 'structuredContent': 3, 'isError': False}
            tool.call_p({'a': 1, 'b': 2}).then(print).wait()
        """
        if not (result := self.input_schema.validate(dict(arguments))):
            return Pyjo.Promise.resolve(error_result(f'Invalid arguments:\n{result}'))
        try:
            bound = self._signature.bind(*([context] if self.context else []), **arguments)
        except TypeError as e:
            return Pyjo.Promise.resolve(error_result(f'Invalid arguments: {e}'))

        try:
            value = self.cb(*bound.args, **bound.kwargs)
        except Error as e:
            return Pyjo.Promise.resolve(error_result(e.message))
        except Exception as e:
            return Pyjo.Promise.reject(e)
        if inspect.iscoroutine(value):
            value = Pyjo.Promise.new(value)
        if isinstance(value, Pyjo.Promise.object):

            def failed(e: Any = None) -> Any:
                if isinstance(e, Error):
                    return error_result(e.message)
                return Pyjo.Promise.reject(e)

            return value.then(self.result, failed)
        try:
            return Pyjo.Promise.resolve(self.result(value))
        except Exception as e:
            return Pyjo.Promise.reject(e)

    @property
    def header_params(self) -> list[tuple[str, list[str], str]]:
        """::

            params = tool.header_params

        The arguments of the ``x-mcp-header`` of the ``inputSchema``, which a
        client of HTTP sends as the headers ``Mcp-Param-{name}`` too, each with
        the name, the path of the properties and the type. A header that the
        specification does not allow, as of a property of an array or of a
        ``number``, fails with a :mod:`Pyjo.Exception` when the tool is made.
        """
        return self._header_params

    def result(self, value: Any = None) -> dict[str, Any]:
        """::

            result = tool.result(3)
            result = tool.result('Three')

        The result of the tool of what the function returns. A value that the
        ``outputSchema`` does not validate fails with a :mod:`Pyjo.Exception`,
        as an error of the server.
        """
        if self.output_schema is not None:
            data = _plain(value)
            if not (result := self.output_schema.validate(data)):
                raise Pyjo.Exception.new(f'The result of the tool {self.name} is not valid:\n{result}')
            text = Pyjo.JSON.to_json(data)
            return {'content': [{'type': 'text', 'text': text}], 'structuredContent': data, 'isError': False}
        if value is None:
            return {'content': [], 'isError': False}
        if isinstance(value, dict) and 'content' in value:
            return cast(dict[str, Any], value)
        data = _plain(value)
        return text_result(data if isinstance(data, str) else Pyjo.JSON.to_json(data))


def error_result(text: str) -> dict[str, Any]:
    """::

        result = Pyjo.MCP.Tool.error_result('Invalid departure date')

    A result of a tool with the text of an error of its execution and
    ``isError``.
    """
    return {'content': [{'type': 'text', 'text': text}], 'isError': True}


def text_result(text: str) -> dict[str, Any]:
    """::

        result = Pyjo.MCP.Tool.text_result('Sunny')

    A result of a tool with a text.
    """
    return {'content': [{'type': 'text', 'text': text}], 'isError': False}


def _header_params_of(schema: Anything, tool: str) -> list[tuple[str, list[str], str]]:
    params: list[tuple[str, list[str], str]] = []
    _header_params(schema, [], params, False)
    names = [name.lower() for name, _, _ in params]
    if len(set(names)) != len(names):
        raise Pyjo.Exception.new(f'The x-mcp-header of the tool {tool} are not unique')
    return params


def _header_params(schema: Anything, path: list[str], params: list[tuple[str, list[str], str]], hidden: bool) -> None:
    # The properties that have an x-mcp-header, through the chain of properties from the root only
    if not isinstance(schema, dict):
        return
    schema_ = cast(dict[str, Any], schema)
    for keyword, value in schema_.items():
        if keyword == 'properties' and isinstance(value, dict):
            for key, property in cast(dict[str, Any], value).items():
                _header_params(property, [*path, key], params, hidden)
        elif keyword in ('items', 'prefixItems', 'additionalProperties', 'patternProperties', 'contains', '$defs'):
            _header_params(value, path, params, True)
        elif keyword in ('allOf', 'anyOf', 'oneOf', 'not', 'if', 'then', 'else', 'dependentSchemas'):
            for each in cast(list[Any], value) if isinstance(value, list) else [value]:
                _header_params(each, path, params, True)
    if (name := schema_.get('x-mcp-header')) is None:
        return
    type = schema_.get('type')
    if hidden or not path:
        raise Pyjo.Exception.new(f'The x-mcp-header {name} is not of a property of the root')
    if not isinstance(name, str) or not _TOKEN.fullmatch(name):
        raise Pyjo.Exception.new(f'The x-mcp-header {name!r} is not a name of a header')
    if type not in ('integer', 'string', 'boolean'):
        raise Pyjo.Exception.new(f'The x-mcp-header {name} is not of an integer, a string or a boolean')
    params.append((name, path, type))


def _plain(value: Any) -> Any:
    # The value as JSON has it, of the types that Pyjo.JSON.Schema gives a schema
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {field.name: _plain(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, enum.Enum):
        return _plain(value.value)
    if isinstance(value, datetime.datetime | datetime.date | datetime.time):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in cast(dict[Any, Any], value).items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [_plain(item) for item in cast(list[Any], value)]
    if value is None or isinstance(value, bool | int | float | str):
        return value
    return Pyjo.JSON.decode_json(Pyjo.JSON.encode_json(value))


new = Pyjo_MCP_Tool.new
object = Pyjo_MCP_Tool
Tool = Pyjo_MCP_Tool
