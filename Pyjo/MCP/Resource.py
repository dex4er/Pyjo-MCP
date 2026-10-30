"""
Pyjo.MCP.Resource - Resource of a server of MCP
===============================================
::

    from Pyjo.MCP.Resource import Resource

    def readme() -> str:
        \"\"\"The documentation of the project.\"\"\"
        return '# Pyjo-MCP'

    resource = Resource('file:///project/README.md', readme, mime_type='text/markdown')
    print(resource.uri, resource.name, resource.description)

    # Or import the module, as in Google Python Style Guide

    import Pyjo.MCP.Resource

    resource = Pyjo.MCP.Resource.new('file:///project/logo.png', lambda: b'\\x89PNG', mime_type='image/png')
    resource.read_p().then(print).wait()

:mod:`Pyjo.MCP.Resource` is a resource of :mod:`Pyjo.MCP.Server`, data that a
client reads by its URI, as the context of a language model. The name and the
description of the resource are those of the function by default: its name
and the first paragraph of its docstring.

The function returns the contents of the resource, as a value, a
:mod:`Pyjo.Promise` of it or a coroutine, of an ``async def``:

* a string is the ``text`` of the contents;
* :class:`bytes` are the ``blob`` of the contents, in Base64;
* a :class:`dict` with ``contents`` is the result as it is, as with several
  of them;
* another value is the text of its JSON.

See also
--------

:mod:`Pyjo.MCP.Server`, :mod:`Pyjo.MCP.Prompt`, :mod:`Pyjo.MCP.Tool`,
:mod:`Pyjo.MCP`.

Classes
-------
"""

import Pyjo.Base
import Pyjo.JSON
import Pyjo.Promise

import base64
import inspect

from collections.abc import Callable
from typing import Any, cast


class Pyjo_MCP_Resource(Pyjo.Base.object):
    """
    :mod:`Pyjo.MCP.Resource` inherits all methods from :mod:`Pyjo.Base` and
    implements the following new ones.
    """

    def __init__(
        self,
        uri: str,
        cb: Callable[..., Any],
        *,
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        mime_type: str = 'text/plain',
        context: bool = False,
    ) -> None:
        """::

            resource = Pyjo.MCP.Resource.new('file:///project/README.md', readme)
            resource = Pyjo.MCP.Resource.new('file:///project/README.md', readme, mime_type='text/markdown')
            resource = Pyjo.MCP.Resource.new('config://app', lambda context: ..., context=True)

        Construct a new :mod:`Pyjo.MCP.Resource` object of a function. With
        ``context``, the function gets the :class:`~Pyjo.MCP.Server.Context` of
        the request.
        """
        if description is None:
            doc = inspect.getdoc(cb) or ''
            description = doc.split('\n\n', 1)[0].replace('\n', ' ').strip() or None

        self.cb = cb
        """::

            cb = resource.cb

        The function of the resource.
        """

        self.context = context
        """::

            boolean = resource.context

        Whether the function gets the context of the request.
        """

        self.description = description
        """::

            description = resource.description

        What the resource is, the first paragraph of the docstring of the
        function by default, or ``None``.
        """

        self.mime_type = mime_type
        """::

            type = resource.mime_type

        The media type of the contents, ``text/plain`` by default.
        """

        self.name = name or cb.__name__
        """::

            name = resource.name

        The name of the resource, the one of the function by default.
        """

        self.title = title
        """::

            title = resource.title

        The name of the resource for people, or ``None``.
        """

        self.uri = uri
        """::

            uri = resource.uri

        The URI of the resource, which ``resources/read`` asks for.
        """

    def __json__(self) -> dict[str, Any]:
        """::

            definition = resource.__json__()

        The definition of the resource, as ``resources/list`` gives it, with
        its ``uri``, ``name``, ``title``, ``description`` and ``mimeType``,
        where it has them.
        """
        definition: dict[str, Any] = {'uri': self.uri, 'name': self.name}
        if self.title is not None:
            definition['title'] = self.title
        if self.description is not None:
            definition['description'] = self.description
        definition['mimeType'] = self.mime_type
        return definition

    def read_p(self, context: Any = None) -> Pyjo.Promise.object:
        """::

            promise = resource.read_p()
            promise = resource.read_p(context)

        Call the function, and return a :mod:`Pyjo.Promise` of the result of
        the resource, as ``resources/read`` gives it, without its
        ``resultType``, or rejected with an exception of the function. ::

            # {'contents': [{'uri': 'file:///project/README.md', 'mimeType': 'text/markdown', 'text': '# Pyjo-MCP'}]}
            resource.read_p().then(print).wait()
        """
        try:
            value = self.cb(*([context] if self.context else []))
        except Exception as e:
            return Pyjo.Promise.reject(e)
        if inspect.iscoroutine(value):
            value = Pyjo.Promise.new(value)
        if isinstance(value, Pyjo.Promise.object):
            return value.then(self.result)
        return Pyjo.Promise.resolve(self.result(value))

    def result(self, value: Any = None) -> dict[str, Any]:
        """::

            result = resource.result('# Pyjo-MCP')
            result = resource.result(b'\\x89PNG')

        The result of the resource of what the function returns.
        """
        if isinstance(value, dict) and 'contents' in value:
            return cast(dict[str, Any], value)
        contents: dict[str, Any] = {'uri': self.uri, 'mimeType': self.mime_type}
        if isinstance(value, bytes | bytearray):
            contents['blob'] = base64.b64encode(value).decode()
        else:
            contents['text'] = value if isinstance(value, str) else Pyjo.JSON.to_json(cast(Any, value))
        return {'contents': [contents]}


new = Pyjo_MCP_Resource.new
object = Pyjo_MCP_Resource
Resource = Pyjo_MCP_Resource
