"""
Pyjo.MCP.Test - Testing servers of MCP
======================================
::

    from Pyjo.File import curfile
    from Pyjo.MCP.Test import Test
    from Pyjo.Test import *

    t = Test(curfile().dirname().sibling('calculator.py'))

    t.discover_ok().status_is(200).result_is('/capabilities', {'tools': {}})
    t.list_tools_ok().status_is(200).tool_exists('divide')
    t.call_ok('divide', a=7, b=2).status_is(200).structured_content_is(3.5).is_error_is(False)
    t.call_ok('divide', {'a': 1, 'b': 0}).is_error_is(True).text_content_is('Division by zero')
    t.call_ok('power').error_code_is(-32602).error_message_is('Unknown tool: power')

    # Or import the module, as in Google Python Style Guide

    import Pyjo.MCP.Test

    t = Pyjo.MCP.Test.new(curfile().dirname().sibling('calculator.py'))

    # A request without its header Mcp-Name
    params = {'name': 'add', 'arguments': {'a': 1, 'b': 2}}
    t.mcp_ok('tools/call', params, headers={'Mcp-Name': None}).status_is(400)
    t.error_message_is('Header mismatch: Missing Mcp-Name header')

    done_testing()

:mod:`Pyjo.MCP.Test` is :mod:`Pyjo.Test.Pyjo` for the servers of the Model
Context Protocol, with the requests of :mod:`Pyjo.MCP.Client`: the envelope of
JSON-RPC, the ``_meta`` of the client and the headers of MCP made from the
body, as a client sends them, and assertions of the response of JSON-RPC,
which the client reads from JSON or from a stream of events.

The arguments of a tool go as a :class:`dict` or as keyword arguments of
:meth:`~Pyjo_MCP_Test.call_ok`, after the name of the tool, which is only
positional, so that no argument of a tool clashes with it.

See also
--------

:mod:`Pyjo.MCP.Client`, :mod:`Pyjo.MCP.Server`, :mod:`Pyjo.Test.Pyjo`,
:mod:`Pyjo.MCP`.

Classes
-------
"""

import Pyjo.Exception
import Pyjo.JSON
import Pyjo.JSON.Pointer
import Pyjo.Test
import Pyjo.Test.Pyjo

# The package of the distribution, imported relatively, as pyright takes the regular package Pyjo of Pyjoyment, which
# hides the namespace that extend_path keeps open
from . import Client

from typing import Any, Self, cast


# pytest leaves the frames of this module out of the traceback of a failed test, as those of Pyjo.Test.Pyjo
__tracebackhide__ = Pyjo.Test.__tracebackhide__


