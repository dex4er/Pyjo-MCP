"""
Pyjo.MCP.ResourceTemplate - Resource template of a server of MCP
================================================================
::

    from Pyjo.MCP.ResourceTemplate import ResourceTemplate

    def note(number: str) -> str:
        \"\"\"A note, by its number.\"\"\"
        return f'Note {number}'

    template = ResourceTemplate('notes://{number}', note)
    print(template.uri, template.name, template.description)

    # Or import the module, as in Google Python Style Guide

    import Pyjo.MCP.ResourceTemplate

    template = Pyjo.MCP.ResourceTemplate.new('file:///project/{+path}', lambda path: path.upper())
    template.resource('file:///project/README.md').read_p().then(print).wait()

:mod:`Pyjo.MCP.ResourceTemplate` is a resource template of
:mod:`Pyjo.MCP.Server`, the resources of the URIs that a URI Template of
:rfc:`6570` of :mod:`Pyjo.URL.Template` matches, which a client reads by their
URIs. The values of the variables of a URI are the keyword arguments of the
function, which returns the contents of the resource, as the function of a
:mod:`Pyjo.MCP.Resource` does. The name and the description of the resource
template are those of the function by default: its name and the first
paragraph of its docstring.

The values of the variables come from the client, so a URI whose value has a
segment ``..``, an absolute path or the character NUL, which would read a
file outside of a directory of the function, has no resource, unless the
resource template is not :attr:`~Pyjo_MCP_ResourceTemplate.safe`.

See also
--------

:mod:`Pyjo.MCP.Resource`, :mod:`Pyjo.MCP.Server`, :mod:`Pyjo.URL.Template`,
:mod:`Pyjo.MCP`.

Classes
-------
"""

import Pyjo.Base
import Pyjo.URL.Template

from . import Resource

import functools
import inspect
import re

from collections.abc import Callable
from typing import Any, cast


class Pyjo_MCP_ResourceTemplate(Pyjo.Base.object):
    """
    :mod:`Pyjo.MCP.ResourceTemplate` inherits all methods from
    :mod:`Pyjo.Base` and implements the following new ones.
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
        safe: bool = True,
    ) -> None:
        """::

            template = Pyjo.MCP.ResourceTemplate.new('notes://{number}', note)
            template = Pyjo.MCP.ResourceTemplate.new('file:///project/{+path}', read, mime_type='text/markdown')
            template = Pyjo.MCP.ResourceTemplate.new('users://{id}', lambda context, id: ..., context=True)

        Construct a new :mod:`Pyjo.MCP.ResourceTemplate` object of a URI
        Template and a function. With ``context``, the function gets the
        :class:`~Pyjo.MCP.Server.Context` of the request before the values of
        the variables. A URI Template that is not valid, or whose expressions
        cannot be told apart, raises a :mod:`Pyjo.Exception`.
        """
        if description is None:
            doc = inspect.getdoc(cb) or ''
            description = doc.split('\n\n', 1)[0].replace('\n', ' ').strip() or None

        self.cb = cb
        """::

            cb = template.cb

        The function of the resource template.
        """

        self.context = context
        """::

            boolean = template.context

        Whether the function gets the context of the request.
        """

        self.description = description
        """::

            description = template.description

        What the resources are, the first paragraph of the docstring of the
        function by default, or ``None``.
        """

        self.mime_type = mime_type
        """::

            type = template.mime_type

        The media type of the contents, ``text/plain`` by default.
        """

        self.name = name or cb.__name__
        """::

            name = template.name

        The name of the resource template, the one of the function by default.
        """

        self.safe = safe
        """::

            boolean = template.safe

        Whether a URI whose value has a segment ``..``, an absolute path or the
        character NUL has no resource, true by default.
        """

        self.template = Pyjo.URL.Template.new(uri)
        """::

            tpl = template.template

        The :mod:`Pyjo.URL.Template` object of the URI Template.
        """
        # A template whose expressions cannot be told apart raises here, not at the first read
        self.template.match('')

        self.title = title
        """::

            title = template.title

        The name of the resource template for people, or ``None``.
        """

        self.uri = uri
        """::

            uri = template.uri

        The URI Template of the resources, which ``resources/templates/list``
        gives as ``uriTemplate``.
        """

    def __json__(self) -> dict[str, Any]:
        """::

            definition = template.__json__()

        The definition of the resource template, as
        ``resources/templates/list`` gives it, with its ``uriTemplate``,
        ``name``, ``title``, ``description`` and ``mimeType``, where it has
        them.
        """
        definition: dict[str, Any] = {'uriTemplate': self.uri, 'name': self.name}
        if self.title is not None:
            definition['title'] = self.title
        if self.description is not None:
            definition['description'] = self.description
        definition['mimeType'] = self.mime_type
        return definition

    def match(self, uri: str) -> dict[str, Any] | None:
        """::

            variables = template.match('notes://1')

        The values of the variables of a URI, as
        :meth:`~Pyjo.URL.Template.Pyjo_URL_Template.match` of the template
        gives them, or ``None`` for a URI that the template does not match, or
        whose value is not safe. ::

            files = Pyjo.MCP.ResourceTemplate.new('file:///project/{+path}', lambda path: '')

            # {'path': 'docs/index.md'}
            files.match('file:///project/docs/index.md')

            # None
            files.match('file:///project/../etc/passwd')
        """
        variables = self.template.match(uri)
        if variables is None or (self.safe and not all(map(_safe, variables.values()))):
            return None
        return variables

    def resource(self, uri: str) -> Resource.object | None:
        """::

            resource = template.resource('notes://1')

        The :mod:`Pyjo.MCP.Resource` of a URI, whose function is the one of
        the resource template with the values of the variables of the URI, or
        ``None`` for a URI that :meth:`match` does not match, or whose values
        the function does not take, as without a value of a variable that the
        function requires. ::

            # {'contents': [{'uri': 'notes://1', 'mimeType': 'text/plain', 'text': 'Note 1'}]}
            Pyjo.MCP.ResourceTemplate.new('notes://{number}', note).resource('notes://1').read_p().then(print).wait()
        """
        if (variables := self.match(uri)) is None:
            return None
        try:
            inspect.signature(self.cb).bind(*([None] if self.context else []), **variables)
        except TypeError:
            return None
        except ValueError:
            # A function without a signature, as some builtins, takes what it takes
            pass
        return Resource.new(
            uri,
            functools.partial(self.cb, **variables),
            name=self.name,
            title=self.title,
            description=self.description,
            mime_type=self.mime_type,
            context=self.context,
        )


# A segment .. or an absolute path of Unix or of Windows
_UNSAFE = re.compile(r'(?:^|[/\\])\.\.(?:[/\\]|$)|^[/\\]|^[A-Za-z]:')


def _safe(value: Any) -> bool:
    # Whether a value of a variable, a string, a list or a dict of them, has no segment .., no absolute path and no NUL
    if isinstance(value, dict):
        return all(map(_safe, cast(dict[str, Any], value).values()))
    if isinstance(value, list):
        return all(map(_safe, cast(list[Any], value)))
    return '\0' not in value and not _UNSAFE.search(value)


new = Pyjo_MCP_ResourceTemplate.new
object = Pyjo_MCP_ResourceTemplate
ResourceTemplate = Pyjo_MCP_ResourceTemplate
