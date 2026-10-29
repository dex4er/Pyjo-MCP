"""
Pyjo.MCP.Client - Client of MCP
===============================
::

    from Pyjo.MCP.Client import Client

    client = Client('http://127.0.0.1:3000/mcp')
    tools = client.list_tools()['tools']

    # Or import the module, as in Google Python Style Guide

    import Pyjo.MCP.Client

    client = Pyjo.MCP.Client.new('http://127.0.0.1:3000/mcp', name='calculator-client')
    result = client.call_tool('add', {'a': 1, 'b': 2})
    print(result['structuredContent'])

    # Non-blocking
    client.call_tool_p('add', {'a': 1, 'b': 2}).then(lambda result: print(result['structuredContent'])).wait()

:mod:`Pyjo.MCP.Client` is a client of the Model Context Protocol over
Streamable HTTP, of the revision :data:`Pyjo.MCP.PROTOCOL_VERSION` of the
specification, made with :mod:`Pyjo.UserAgent`. It sends what every request
carries, the ``_meta`` with the revision, the capabilities and the name of the
client, and the headers of MCP made from the body, ``MCP-Protocol-Version``,
``Mcp-Method``, ``Mcp-Name`` and the ``Mcp-Param-{name}`` of the
``x-mcp-header`` of a tool, and reads the response in JSON or in a stream of
events.

It is a client to test a server with and to start from, not an agent: it
caches nothing for the ``ttlMs`` of a result, and leaves the authorization to
the application, which sends its headers with :attr:`~Pyjo_MCP_Client.headers`.

See also
--------

:mod:`Pyjo.MCP.Server`, :mod:`Pyjo.MCP.Tool`, :mod:`Pyjo.UserAgent`,
:mod:`Pyjo.MCP`.

Classes
-------
"""

import Pyjo.EventEmitter
import Pyjo.Exception
import Pyjo.JSON
import Pyjo.JSON.RPC
import Pyjo.Promise
import Pyjo.SSE
import Pyjo.Transaction.HTTP
import Pyjo.UserAgent

# The package of the distribution, imported relatively, as pyright takes the regular package Pyjo of Pyjoyment, which
# hides the namespace that extend_path keeps open
from .. import MCP
from . import Tool

import base64
import builtins
import re
import weakref

from typing import Any, cast


type Anything = builtins.object

# The members of params that the header Mcp-Name has, for each method
_NAMES = {'tools/call': 'name', 'resources/read': 'uri', 'prompts/get': 'name'}

# A value of a header that is plain, without the spaces at its ends that HTTP drops, and one that looks encoded
_BASE64 = re.compile(r'=\?base64\?.*\?=', re.S)
_PLAIN = re.compile(r'[\x21-\x7e](?:[\x20-\x7e]*[\x21-\x7e])?')


