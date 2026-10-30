"""
Pyjo.MCP.Prompt - Prompt of a server of MCP
===========================================
::

    from Pyjo.MCP.Prompt import Prompt

    def review(code: str, language: str = 'Python') -> str:
        \"\"\"Review a piece of code.

        :param code: The code to review.
        :param language: The language of the code.
        \"\"\"
        return f'Review this {language} code:\\n{code}'

    prompt = Prompt(review)
    print(prompt.name, prompt.description, prompt.arguments)

    # Or import the module, as in Google Python Style Guide

    import Pyjo.MCP.Prompt

    prompt = Pyjo.MCP.Prompt.new(review, name='code_review', title='Code review')
    prompt.get_p({'code': 'x = 1'}).then(print).wait()

:mod:`Pyjo.MCP.Prompt` is a prompt of :mod:`Pyjo.MCP.Server`, a template of
messages for a language model, which a user picks and fills with its
arguments. The name, the description and the arguments of the prompt are those
of the function by default: its name, the first paragraph of its docstring,
and its parameters, with the descriptions of its docstring, of which those
without a default are required.

The function returns the messages of the prompt, as a value, a
:mod:`Pyjo.Promise` of it or a coroutine, of an ``async def``:

* a string is one message of the user with the text;
* a :class:`list` is the messages, each with its ``role`` and its
  ``content``;
* a :class:`dict` with ``messages`` is the result as it is, as with a
  ``description`` of its own.

A missing argument that is required, or one that the function does not take,
is an error of the request, ``-32602``, as the specification requires, and an
exception of the function an error of the server.

See also
--------

:mod:`Pyjo.MCP.Server`, :mod:`Pyjo.MCP.Resource`, :mod:`Pyjo.MCP.Tool`,
:mod:`Pyjo.MCP`.

Classes
-------
"""

import Pyjo.Base
import Pyjo.JSON.RPC
import Pyjo.JSON.Schema
import Pyjo.Promise

import inspect

from collections.abc import Callable, Mapping
from typing import Any, cast


class Pyjo_MCP_Prompt(Pyjo.Base.object):
    """
    :mod:`Pyjo.MCP.Prompt` inherits all methods from :mod:`Pyjo.Base` and
    implements the following new ones.
    """

    def __init__(
        self,
        cb: Callable[..., Any],
        *,
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        arguments: list[Mapping[str, Any]] | None = None,
        context: bool = False,
    ) -> None:
        """::

            prompt = Pyjo.MCP.Prompt.new(review)
            prompt = Pyjo.MCP.Prompt.new(review, name='code_review', title='Code review')
            prompt = Pyjo.MCP.Prompt.new(lambda **args: ..., arguments=[{'name': 'code', 'required': True}])
            prompt = Pyjo.MCP.Prompt.new(lambda context, code: ..., context=True)

        Construct a new :mod:`Pyjo.MCP.Prompt` object of a function. With
        ``context``, the function gets the :class:`~Pyjo.MCP.Server.Context` of
        the request before its arguments.
        """
        skip = 1 if context else 0
        if arguments is None:
            data = cast(dict[str, Any], Pyjo.JSON.Schema.parameters(cb, skip=skip).data)
            if description is None:
                description = data.get('description')
            required = cast(list[str], data.get('required', []))
            arguments = []
            for key, property in cast(dict[str, Any], data.get('properties', {})).items():
                argument: dict[str, Any] = {'name': key}
                if (text := cast(dict[str, Any], property).get('description')) is not None:
                    argument['description'] = text
                argument['required'] = key in required
                arguments.append(argument)

        self.arguments: list[dict[str, Any]] = [dict(argument) for argument in arguments]
        """::

            arguments = prompt.arguments

        The arguments of the prompt, each with its ``name``, its
        ``description`` and whether it is ``required``, the parameters of the
        function by default.
        """

        self.cb = cb
        """::

            cb = prompt.cb

        The function of the prompt.
        """

        self.context = context
        """::

            boolean = prompt.context

        Whether the function gets the context of the request before its
        arguments.
        """

        self.description = description or ''
        """::

            description = prompt.description

        What the prompt is for, the first paragraph of the docstring of the
        function by default.
        """

        self.name = name or cb.__name__
        """::

            name = prompt.name

        The name of the prompt, the one of the function by default.
        """

        self.title = title
        """::

            title = prompt.title

        The name of the prompt for people, or ``None``.
        """

        self._signature = inspect.signature(cb)

    def __json__(self) -> dict[str, Any]:
        """::

            definition = prompt.__json__()

        The definition of the prompt, as ``prompts/list`` gives it, with its
        ``name``, ``title``, ``description`` and ``arguments``, where it has
        them.
        """
        definition: dict[str, Any] = {'name': self.name}
        if self.title is not None:
            definition['title'] = self.title
        definition['description'] = self.description
        definition['arguments'] = self.arguments
        return definition

    def get_p(self, arguments: Mapping[str, Any], context: Any = None) -> Pyjo.Promise.object:
        """::

            promise = prompt.get_p({'code': 'x = 1'})
            promise = prompt.get_p({'code': 'x = 1'}, context)

        Call the function with the arguments, and return a :mod:`Pyjo.Promise`
        of the result of the prompt, as ``prompts/get`` gives it, without its
        ``resultType``, or rejected with a :class:`Pyjo.JSON.RPC.Error` of
        arguments that are not valid, or an exception of the function. ::

            # {'messages': [{'role': 'user', 'content': {'type': 'text', 'text': 'Review this Python code:\\nx = 1'}}]}
            prompt.get_p({'code': 'x = 1'}).then(print).wait()
        """
        for argument in self.arguments:
            if argument.get('required') and argument['name'] not in arguments:
                message = f'Missing required argument: {argument["name"]}'
                return Pyjo.Promise.reject(Pyjo.JSON.RPC.Error.new(Pyjo.JSON.RPC.INVALID_PARAMS, message))
        try:
            bound = self._signature.bind(*([context] if self.context else []), **arguments)
        except TypeError as e:
            message = f'Invalid arguments: {e}'
            return Pyjo.Promise.reject(Pyjo.JSON.RPC.Error.new(Pyjo.JSON.RPC.INVALID_PARAMS, message))

        try:
            value = self.cb(*bound.args, **bound.kwargs)
        except Exception as e:
            return Pyjo.Promise.reject(e)
        if inspect.iscoroutine(value):
            value = Pyjo.Promise.new(value)
        if isinstance(value, Pyjo.Promise.object):
            return value.then(self.result)
        return Pyjo.Promise.resolve(self.result(value))

    def result(self, value: Any = None) -> dict[str, Any]:
        """::

            result = prompt.result('Review this code')
            result = prompt.result([{'role': 'assistant', 'content': {'type': 'text', 'text': 'Done'}}])

        The result of the prompt of what the function returns.
        """
        if isinstance(value, dict) and 'messages' in value:
            return cast(dict[str, Any], value)
        if isinstance(value, list):
            return {'messages': cast(list[Any], value)}
        return text_result('' if value is None else str(cast(Any, value)))


def text_result(text: str, role: str = 'user') -> dict[str, Any]:
    """::

        result = Pyjo.MCP.Prompt.text_result('Review this code')
        result = Pyjo.MCP.Prompt.text_result('Here is the review', role='assistant')

    A result of a prompt with one message of the text, of the user by default.
    """
    return {'messages': [{'role': role, 'content': {'type': 'text', 'text': text}}]}


new = Pyjo_MCP_Prompt.new
object = Pyjo_MCP_Prompt
Prompt = Pyjo_MCP_Prompt