class Pyjo_MCP_Test(Pyjo.Test.Pyjo.object):
    """
    :mod:`Pyjo.MCP.Test` inherits all attributes and methods from
    :mod:`Pyjo.Test.Pyjo` and implements the following new ones.
    """

    def __init__(self, app: Any = None, config: dict[str, Any] | None = None, /) -> None:
        """::

            t = Pyjo.MCP.Test.new()
            t = Pyjo.MCP.Test.new(Pyjo.File.new('/path/to/server.py'))
            t = Pyjo.MCP.Test.new(app, {'foo': 'bar'})

        Construct a new :mod:`Pyjo.MCP.Test` object, with the application of
        :meth:`Pyjo.Test.Pyjo.Pyjo_Test_Pyjo.__init__`.
        """
        self._client: Client.object | None = None
        super().__init__(app, config)

        self.notifications: list[dict[str, Any]] = []
        """::

            notifications = t.notifications

        The notifications of JSON-RPC that the server sent before the
        response of the last request, in its stream of events, as the
        progress of a tool. ::

            params = {'name': 'count', 'arguments': {'to': 3}}
            t.mcp_ok('tools/call', params, meta={'progressToken': 'count-1'}).status_is(200)
            is_ok(t.notifications[0]['method'], 'notifications/progress', 'progress')
        """

        self.response: dict[str, Any] | None = None
        """::

            response = t.response
            t.response = {'jsonrpc': '2.0', 'id': 1, 'result': {}}

        The response of JSON-RPC of the last request, from JSON or from a
        stream of events, which the assertions of the response test, or
        ``None`` for none. ::

            # More specific tests
            is_ok(t.response['result']['content'][0]['type'], 'text', 'right type')
        """

    @property
    def client(self) -> Client.object:
        """::

            client = t.client
            t.client = Pyjo.MCP.Client.new('/api/mcp')

        The :mod:`Pyjo.MCP.Client` of the requests, of the endpoint ``/mcp``
        by default, which sends them with :attr:`~Pyjo.Test.Pyjo.Pyjo_Test_Pyjo.ua`. ::

            # Another endpoint, client and capabilities
            t.client.url = '/api/mcp'
            t.client.name = 'ExampleClient'
            t.client.capabilities = {'elicitation': {}}
        """
        if self._client is None:
            self._client = Client.new('/mcp', ua=self.ua)
        return self._client

    @client.setter
    def client(self, value: Client.object) -> None:
        self._client = value

    def call_ok(self, tool: str, arguments: dict[str, Any] | None = None, /, **kwargs: Any) -> Self:
        """::

            t = t.call_ok('greet')
            t = t.call_ok('greet', name='Pyjo')
            t = t.call_ok('greet', {'name': 'Pyjo'})

        Call a tool with ``tools/call``, with its arguments as a :class:`dict`
        or as keyword arguments, and check for transport errors. The headers
        ``Mcp-Param-{name}`` of the ``x-mcp-header`` of a tool come from the
        tools of the last :meth:`list_tools_ok`, as a client knows them from
        its definition. ::

            t.list_tools_ok().call_ok('execute_sql', region='eu', query='SELECT 1').status_is(200)
        """
        return self.mcp_ok('tools/call', {'name': tool, 'arguments': {**(arguments or {}), **kwargs}})

    def discover_ok(self, *, headers: dict[str, Any] | None = None, meta: dict[str, Any] | None = None) -> Self:
        """::

            t = t.discover_ok()
            t = t.discover_ok(headers={'MCP-Protocol-Version': '2025-11-25'})

        Discover the server with ``server/discover``, and check for transport
        errors, with the headers and the ``_meta`` of :meth:`mcp_ok`.
        """
        return self.mcp_ok('server/discover', headers=headers, meta=meta)

    def error_code_is(self, code: int, desc: str | None = None) -> Self:
        """::

            t = t.error_code_is(-32602)
            t = t.error_code_is(-32602, 'invalid params')

        Check the code of the error of JSON-RPC of the response.
        """
        return self.test('is', self._response_value('/error/code'), code, desc or f'error code is {code}')

    def error_is(self, *args: Any) -> Self:
        """::

            t = t.error_is({'code': -32601, 'message': 'Method not found'})
            t = t.error_is('/data/supported', ['2026-07-28'])
            t = t.error_is('/code', -32601, 'right code')

        Check the value of the error of JSON-RPC of the response, at a JSON
        Pointer of :mod:`Pyjo.JSON.Pointer`, which defaults to the whole
        error.
        """
        p, data, desc = _args(args)
        return self.test('is_deeply', self._response_value(f'/error{p}'), data, desc or f'exact match for error "{p}"')

    def error_message_is(self, message: str, desc: str | None = None) -> Self:
        """::

            t = t.error_message_is('Unknown tool: power')
            t = t.error_message_is('Unknown tool: power', 'right message')

        Check the message of the error of JSON-RPC of the response.
        """
        return self.test('is', self._response_value('/error/message'), message, desc or 'exact match for error message')

    def error_message_like(self, regex: Any, desc: str | None = None) -> Self:
        """::

            t = t.error_message_like(re.compile(r'^Unknown tool'))
            t = t.error_message_like(re.compile(r'^Unknown tool'), 'right message')

        Check the message of the error of JSON-RPC of the response for a
        similar match.
        """
        return self.test(
            'like', self._response_value('/error/message'), regex, desc or 'similar match for error message'
        )

    def get_prompt_ok(self, name: str, arguments: dict[str, Any] | None = None, /, **kwargs: Any) -> Self:
        """::

            t = t.get_prompt_ok('review')
            t = t.get_prompt_ok('review', code='x = 1')
            t = t.get_prompt_ok('review', {'code': 'x = 1'})

        Get the messages of a prompt with ``prompts/get``, with its arguments
        as a :class:`dict` or as keyword arguments, and check for transport
        errors. ::

            t.get_prompt_ok('review', code='x = 1').status_is(200).text_content_like(r'x = 1')
        """
        return self.mcp_ok('prompts/get', {'name': name, 'arguments': {**(arguments or {}), **kwargs}})

    def is_error_is(self, value: bool, desc: str | None = None) -> Self:
        """::

            t = t.is_error_is(False)
            t = t.is_error_is(True, 'error of the tool')

        Check ``isError`` of the result of a tool, which is true for an error
        of the execution of the tool, as its arguments that the
        ``inputSchema`` does not validate.
        """
        return self.test(
            'is', self._response_value('/result/isError'), value, desc or f'isError is {Pyjo.JSON.to_json(value)}'
        )

    def list_prompts_ok(self, *, headers: dict[str, Any] | None = None, meta: dict[str, Any] | None = None) -> Self:
        """::

            t = t.list_prompts_ok()

        List the prompts with ``prompts/list``, and check for transport
        errors, with the headers and the ``_meta`` of :meth:`mcp_ok`.
        """
        return self.mcp_ok('prompts/list', headers=headers, meta=meta)

    def list_resources_ok(self, *, headers: dict[str, Any] | None = None, meta: dict[str, Any] | None = None) -> Self:
        """::

            t = t.list_resources_ok()

        List the resources with ``resources/list``, and check for transport
        errors, with the headers and the ``_meta`` of :meth:`mcp_ok`.
        """
        return self.mcp_ok('resources/list', headers=headers, meta=meta)

    def list_tools_ok(self, *, headers: dict[str, Any] | None = None, meta: dict[str, Any] | None = None) -> Self:
        """::

            t = t.list_tools_ok()

        List the tools with ``tools/list``, and check for transport errors,
        with the headers and the ``_meta`` of :meth:`mcp_ok`. The client keeps
        the tools, whose ``x-mcp-header`` give the headers of the arguments of
        :meth:`call_ok`.
        """
        return self.mcp_ok('tools/list', headers=headers, meta=meta)

    def listen_ok(
        self,
        notifications: dict[str, Any] | None = None,
        /,
        *,
        headers: dict[str, Any] | None = None,
        meta: dict[str, Any] | None = None,
    ) -> Self:
        """::

            t = t.listen_ok({'toolsListChanged': True})
            t = t.listen_ok({'resourceSubscriptions': ['file:///project/README.md']})

        Open a subscription with ``subscriptions/listen``, for the
        notifications that the filter asks for, with the headers and the
        ``_meta`` of :meth:`mcp_ok`, and check that its stream of events is
        established, as :meth:`~Pyjo.Test.Pyjo.Pyjo_Test_Pyjo.post_sse_ok`
        does. Its messages are the events of the stream, which
        :meth:`notification_ok` waits for, and
        :meth:`~Pyjo.Test.Pyjo.Pyjo_Test_Pyjo.sse_finish_ok` closes it. ::

            t.listen_ok({'toolsListChanged': True})
            t.notification_ok().notification_is('/method', 'notifications/subscriptions/acknowledged')
            server.notify_list_changed('tools')
            t.notification_ok().notification_is('/method', 'notifications/tools/list_changed')
            t.sse_finish_ok()
        """
        _, tx = self._build_tx('subscriptions/listen', {'notifications': notifications or {}}, headers, None, meta)
        self.response = None
        return self._sse_ok(tx, f'subscriptions/listen {self.client.url}')

    def mcp_ok(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        /,
        *,
        headers: dict[str, Any] | None = None,
        id: Any = None,
        meta: dict[str, Any] | None = None,
    ) -> Self:
        """::

            t = t.mcp_ok('tools/list')
            t = t.mcp_ok('tools/call', {'name': 'add', 'arguments': {'a': 1, 'b': 2}})
            t = t.mcp_ok('tools/call', {'name': 'add', 'arguments': {}}, headers={'Mcp-Name': 'foo'})
            t = t.mcp_ok('server/discover', id='discover-1', meta={'io.modelcontextprotocol/clientInfo': None})

        Send a request of MCP with the method and its parameters, as
        :mod:`Pyjo.MCP.Client` builds it, and check for transport errors. The
        ``id`` replaces the one of the client, a value of ``meta`` replaces
        the one of its key in the ``_meta`` of the request, before the headers
        are made from the body, and a value of ``headers`` replaces the header
        of its name after it, ``None`` dropping either, so that a test sends
        what a client must not. ::

            # A revision of the specification that the server does not support
            t.mcp_ok('tools/list', meta={'io.modelcontextprotocol/protocolVersion': '1900-01-01'}).status_is(400)
            t.error_code_is(-32022)
        """
        client = self.client
        request, tx = self._build_tx(method, params, headers, id, meta)
        notifications: list[dict[str, Any]] = []

        def notification(client: Client.object, message: dict[str, Any]) -> None:
            notifications.append(message)

        client.on('notification', notification)
        try:
            self.request_ok(tx)
            try:
                self.response = client.read_response(tx, request)
            except Pyjo.Exception.object:
                self.response = None
        finally:
            client.unsubscribe('notification', notification)
        self.notifications = notifications
        return self

    def notification_is(self, *args: Any) -> Self:
        """::

            t = t.notification_is({'jsonrpc': '2.0', 'method': 'notifications/tools/list_changed', 'params': {}})
            t = t.notification_is('/method', 'notifications/resources/updated')
            t = t.notification_is('/params/uri', 'file:///project/README.md', 'right resource')

        Check the value of the message of JSON-RPC of the last event of the
        subscription of :meth:`listen_ok`, a notification, or the response at
        its end, at a JSON Pointer of :mod:`Pyjo.JSON.Pointer`, which defaults
        to the whole message.
        """
        p, data, desc = _args(args)
        got = Pyjo.JSON.Pointer.new(_message(self.sse)).get(p)
        return self.test('is_deeply', got, data, desc or f'exact match for notification "{p}"')

    def notification_ok(self, desc: str | None = None) -> Self:
        """::

            t = t.notification_ok()
            t = t.notification_ok('got a notification')

        Wait for the next message of the subscription of :meth:`listen_ok`, as
        :meth:`~Pyjo.Test.Pyjo.Pyjo_Test_Pyjo.sse_ok` waits for the next event.
        """
        return self.sse_ok(desc or 'notification received')

    def prompt_exists(self, name: str, desc: str | None = None) -> Self:
        """::

            t = t.prompt_exists('review')
            t = t.prompt_exists('review', 'has a review')

        Check if the result of ``prompts/list`` has a prompt of the name.
        """
        return self.test('ok', self._listed('prompts', 'name', name) is not None, desc or f'has prompt "{name}"')

    def prompt_exists_not(self, name: str, desc: str | None = None) -> Self:
        """::

            t = t.prompt_exists_not('summary')
            t = t.prompt_exists_not('summary', 'no summary')

        Opposite of :meth:`prompt_exists`.
        """
        return self.test('ok', self._listed('prompts', 'name', name) is None, desc or f'has no prompt "{name}"')

    def prompt_is(self, name: str, *args: Any) -> Self:
        """::

            t = t.prompt_is('review', {'name': 'review', 'arguments': []})
            t = t.prompt_is('review', '/arguments/0/name', 'code')
            t = t.prompt_is('review', '/arguments/0/required', True, 'code required')

        Check the value of the definition of a prompt of the result of
        ``prompts/list``, at a JSON Pointer of :mod:`Pyjo.JSON.Pointer`, which
        defaults to the whole definition.
        """
        p, data, desc = _args(args)
        got = Pyjo.JSON.Pointer.new(self._listed('prompts', 'name', name)).get(p)
        return self.test('is_deeply', got, data, desc or f'exact match for prompt "{name}" "{p}"')

    def read_resource_ok(
        self, uri: str, *, headers: dict[str, Any] | None = None, meta: dict[str, Any] | None = None
    ) -> Self:
        """::

            t = t.read_resource_ok('file:///project/README.md')

        Read the contents of a resource with ``resources/read``, and check for
        transport errors, with the headers and the ``_meta`` of
        :meth:`mcp_ok`. ::

            t.read_resource_ok('file:///project/README.md').status_is(200).text_content_like(r'^# ')
        """
        return self.mcp_ok('resources/read', {'uri': uri}, headers=headers, meta=meta)

    def resource_exists(self, uri: str, desc: str | None = None) -> Self:
        """::

            t = t.resource_exists('file:///project/README.md')
            t = t.resource_exists('file:///project/README.md', 'has a README')

        Check if the result of ``resources/list`` has a resource of the URI.
        """
        return self.test('ok', self._listed('resources', 'uri', uri) is not None, desc or f'has resource "{uri}"')

    def resource_exists_not(self, uri: str, desc: str | None = None) -> Self:
        """::

            t = t.resource_exists_not('file:///etc/passwd')
            t = t.resource_exists_not('file:///etc/passwd', 'no secrets')

        Opposite of :meth:`resource_exists`.
        """
        return self.test('ok', self._listed('resources', 'uri', uri) is None, desc or f'has no resource "{uri}"')

    def resource_is(self, uri: str, *args: Any) -> Self:
        """::

            t = t.resource_is('file:///project/README.md', {'uri': 'file:///project/README.md', 'name': 'readme'})
            t = t.resource_is('file:///project/README.md', '/mimeType', 'text/markdown')
            t = t.resource_is('file:///project/README.md', '/name', 'readme', 'right name')

        Check the value of the definition of a resource of the result of
        ``resources/list``, at a JSON Pointer of :mod:`Pyjo.JSON.Pointer`,
        which defaults to the whole definition.
        """
        p, data, desc = _args(args)
        got = Pyjo.JSON.Pointer.new(self._listed('resources', 'uri', uri)).get(p)
        return self.test('is_deeply', got, data, desc or f'exact match for resource "{uri}" "{p}"')

    def response_is(self, *args: Any) -> Self:
        """::

            t = t.response_is({'jsonrpc': '2.0', 'id': 1, 'result': {}})
            t = t.response_is('/id', 1)
            t = t.response_is('/id', 1, 'right id')

        Check the value of the response of JSON-RPC, at a JSON Pointer of
        :mod:`Pyjo.JSON.Pointer`, which defaults to the whole response.
        """
        p, data, desc = _args(args)
        return self.test('is_deeply', self._response_value(p), data, desc or f'exact match for response "{p}"')

    def result_is(self, *args: Any) -> Self:
        """::

            t = t.result_is({'resultType': 'complete', 'tools': []})
            t = t.result_is('/content/0/text', 'Hello, Pyjo!')
            t = t.result_is('/content/0/text', 'Hello, Pyjo!', 'right text')

        Check the value of the result of the response, at a JSON Pointer of
        :mod:`Pyjo.JSON.Pointer`, which defaults to the whole result.
        """
        p, data, desc = _args(args)
        return self.test(
            'is_deeply', self._response_value(f'/result{p}'), data, desc or f'exact match for result "{p}"'
        )

    def structured_content_is(self, *args: Any) -> Self:
        """::

            t = t.structured_content_is(3.5)
            t = t.structured_content_is('/temperature', 21.5)
            t = t.structured_content_is('/temperature', 21.5, 'right temperature')

        Check the value of the ``structuredContent`` of the result of a tool,
        at a JSON Pointer of :mod:`Pyjo.JSON.Pointer`, which defaults to the
        whole value.
        """
        p, data, desc = _args(args)
        got = self._response_value(f'/result/structuredContent{p}')
        return self.test('is_deeply', got, data, desc or f'exact match for structured content "{p}"')

    def text_content_is(self, text: str, desc: str | None = None) -> Self:
        """::

            t = t.text_content_is('Hello, Pyjo!')
            t = t.text_content_is('Hello, Pyjo!', 'right text')

        Check the text of the result: of the ``content`` of a tool, of the
        ``content`` of the messages of a prompt, or of the ``contents`` of a
        resource, its items of the type ``text`` joined. ::

            t.get_prompt_ok('review', code='x = 1').text_content_is('Review this Python code:\\nx = 1')
            t.read_resource_ok('file:///project/README.md').text_content_is('# Project')
        """
        return self.test('is', self._content_text(), text, desc or 'exact match for text content')

    def text_content_like(self, regex: Any, desc: str | None = None) -> Self:
        """::

            t = t.text_content_like(re.compile(r'/name: Missing property'))
            t = t.text_content_like(re.compile(r'/name: Missing property'), 'right error')

        Check the text of the result, as :meth:`text_content_is` takes it, for
        a similar match.
        """
        return self.test('like', self._content_text(), regex, desc or 'similar match for text content')

    def tool_exists(self, name: str, desc: str | None = None) -> Self:
        """::

            t = t.tool_exists('greet')
            t = t.tool_exists('greet', 'has a greeting')

        Check if the result of ``tools/list`` has a tool of the name.
        """
        return self.test('ok', self._listed('tools', 'name', name) is not None, desc or f'has tool "{name}"')

    def tool_exists_not(self, name: str, desc: str | None = None) -> Self:
        """::

            t = t.tool_exists_not('power')
            t = t.tool_exists_not('power', 'no power')

        Opposite of :meth:`tool_exists`.
        """
        return self.test('ok', self._listed('tools', 'name', name) is None, desc or f'has no tool "{name}"')

    def tool_is(self, name: str, *args: Any) -> Self:
        """::

            t = t.tool_is('greet', {'name': 'greet', 'inputSchema': {'type': 'object'}})
            t = t.tool_is('greet', '/description', 'Greet somebody by name.')
            t = t.tool_is('greet', '/inputSchema/required', ['name'], 'right required arguments')

        Check the value of the definition of a tool of the result of
        ``tools/list``, at a JSON Pointer of :mod:`Pyjo.JSON.Pointer`, which
        defaults to the whole definition.
        """
        p, data, desc = _args(args)
        got = Pyjo.JSON.Pointer.new(self._listed('tools', 'name', name)).get(p)
        return self.test('is_deeply', got, data, desc or f'exact match for tool "{name}" "{p}"')

    def _build_tx(
        self,
        method: str,
        params: dict[str, Any] | None,
        headers: dict[str, Any] | None,
        id: Any,
        meta: dict[str, Any] | None,
    ) -> tuple[dict[str, Any], Any]:
        # A request of the client and its transaction, with the id, the _meta and the headers that replace its own
        client = self.client
        client.ua = self.ua
        request = client.build_request(method, params)
        if id is not None:
            request['id'] = id
        request_meta = cast(dict[str, Any], request['params']['_meta'])
        for key, value in (meta or {}).items():
            if value is None:
                request_meta.pop(key, None)
            else:
                request_meta[key] = value

        tx = client.build_tx(request)
        for name, value in (headers or {}).items():
            if value is None:
                tx.req.headers.remove(name)
            else:
                tx.req.headers.header(name, value)
        return request, tx

    def _response_value(self, p: str) -> Any:
        return Pyjo.JSON.Pointer.new(self.response).get(p)

    def _content_text(self) -> str | None:
        # The text of the content of a tool, of the messages of a prompt, or of the contents of a resource, or None
        result = _object(self._response_value('/result'))
        if isinstance(content := result.get('content'), list):
            items = [_object(item) for item in cast(list[Any], content)]
        elif isinstance(messages := result.get('messages'), list):
            items = [_object(_object(message).get('content')) for message in cast(list[Any], messages)]
        elif isinstance(contents := result.get('contents'), list):
            items = [{'type': 'text', **_object(item)} for item in cast(list[Any], contents) if 'text' in _object(item)]
        else:
            return None
        return ''.join(str(item.get('text', '')) for item in items if item.get('type') == 'text')

    def _listed(self, kind: str, key: str, value: str) -> dict[str, Any] | None:
        # The definition of the result of a list, of the tools, the prompts or the resources, by its name or its URI
        listed = self._response_value(f'/result/{kind}')
        if not isinstance(listed, list):
            return None
        return next((item for item in map(_object, cast(list[Any], listed)) if item.get(key) == value), None)


def _args(args: tuple[Any, ...]) -> tuple[str, Any, str | None]:
    # The JSON Pointer, the value and the description of an assertion, as json_is of Pyjo.Test.Pyjo takes them
    values = list(args)
    if len(values) > 1:
        return values[0], values[1], values[2] if len(values) > 2 else None
    return '', values[0] if len(values) else None, None


def _message(event: Any) -> Any:
    # The message of JSON-RPC of an event, or None
    try:
        return Pyjo.JSON.decode_json(_object(event).get('text') or '')
    except ValueError:
        return None


def _object(value: Any) -> dict[str, Any]:
    # An object of JSON, or an empty one for another value
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


new = Pyjo_MCP_Test.new
object = Pyjo_MCP_Test
Test = Pyjo_MCP_Test