class Pyjo_MCP_Client(Pyjo.EventEmitter.object):
    """
    :mod:`Pyjo.MCP.Client` inherits all events and methods from
    :mod:`Pyjo.EventEmitter` and implements the following new ones.

    Events
    ------

    ``invalid_tool`` ::

        @client.on('invalid_tool')
        def invalid_tool(client, definition, e):
            ...

    Emitted for a tool of ``tools/list`` with an ``x-mcp-header`` that the
    specification does not allow, which :meth:`list_tools` leaves out, with the
    definition of the tool and the :mod:`Pyjo.Exception` of
    :mod:`Pyjo.MCP.Tool`. ::

        client.on('invalid_tool', lambda client, definition, e: print(f'{definition["name"]}: {e.message}'))

    ``notification`` ::

        @client.on('notification')
        def notification(client, message):
            ...

    Emitted for every message of the stream of events of a response that is
    not the response itself, as a notification of the progress of a tool. ::

        client.on('notification', lambda client, message: print(message['method']))
    """

    def __init__(
        self,
        url: str = 'http://localhost:3000/mcp',
        ua: Pyjo.UserAgent.object | None = None,
        name: str = 'Pyjo.MCP',
        version: str = '1.0.0',
    ) -> None:
        """::

            client = Pyjo.MCP.Client.new()
            client = Pyjo.MCP.Client.new('http://127.0.0.1:3000/mcp', name='calculator-client', version='2.0.0')
            client = Pyjo.MCP.Client.new('/mcp', ua=t.ua)

        Construct a new :mod:`Pyjo.MCP.Client` object.
        """
        super().__init__()

        self.capabilities: dict[str, Any] = {}
        """::

            capabilities = client.capabilities
            client.capabilities = {'elicitation': {}}

        The capabilities that every request declares, an empty :class:`dict`
        by default.
        """

        self.headers: dict[str, Any] = {}
        """::

            headers = client.headers
            client.headers = {'Authorization': 'Bearer abc123'}

        The headers of HTTP of every request, as the ``Authorization`` of a
        server that requires a bearer token, an empty :class:`dict` by default.
        """

        self.name = name
        """::

            name = client.name
            client.name = 'calculator-client'

        The name of the client, ``Pyjo.MCP`` by default.
        """

        self.protocol_version = MCP.PROTOCOL_VERSION
        """::

            version = client.protocol_version
            client.protocol_version = '2026-07-28'

        The revision of the specification of the requests,
        :data:`Pyjo.MCP.PROTOCOL_VERSION` by default. A server that rejects it
        with the error ``-32022`` gets the request once more, of the newest
        revision that both support, which the client keeps for the next
        requests.
        """

        self.tools: dict[str, Tool.object] = {}
        """::

            tools = client.tools

        The :mod:`Pyjo.MCP.Tool` objects of the tools of the last
        :meth:`list_tools`, by their names, whose ``x-mcp-header`` give the
        headers ``Mcp-Param-{name}`` of their calls.
        """

        self.url = url
        """::

            url = client.url
            client.url = 'http://127.0.0.1:3000/mcp'

        The URL of the endpoint of MCP, ``http://localhost:3000/mcp`` by
        default.
        """

        self.version = version
        """::

            version = client.version
            client.version = '2.0.0'

        The version of the client, ``1.0.0`` by default.
        """

        self._id = 0
        self._ua = ua
        # The response of a stream of events, which the parser of the content takes from the body
        self._responses: weakref.WeakKeyDictionary[Pyjo.Transaction.HTTP.object, dict[str, Any]] = (
            weakref.WeakKeyDictionary()
        )

    @property
    def ua(self) -> Pyjo.UserAgent.object:
        """::

            ua = client.ua
            client.ua = Pyjo.UserAgent.new()

        The :mod:`Pyjo.UserAgent` of the requests, a new one by default.
        """
        if self._ua is None:
            self._ua = Pyjo.UserAgent.new()
        return self._ua

    @ua.setter
    def ua(self, value: Pyjo.UserAgent.object) -> None:
        self._ua = value

    def build_notification(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """::

            notification = client.build_notification('notifications/cancelled', {'requestId': 1})

        Build a notification of JSON-RPC with the method and its parameters.
        """
        return {'jsonrpc': '2.0', 'method': method, 'params': params or {}}

    def build_request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """::

            request = client.build_request('tools/call', {'name': 'add', 'arguments': {'a': 1, 'b': 2}})

        Build a request of JSON-RPC with the method and its parameters, the
        next ``id`` of the client, and the ``_meta`` that every request
        carries, over the ``_meta`` of the parameters.
        """
        params = params or {}
        meta = {
            **cast(dict[str, Any], params.get('_meta') or {}),
            MCP.META_CLIENT_CAPABILITIES: self.capabilities,
            MCP.META_CLIENT_INFO: {'name': self.name, 'version': self.version},
            MCP.META_PROTOCOL_VERSION: self.protocol_version,
        }
        self._id += 1
        return {**self.build_notification(method, {**params, '_meta': meta}), 'id': self._id}

    def build_tx(self, request: dict[str, Any]) -> Pyjo.Transaction.HTTP.object:
        """::

            tx = client.build_tx(request)

        Build the :mod:`Pyjo.Transaction.HTTP` of a request or a notification,
        a POST to :attr:`url` with the headers of MCP made from the body, which
        reads a response in a stream of events too, as :meth:`send_request`
        does, so that a test sends what the client sends. ::

            # The request without its header Mcp-Name
            tx = client.build_tx(client.build_request('tools/call', {'name': 'add', 'arguments': {}}))
            tx.req.headers.remove('Mcp-Name')
            t.request_ok(tx).status_is(400)
        """
        tx = self.ua.build_tx('POST', self.url, self._headers(request), json=request)
        id = request.get('id')

        def sse(content: Any, event: Any = None) -> None:
            if event and (message := _message(event)) is not None:
                if _is_response(message, id):
                    self._responses[tx] = message
                else:
                    self.emit('notification', message)

        tx.res.content.on('sse', sse)
        return tx

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None, /) -> dict[str, Any]:
        """::

            result = client.call_tool('greet')
            result = client.call_tool('greet', {'name': 'Pyjo'})

        Call a tool with its arguments and return its result, or raise the
        :class:`Pyjo.JSON.RPC.Error` of the response. A result with
        ``isError`` is a result, of an error of the execution of the tool. ::

            result = client.call_tool('divide', {'a': 1, 'b': 0})
            if result['isError']:
                print(result['content'][0]['text'])
        """
        return _result(self.send_request(self._call_tool(name, arguments)))

    def call_tool_p(self, name: str, arguments: dict[str, Any] | None = None, /) -> Pyjo.Promise.object:
        """::

            promise = client.call_tool_p('greet', {'name': 'Pyjo'})

        Same as :meth:`call_tool`, but returns a :mod:`Pyjo.Promise` of the
        result instead of blocking.
        """
        return self.send_request_p(self._call_tool(name, arguments)).then(_result)

    def discover(self) -> dict[str, Any]:
        """::

            result = client.discover()

        Discover the revisions, the capabilities and the instructions of the
        server with ``server/discover``.
        """
        return _result(self.send_request(self.build_request('server/discover')))

    def discover_p(self) -> Pyjo.Promise.object:
        """::

            promise = client.discover_p()

        Same as :meth:`discover`, but returns a :mod:`Pyjo.Promise` of the
        result instead of blocking.
        """
        return self.send_request_p(self.build_request('server/discover')).then(_result)

    def list_tools(self) -> dict[str, Any]:
        """::

            result = client.list_tools()

        List the tools of the server with ``tools/list``, and keep them in
        :attr:`tools`, which the calls take the headers of their arguments
        from. A tool whose ``x-mcp-header`` the specification does not allow
        is left out of the result and of :attr:`tools`, as the specification
        requires, with the event ``invalid_tool``. ::

            for tool in client.list_tools()['tools']:
                print(tool['name'], tool.get('description'))
        """
        return _result(self.send_request(self.build_request('tools/list')))

    def list_tools_p(self) -> Pyjo.Promise.object:
        """::

            promise = client.list_tools_p()

        Same as :meth:`list_tools`, but returns a :mod:`Pyjo.Promise` of the
        result instead of blocking.
        """
        return self.send_request_p(self.build_request('tools/list')).then(_result)

    def read_response(self, tx: Pyjo.Transaction.HTTP.object, request: dict[str, Any]) -> dict[str, Any] | None:
        """::

            response = client.read_response(tx, request)

        Read the response of a request from its transaction of
        :meth:`build_tx`, once the transaction is done, as
        :meth:`send_request` does: from JSON or from a stream of events, and
        with the tools of a result of ``tools/list`` kept in :attr:`tools`,
        without the ones of the event ``invalid_tool``. ::

            request = client.build_request('tools/list')
            tx = client.ua.start(client.build_tx(request))
            print(client.read_response(tx, request)['result']['tools'])
        """
        response = self._read_response(tx, request)
        if request.get('method') == 'tools/list' and isinstance(result := _object(response).get('result'), dict):
            response = {**_object(response), 'result': self._tools(cast(dict[str, Any], result))}
        return response

    def send_request(self, request: dict[str, Any]) -> dict[str, Any] | None:
        """::

            response = client.send_request(request)

        Send a request or a notification and return the response, or ``None``
        for one that the server accepted without a response, ``202
        Accepted``. A response of HTTP without one of JSON-RPC fails with a
        :mod:`Pyjo.Exception`, with the text of an error in plain text, as a
        server of an older revision tells the revisions that it supports. ::

            response = client.send_request(client.build_request('tools/list'))
            print(response['result']['tools'])
        """
        response = self.read_response(self.ua.start(self.build_tx(request)), request)
        if self._renegotiate(request, response):
            response = self.read_response(self.ua.start(self.build_tx(request)), request)
        return response

    def send_request_p(self, request: dict[str, Any]) -> Pyjo.Promise.object:
        """::

            promise = client.send_request_p(request)

        Same as :meth:`send_request`, but returns a :mod:`Pyjo.Promise` of the
        response instead of blocking.
        """

        def response(tx: Pyjo.Transaction.HTTP.object) -> dict[str, Any] | None:
            return self.read_response(tx, request)

        def start() -> Pyjo.Promise.object:
            return self.ua.start_p(self.build_tx(request)).then(response)

        def renegotiate(response: Any = None) -> Any:
            return start() if self._renegotiate(request, response) else response

        return start().then(renegotiate)

    # TODO: get_prompt, list_prompts, list_resources, read_resource and listen of MCP::Client, and the options
    # input_responses and request_state of its call_tool, with the prompts, the resources, subscriptions/listen and the
    # multi round-trip requests of the server

    def _call_tool(self, name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
        return self.build_request('tools/call', {'name': name, 'arguments': arguments or {}})

    def _headers(self, request: dict[str, Any]) -> dict[str, Any]:
        # The headers of MCP, which mirror the body, as the server checks them
        method = request.get('method')
        params = _object(request.get('params'))
        meta = _object(params.get('_meta'))
        headers = {
            **self.headers,
            'Accept': 'application/json, text/event-stream',
            'MCP-Protocol-Version': meta.get(MCP.META_PROTOCOL_VERSION, self.protocol_version),
            'Mcp-Method': method,
        }
        if isinstance(method, str) and (key := _NAMES.get(method)) is not None:
            headers['Mcp-Name'] = _encode(params.get(key, ''))
        if method == 'tools/call' and (tool := self.tools.get(params.get('name', ''))) is not None:
            for name, path, _ in tool.header_params:
                if (value := _value(params.get('arguments'), path)) is not None:
                    headers[f'Mcp-Param-{name}'] = _encode(value)
        return headers

    def _renegotiate(self, request: dict[str, Any], response: Any) -> bool:
        # The newest revision that both support, for one more request, after the error of an unsupported one
        error = _object(_object(response).get('error'))
        if error.get('code') != MCP.UNSUPPORTED_PROTOCOL_VERSION:
            return False
        supported = _object(error.get('data')).get('supported')
        supported = cast(list[Any], supported) if isinstance(supported, list) else []
        version = next((version for version in MCP.SUPPORTED_VERSIONS if version in supported), None)
        if version is None or version == self.protocol_version:
            return False
        self.protocol_version = version
        _object(_object(request.get('params')).get('_meta'))[MCP.META_PROTOCOL_VERSION] = version
        return True

    def _read_response(self, tx: Pyjo.Transaction.HTTP.object, request: dict[str, Any]) -> dict[str, Any] | None:
        # The response of a stream of events, which the parser of the content takes from the body
        res = tx.res
        if (response := self._responses.pop(tx, None)) is not None:
            return response
        if res.code == 202:
            return None

        # The events that stay in the body of a chunked stream, which the parser of the content does not parse
        if (res.headers.content_type or '').startswith('text/event-stream'):
            buffer = bytearray(res.body)
            while (event := Pyjo.SSE.parse_event(buffer)) is not None:
                if (message := _message(event)) is None:
                    continue
                if _is_response(message, request.get('id')):
                    return message
                self.emit('notification', message)

        if isinstance(response := res.json(), dict):
            return cast(dict[str, Any], response)

        # The text of the error, as a server of an older revision of MCP tells the revisions it supports in plain text
        error = tx.error or {}
        message = f'{self.url}: {error.get("code") or ""} {error.get("message", "No response")}'.strip()
        if (res.headers.content_type or '').startswith('text/plain') and (body := res.text.strip()):
            message += f': {body}'
        raise Pyjo.Exception.new(message)

    def _tools(self, result: dict[str, Any]) -> dict[str, Any]:
        # The tools whose x-mcp-header the specification allows, as a client excludes the others
        def nothing(**arguments: Any) -> None:
            return None

        tools: dict[str, Tool.object] = {}
        definitions: list[Any] = []
        for definition in cast(list[Any], result.get('tools') or []):
            definition_ = _object(definition)
            try:
                tool = Tool.new(
                    nothing,
                    name=definition_.get('name'),
                    input_schema=definition_.get('inputSchema') or {'type': 'object'},
                )
            except Pyjo.Exception.object as e:
                self.emit('invalid_tool', definition, e)
                continue
            tools[tool.name] = tool
            definitions.append(definition)
        self.tools = tools
        return {**result, 'tools': definitions}


def _encode(value: Any) -> str:
    # A value of a header, plain ASCII, or Base64 of UTF-8 with the sentinel of MCP
    text = value if isinstance(value, str) else Pyjo.JSON.to_json(value)
    if _PLAIN.fullmatch(text) and not _BASE64.fullmatch(text):
        return text
    return f'=?base64?{base64.b64encode(text.encode()).decode()}?='


def _is_response(message: dict[str, Any], id: Any) -> bool:
    return id is not None and message.get('id') == id and 'method' not in message


def _message(event: Any) -> dict[str, Any] | None:
    # The message of JSON-RPC of an event, or None
    try:
        message = Pyjo.JSON.decode_json(_object(event).get('text') or '')
    except ValueError:
        return None
    return cast(dict[str, Any], message) if isinstance(message, dict) else None


def _object(value: Anything) -> dict[str, Any]:
    # An object of JSON, or an empty one for another value
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _result(response: Any) -> dict[str, Any]:
    # The result of a response, or the error of JSON-RPC that it has
    if response is None:
        raise Pyjo.Exception.new('No response')
    if 'error' in (response_ := _object(response)):
        raise Pyjo.JSON.RPC.Error.from_json(response_['error'])
    return _object(response_.get('result'))


def _value(arguments: Any, path: list[str]) -> Any:
    # The value of an argument at the path of its properties
    for key in path:
        if not isinstance(arguments, dict):
            return None
        arguments = cast(dict[str, Any], arguments).get(key)
    return arguments


new = Pyjo_MCP_Client.new
object = Pyjo_MCP_Client
Client = Pyjo_MCP_Client
