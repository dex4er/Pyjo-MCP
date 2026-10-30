"""
Pyjo.MCP.Server - Server of MCP
===============================
::

    from Pyjo.MCP.Server import Server

    server = Server(name='calculator', version='1.0.0')

    @server.tool
    def add(a: int, b: int) -> int:
        \"\"\"Add two numbers.\"\"\"
        return a + b

    @server.prompt
    def explain(expression: str) -> str:
        \"\"\"Explain an arithmetic expression step by step.\"\"\"
        return f'Explain step by step how to compute {expression}.'

    @server.resource('calculator://precision', mime_type='application/json')
    def precision() -> dict:
        \"\"\"The precision of the numbers of the calculator.\"\"\"
        return {'digits': 15}

    # Or import the module, as in Google Python Style Guide

    import Pyjo.MCP.Server

    server = Pyjo.MCP.Server.new(name='calculator', version='1.0.0', instructions='Arithmetic for the model.')
    server.tool('add', lambda a, b: a + b, input_schema={'type': 'object', 'properties': {'a': {}, 'b': {}}})

    # Pyjoyment.Lite, with the validation of Host and Origin
    plugin('AllowedHosts')
    any('/mcp', server.to_action())

    # Pyjoyment
    app.plugin('AllowedHosts')
    app.routes.any('/mcp').to(cb=server.to_action())

    # The transport stdio too, of the command stdio
    app.hook('before_server_start', server.to_stdio())

:mod:`Pyjo.MCP.Server` is a server of the Model Context Protocol, of the
revision :data:`Pyjo.MCP.PROTOCOL_VERSION` of the specification, with the
methods ``server/discover``, ``tools/list`` and ``tools/call``, whose tools are
:mod:`Pyjo.MCP.Tool` objects, ``prompts/list`` and ``prompts/get``, whose
prompts are :mod:`Pyjo.MCP.Prompt` objects, and ``resources/list`` and
``resources/read``, whose resources are :mod:`Pyjo.MCP.Resource` objects. The
protocol is stateless: each request carries its revision and the capabilities
of its client in its ``_meta``, which the server checks, and a result carries
the name and the version of the server in its own ``_meta``.

A client that wants to know of the changes of the server opens a subscription
with ``subscriptions/listen``, a request that stays in progress, whose stream
gets the notifications of :meth:`~Pyjo_MCP_Server.notify_list_changed` and
:meth:`~Pyjo_MCP_Server.notify_resource_updated` that the client asks for,
until the client cancels it or the server stops.

The requests come over Streamable HTTP, the transport of
:meth:`~Pyjo_MCP_Server.to_action`, an action of a route of :mod:`Pyjoyment`,
which answers each request with a JSON object, or with a stream of events when
the request sends notifications before its result, as its progress, and the
client accepts one. The specification requires the
validation of ``Origin`` of a server on ``localhost``, against DNS rebinding,
which :mod:`Pyjoyment.Plugin.AllowedHosts` does, for the whole application or
the routes under its helper.

The requests come over the transport stdio too, a message of JSON-RPC on each
line of the standard input and output, which
:meth:`~Pyjo_MCP_Server.to_stdio` serves when the command ``stdio`` of
:mod:`Pyjoyment` starts the application, and the log goes to the standard
error. :meth:`~Pyjo_MCP_Server.serve` serves any other stream of messages, and
:meth:`~Pyjo_MCP_Server.dispatch_p` handles a message of any other transport.

See also
--------

:mod:`Pyjo.MCP.Tool`, :mod:`Pyjo.MCP.Prompt`, :mod:`Pyjo.MCP.Resource`,
:mod:`Pyjo.JSON.RPC`, :mod:`Pyjoyment.Plugin.AllowedHosts`, :mod:`Pyjo.MCP`.

Classes
-------
"""

import Pyjo.EventEmitter
import Pyjo.Exception
import Pyjo.IOLoop
import Pyjo.IOLoop.Messages
import Pyjo.JSON
import Pyjo.JSON.RPC
import Pyjo.Log
import Pyjo.Promise
import Pyjo.Server.Stdio

# The package of the distribution, imported relatively, as pyright takes the regular package Pyjo of Pyjoyment, which
# hides the namespace that extend_path keeps open
from .. import MCP
from . import Prompt, Resource, Tool

import base64
import binascii
import builtins
import re
import threading

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Self, cast, overload


if TYPE_CHECKING:
    import Pyjoyment.Controller

type Anything = builtins.object

# The members of params that the header Mcp-Name has, for each method
_NAMES = {'tools/call': 'name', 'resources/read': 'uri', 'prompts/get': 'name'}

# A value of a header that is encoded with Base64, and one that is plain
_BASE64 = re.compile(r'=\?base64\?(.*)\?=', re.S)
_PLAIN = re.compile(r'[\t\x20-\x7e]*')


class Context(Pyjo.EventEmitter.object):
    """
    The context of a request of MCP, with what its ``_meta`` tells, which a
    tool that asks for it gets before its arguments, and the notifications
    that the tool sends to the client before its result. ::

        @server.tool(context=True)
        def whoami(context) -> str:
            return context.client_info.get('name', 'unknown')

    Events
    ------

    ``cancelled`` ::

        @context.on('cancelled')
        def cancelled(context):
            ...

    Emitted once when the client abandons the request, as when it closes the
    connection of a response of Streamable HTTP before the result, or sends
    ``notifications/cancelled`` of the request over the transport stdio, so
    that a tool that runs long stops. ::

        id = Pyjo.IOLoop.recurring(1, lambda: ...)
        context.on('cancelled', lambda context: Pyjo.IOLoop.remove(id))
    """

    def __init__(
        self,
        controller: 'Pyjoyment.Controller.object | None' = None,
        client: Pyjo.JSON.RPC.Client | None = None,
        log: Pyjo.Log.object | None = None,
    ) -> None:
        """::

            context = Pyjo.MCP.Server.Context.new()
            context = Pyjo.MCP.Server.Context.new(c)
            context = Pyjo.MCP.Server.Context.new(client=client, log=app.log)

        Construct a new :class:`Context` object.
        """
        super().__init__()

        self.client = client
        """::

            client = context.client

        The :class:`Pyjo.JSON.RPC.Client` of the peer of a stream of messages,
        as the transport stdio, whose requests go to the client of MCP on the
        same stream, or ``None`` for Streamable HTTP.
        """

        self.client_capabilities: dict[str, Any] = {}
        """::

            capabilities = context.client_capabilities

        The capabilities of the client, as the request declares them.
        """

        self.client_info: dict[str, Any] = {}
        """::

            info = context.client_info

        The name and the version of the client, as the request tells them, or
        an empty :class:`dict`.
        """

        self.controller = controller
        """::

            c = context.controller

        The :mod:`Pyjoyment.Controller` of the request of HTTP, or ``None`` for
        another transport.
        """

        self.id: Any = None
        """::

            id = context.id

        The ``id`` of the request of JSON-RPC, which the messages of its
        subscription name, or ``None`` for a notification.
        """

        self.log = log
        """::

            log = context.log

        The :mod:`Pyjo.Log` of the errors of the server of a request without
        a controller, as the one of the application for the transport stdio,
        or ``None``.
        """

        self.log_level: str | None = None
        """::

            level = context.log_level

        The lowest level of the log messages that the client wants of the
        request, as its ``_meta`` tells it, or ``None`` for none.
        """

        self.meta: dict[str, Any] = {}
        """::

            meta = context.meta

        The ``_meta`` of the request.
        """

        self.progress_token: Any = None
        """::

            token = context.progress_token

        The ``progressToken`` of the ``_meta`` of the request, which the
        notifications of its progress name, or ``None`` for none.
        """

        self.protocol_version: str | None = None
        """::

            version = context.protocol_version

        The revision of the specification of the request.
        """

        self.status: int | None = None
        """::

            status = context.status

        The status of the response of HTTP of an error, which the request sets,
        or ``None`` for the one of its code.
        """

        self.stream: Callable[[dict[str, Any]], Any] | None = None
        """::

            cb = context.stream
            context.stream = lambda notification: ...

        The function of the transport that sends a notification of the request
        to the client, as an event of the stream of the response of Streamable
        HTTP, or a message of the transport stdio, or ``None``, where the
        notifications go nowhere, as for a client of Streamable HTTP that does
        not accept a stream of events.
        """

        self._cancelled = False

    @property
    def is_cancelled(self) -> bool:
        """::

            boolean = context.is_cancelled

        Check if the client abandoned the request, for a tool that cannot
        subscribe to the event ``cancelled`` and checks it instead.
        """
        return self._cancelled

    def cancel(self) -> Self:
        """::

            context = context.cancel()

        Mark the request as abandoned, and emit the event ``cancelled``, once.
        """
        if not self._cancelled:
            self._cancelled = True
            self.emit('cancelled')
        return self

    def notify(self, method: str, params: dict[str, Any] | None = None) -> bool:
        """::

            boolean = context.notify('notifications/message', {'level': 'info', 'data': 'Hello'})

        Send a notification of JSON-RPC to the client, before the result of
        the request, and return whether it was sent: not for a request that
        the client abandoned, nor without a :attr:`stream`.
        """
        if self._cancelled or (stream := self.stream) is None:
            return False
        stream({'jsonrpc': '2.0', 'method': method, 'params': params or {}})
        return True

    def notify_log(self, level: str, data: Any) -> bool:
        """::

            boolean = context.notify_log('info', 'Fetching the forecast')
            boolean = context.notify_log('error', {'code': 23})

        Send a log message of the level, ``debug``, ``info``, ``notice``,
        ``warning``, ``error``, ``critical``, ``alert`` or ``emergency``, as
        ``notifications/message``, if the client wants the messages of the
        level, as :attr:`log_level` tells, and return whether it was sent.
        """
        if (minimum := self.log_level) is None or _LEVELS.get(level, 0) < _LEVELS.get(minimum, 0):
            return False
        return self.notify('notifications/message', {'level': level, 'data': data})

    def notify_progress(self, progress: float, total: float | None = None, message: str | None = None) -> bool:
        """::

            boolean = context.notify_progress(1)
            boolean = context.notify_progress(1, 3, 'Fetched the first page')

        Send the progress of the request, as ``notifications/progress``, if
        the client asked for it with a :attr:`progress_token`, and return
        whether it was sent.
        """
        if (token := self.progress_token) is None:
            return False
        params: dict[str, Any] = {'progressToken': token, 'progress': progress}
        if total is not None:
            params['total'] = total
        if message is not None:
            params['message'] = message
        return self.notify('notifications/progress', params)


class Pyjo_MCP_Server(Pyjo.EventEmitter.object):
    """
    :mod:`Pyjo.MCP.Server` inherits all events and methods from
    :mod:`Pyjo.EventEmitter` and implements the following new ones.

    Events
    ------

    ``exception`` ::

        @server.on('exception')
        def exception(server, e, context):
            ...

    Emitted when a tool raises an exception that is not a
    :class:`Pyjo.MCP.Tool.Error`, an error of the server, which the response
    does not tell, with the :class:`Context` of the request. The action of
    :meth:`to_action` logs it with the log of the application too. ::

        server.on('exception', lambda server, e, context: print(f'Failed: {e}'))
    """

    def __init__(self, name: str = 'Pyjo.MCP', version: str = '1.0.0', instructions: str | None = None) -> None:
        """::

            server = Pyjo.MCP.Server.new()
            server = Pyjo.MCP.Server.new(name='calculator', version='1.0.0', instructions='Arithmetic.')

        Construct a new :mod:`Pyjo.MCP.Server` object.
        """
        super().__init__()

        self.cache_scope = 'public'
        """::

            scope = server.cache_scope
            server.cache_scope = 'private'

        Who may cache the results of ``server/discover`` and ``tools/list``,
        ``public`` by default, or ``private`` for the tools of the user of the
        request.
        """

        self.cache_ttl = 0
        """::

            ttl = server.cache_ttl
            server.cache_ttl = 300000

        How long a client may cache the results of ``server/discover`` and
        ``tools/list``, in milliseconds, ``0`` by default.
        """

        self.heartbeat: float = 30
        """::

            interval = server.heartbeat
            server.heartbeat = 15

        How often a subscription of Streamable HTTP sends a comment of the
        stream of events, which keeps a connection without notifications from
        being closed by a proxy, in seconds, ``30`` by default, or ``0`` for
        never.
        """

        self.instructions = instructions
        """::

            instructions = server.instructions
            server.instructions = 'Arithmetic for the model.'

        How a language model uses the server, which ``server/discover`` gives,
        or ``None``.
        """

        self.list_changed = False
        """::

            boolean = server.list_changed
            server.list_changed = True

        Whether ``server/discover`` declares ``listChanged`` of the tools, the
        prompts and the resources, a promise that the application calls
        :meth:`notify_list_changed` when it changes a list, false by default.
        """

        self.name = name
        """::

            name = server.name
            server.name = 'calculator'

        The name of the server, ``Pyjo.MCP`` by default.
        """

        self.prompts: list[Prompt.object] = []
        """::

            prompts = server.prompts

        The :mod:`Pyjo.MCP.Prompt` objects of the server, in the order of
        ``prompts/list``.
        """

        self.resources: list[Resource.object] = []
        """::

            resources = server.resources

        The :mod:`Pyjo.MCP.Resource` objects of the server, in the order of
        ``resources/list``.
        """

        self.subscribe = False
        """::

            boolean = server.subscribe
            server.subscribe = True

        Whether ``server/discover`` declares ``subscribe`` of the resources, a
        promise that the application calls :meth:`notify_resource_updated`
        when a resource changes, false by default.
        """

        self.tools: list[Tool.object] = []
        """::

            tools = server.tools

        The :mod:`Pyjo.MCP.Tool` objects of the server, in the order of
        ``tools/list``.
        """

        self.version = version
        """::

            version = server.version
            server.version = '2.0.0'

        The version of the server, ``1.0.0`` by default.
        """

        rpc = self._rpc = Pyjo.JSON.RPC.new()
        rpc.method('server/discover', self._discover, context=True)
        rpc.method('tools/list', self._tools_list, context=True)
        rpc.method('tools/call', self._tools_call, context=True)
        rpc.method('prompts/list', self._prompts_list, context=True)
        rpc.method('prompts/get', self._prompts_get, context=True)
        rpc.method('resources/list', self._resources_list, context=True)
        rpc.method('resources/read', self._resources_read, context=True)
        rpc.method('subscriptions/listen', self._listen, context=True)
        # TODO: resources/templates/list, with the URI templates of RFC 6570

        # The subscriptions of each thread, as a notification is written by the event loop of the thread of its stream
        self._local = threading.local()

        def exception(rpc: Pyjo.JSON.RPC.object, e: Exception, context: Any) -> None:
            self._exception(e, context)

        rpc.on('exception', exception)

    def dispatch_p(self, message: Any, context: Context | None = None) -> Pyjo.Promise.object:
        """::

            promise = server.dispatch_p(request)
            promise = server.dispatch_p(b'{"jsonrpc": "2.0", "method": "tools/list", ...}', context)

        Dispatch a request or a notification of JSON-RPC, as :mod:`Pyjo.JSON`
        decodes it, or the JSON of one, and return a :mod:`Pyjo.Promise` of
        the response, or of ``None`` for a notification, as
        :meth:`~Pyjo.JSON.RPC.Pyjo_JSON_RPC.dispatch_p` does. A batch, which
        MCP does not have, and a request with the ``id`` of ``null``, which
        MCP does not allow, are invalid requests.
        """
        context = context or Context()
        if isinstance(message, bytes | bytearray | str):
            try:
                message = Pyjo.JSON.decode_json(message)
            except ValueError:
                pass
        if isinstance(message, list) or ('id' in _object(message) and _object(message)['id'] is None):
            return Pyjo.Promise.resolve(_error(None, Pyjo.JSON.RPC.INVALID_REQUEST, 'Invalid Request'))
        context.id = _object(message).get('id')
        return self._rpc.dispatch_p(message, context)

    def notify_list_changed(self, kind: str) -> int:
        """::

            count = server.notify_list_changed('tools')
            count = server.notify_list_changed('prompts')
            count = server.notify_list_changed('resources')

        Send ``notifications/tools/list_changed``, or the one of the prompts
        or of the resources, to the subscriptions that want it, after a change
        of :attr:`tools`, :attr:`prompts` or :attr:`resources`, and return how
        many got it. The subscriptions are those of the process and of the
        thread, as each worker of a server that has several has its own. ::

            server.tools = [tool for tool in server.tools if tool.name != 'add']
            server.notify_list_changed('tools')
        """
        if (key := _LIST_CHANGED.get(kind)) is None:
            raise Pyjo.Exception.new(f'Unknown list: {kind}')
        return self._notify(lambda notifications: notifications.get(key) is True, f'notifications/{kind}/list_changed')

    def notify_resource_updated(self, uri: str) -> int:
        """::

            count = server.notify_resource_updated('file:///project/README.md')

        Send ``notifications/resources/updated`` of the URI to the
        subscriptions that want it, after a change of the contents of the
        resource, which the client reads again, and return how many got it, as
        :meth:`notify_list_changed` does.
        """

        def wants(notifications: dict[str, Any]) -> bool:
            return uri in notifications.get('resourceSubscriptions', [])

        return self._notify(wants, 'notifications/resources/updated', {'uri': uri})

    @overload
    def prompt[F: Callable[..., Any]](self, name: F, cb: None = None) -> F: ...

    @overload
    def prompt[F: Callable[..., Any]](
        self, name: str | None = None, cb: None = None, **options: Any
    ) -> Callable[[F], F]: ...

    @overload
    def prompt[F: Callable[..., Any]](self, name: str, cb: F, **options: Any) -> F: ...

    def prompt(
        self, name: str | Callable[..., Any] | None = None, cb: Callable[..., Any] | None = None, **options: Any
    ) -> Any:
        """::

            cb = server.prompt('review', lambda code: f'Review this code:\\n{code}')
            cb = server.prompt('review', lambda context, code: ..., context=True)

        Add a prompt, a :mod:`Pyjo.MCP.Prompt` of the function with the options
        of its constructor, and return the function. Without a function, it is
        a decorator, with the name of the prompt or of the function. ::

            @server.prompt
            def review(code: str, language: str = 'Python') -> str:
                \"\"\"Review a piece of code.\"\"\"
                return f'Review this {language} code:\\n{code}'

            @server.prompt('code_review', title='Code review')
            def code_review(code: str) -> str:
                \"\"\"Review a piece of code.\"\"\"
                return f'Review this code:\\n{code}'
        """
        if callable(name):
            return self._prompt(None, name, options)
        if cb is None:
            title = name

            def decorator(cb: Callable[..., Any]) -> Callable[..., Any]:
                return self._prompt(title, cb, options)

            return decorator
        return self._prompt(name, cb, options)

    @overload
    def resource[F: Callable[..., Any]](self, uri: str, cb: None = None, **options: Any) -> Callable[[F], F]: ...

    @overload
    def resource[F: Callable[..., Any]](self, uri: str, cb: F, **options: Any) -> F: ...

    def resource(self, uri: str, cb: Callable[..., Any] | None = None, **options: Any) -> Any:
        """::

            cb = server.resource('file:///project/README.md', lambda: '# Project', mime_type='text/markdown')
            cb = server.resource('config://app', lambda context: ..., context=True)

        Add a resource of the URI, a :mod:`Pyjo.MCP.Resource` of the function
        with the options of its constructor, and return the function. Without
        a function, it is a decorator. ::

            @server.resource('file:///project/README.md', mime_type='text/markdown')
            def readme() -> str:
                \"\"\"The documentation of the project.\"\"\"
                return '# Project'
        """
        if cb is None:

            def decorator(cb: Callable[..., Any]) -> Callable[..., Any]:
                return self._resource(uri, cb, options)

            return decorator
        return self._resource(uri, cb, options)

    def serve(self, peer: Any, log: Pyjo.Log.object | None = None) -> Pyjo.JSON.RPC.Client:
        """::

            client = server.serve(messages)
            client = server.serve(messages, log=app.log)

        Serve the methods to a peer on a stream of messages in both directions,
        as a :mod:`Pyjo.IOLoop.Messages` object, and return the
        :class:`Pyjo.JSON.RPC.Client` of the peer, as
        :meth:`~Pyjo.JSON.RPC.Pyjo_JSON_RPC.serve` does, with the rules of
        :meth:`dispatch_p` and a :class:`Context` of its own for each request,
        whose ``client`` is the one of the peer and whose ``log`` gets the
        errors of the server. ``notifications/cancelled`` of the peer cancels
        the :class:`Context` of its request, which gets no response then, and
        the end of the input of the peer ends its subscriptions gracefully,
        with their responses. ::

            # The transport stdio, a message on each line of the standard input and output
            messages = Pyjo.IOLoop.Messages.new(Pyjo.IOLoop.Stdio.new())
            server.serve(messages)
            messages.start()
        """
        contexts: dict[Any, Context] = {}

        def dispatch_p(message: Any, client: Pyjo.JSON.RPC.Client) -> Any:
            # The cancellation of a request in progress, as a connection that closes is over Streamable HTTP
            if (message_ := _object(message)).get('method') == 'notifications/cancelled':
                if (context := contexts.get(_id(_object(message_.get('params')).get('requestId')))) is not None:
                    context.cancel()
                return None

            # The notifications of a request go to the peer, on the same stream
            context = Context(client=client, log=log)
            context.stream = lambda notification: client.notify(notification['method'], **notification['params'])
            if (id := _id(message_.get('id'))) is not None:
                contexts[id] = context

            def respond(response: Any = None) -> Any:
                if contexts.get(id) is context:
                    del contexts[id]
                return None if context.is_cancelled else response

            return self.dispatch_p(message, context).then(respond)

        client = self._rpc.serve(peer, dispatch_p=dispatch_p)

        # The end of the input, after which the requests in progress get their responses, ends the subscriptions
        def end(peer: Any) -> None:
            for subscription in list(self._subscriptions):
                if subscription.context.client is client:
                    subscription.end()

        # A stream that closes abandons its requests
        def close(peer: Any, *args: Any) -> None:
            for context in list(contexts.values()):
                context.cancel()

        peer.on('end', end)
        peer.on('close', close)
        return client

    @overload
    def tool[F: Callable[..., Any]](self, name: F, cb: None = None) -> F: ...

    @overload
    def tool[F: Callable[..., Any]](
        self, name: str | None = None, cb: None = None, **options: Any
    ) -> Callable[[F], F]: ...

    @overload
    def tool[F: Callable[..., Any]](self, name: str, cb: F, **options: Any) -> F: ...

    def tool(
        self, name: str | Callable[..., Any] | None = None, cb: Callable[..., Any] | None = None, **options: Any
    ) -> Any:
        """::

            cb = server.tool('add', lambda a, b: a + b, input_schema={'type': 'object'})
            cb = server.tool('whoami', lambda context: context.client_info.get('name'), context=True)

        Add a tool, a :mod:`Pyjo.MCP.Tool` of the function with the options of
        its constructor, and return the function. Without a function, it is a
        decorator, with the name of the tool or of the function. ::

            @server.tool
            def add(a: int, b: int) -> int:
                \"\"\"Add two numbers.\"\"\"
                return a + b

            @server.tool('math.multiply', title='Multiplication', annotations={'readOnlyHint': True})
            def multiply(a: int, b: int) -> int:
                \"\"\"Multiply two numbers.\"\"\"
                return a * b
        """
        if callable(name):
            return self._tool(None, name, options)
        if cb is None:
            title = name

            def decorator(cb: Callable[..., Any]) -> Callable[..., Any]:
                return self._tool(title, cb, options)

            return decorator
        return self._tool(name, cb, options)

    def to_action(self) -> Callable[['Pyjoyment.Controller.object'], Any]:
        """::

            action = server.to_action()

        The action of a route of :mod:`Pyjoyment`, the endpoint of MCP of
        Streamable HTTP, which takes a request of JSON-RPC in the body of a
        POST and renders its response in JSON, ``202 Accepted`` without a body
        for a notification, ``405 Method Not Allowed`` for another method of
        HTTP, and ``400 Bad Request`` for a header of MCP that does not match
        the body, as ``MCP-Protocol-Version``, ``Mcp-Method``, ``Mcp-Name`` and
        ``Mcp-Param-{name}``, or a request that is not valid. The first
        notification of the request, of :meth:`Context.notify`, turns the
        response into a stream of events, ``text/event-stream``, where the
        ``Accept`` of the request has it, with the notifications and then the
        response, and a connection that closes before the result cancels the
        :class:`Context`. A subscription of ``subscriptions/listen`` is such a
        stream, which needs the ``Accept`` and stays open, with a comment every
        :attr:`heartbeat` seconds, until the client closes the connection, or
        until the event loop stops gracefully, which ends the subscription with
        its response. ::

            # Pyjoyment.Lite
            any('/mcp', server.to_action())

            # Pyjoyment
            app.routes.any('/mcp').to(cb=server.to_action())
        """

        def action(c: 'Pyjoyment.Controller.object') -> Any:
            if c.req.method != 'POST':
                c.res.headers.header('Allow', 'POST')
                return c.render(json=_error(None, Pyjo.JSON.RPC.INVALID_REQUEST, 'Method not allowed'), status=405)

            try:
                message: Any = Pyjo.JSON.decode_json(c.req.body)
            except ValueError:
                return c.render(json=_error(None, Pyjo.JSON.RPC.PARSE_ERROR, 'Parse error'), status=400)
            if (request := _object(message)).get('id') is not None:
                if (mismatch := self._headers(c, request)) is not None:
                    error = _error(request['id'], MCP.HEADER_MISMATCH, f'Header mismatch: {mismatch}')
                    return c.render(json=error, status=400)

            context = Context.new(c)
            streaming = done = False

            # The notifications of the request open a stream of events, where the client accepts one, before the result
            def stream(notification: dict[str, Any]) -> None:
                nonlocal streaming
                if not streaming:
                    streaming = True
                    c.helpers.inactivity_timeout(0)
                    c.res.headers.header('X-Accel-Buffering', 'no')
                    c.write_sse()
                c.write_sse({'text': Pyjo.JSON.to_json(notification)})

            if 'text/event-stream' in (c.req.headers.accept or ''):
                context.stream = stream

            # A connection that closes before the result abandons the request
            def finish(c: 'Pyjoyment.Controller.object') -> None:
                if not done:
                    context.cancel()

            c.on('finish', finish)

            def respond(response: Any = None) -> None:
                nonlocal done
                done = True
                if context.is_cancelled:
                    return
                if streaming:
                    if response is not None:
                        c.write_sse({'text': Pyjo.JSON.to_json(response)})
                    c.finish()
                    return
                if response is None:
                    c.rendered(202)
                    return
                code = _object(_object(response).get('error')).get('code')
                c.render(
                    json=response, status=context.status or (_STATUS.get(code, 200) if isinstance(code, int) else 200)
                )

            c.render_later()
            return self.dispatch_p(message, context).then(respond)

        return action

    def to_stdio(self) -> Callable[[Any, Any], None]:
        """::

            hook = server.to_stdio()

        The hook ``before_server_start`` of an application of :mod:`Pyjoyment`,
        the transport stdio, which serves the methods with :meth:`serve` on
        the standard input and output of :mod:`Pyjo.Server.Stdio`, a message
        of JSON-RPC on each line, when the command ``stdio`` starts the
        application, and does nothing for another server, so that the same
        application serves Streamable HTTP with ``daemon``. ::

            # Pyjoyment.Lite
            hook('before_server_start', server.to_stdio())

            # Pyjoyment
            app.hook('before_server_start', server.to_stdio())
        """

        def hook(server: Any, app: Any) -> None:
            def stream(server: Pyjo.Server.Stdio.object, stream: Any) -> None:
                self.serve(Pyjo.IOLoop.Messages.new(stream), log=app.log)

            if isinstance(server, Pyjo.Server.Stdio.object):
                server.on('stream', stream)

        return hook

    def _cursor(self, params: dict[str, Any]) -> None:
        # A list of one page, whose cursor no request has
        if params.get('cursor') is not None:
            raise Pyjo.JSON.RPC.Error.new(Pyjo.JSON.RPC.INVALID_PARAMS, 'Invalid cursor')

    def _discover(self, context: Context, **params: Any) -> dict[str, Any]:
        self._meta(context, params)
        capabilities: dict[str, Any] = {}
        listed: dict[str, Any] = {'listChanged': True} if self.list_changed else {}
        if self.tools:
            capabilities['tools'] = {**listed}
        if self.prompts:
            capabilities['prompts'] = {**listed}
        if self.resources:
            capabilities['resources'] = {**listed, **({'subscribe': True} if self.subscribe else {})}
        result: dict[str, Any] = {'supportedVersions': list(MCP.SUPPORTED_VERSIONS), 'capabilities': capabilities}
        if self.instructions is not None:
            result['instructions'] = self.instructions
        return self._result(result, cacheable=True)

    def _exception(self, e: Exception, context: Any) -> None:
        # An error of the server, which the log of the application of the request gets too
        if isinstance(context, Context) and (c := context.controller) is not None:
            c.helpers.log().error(Pyjo.Exception.new(e).inspect())
        elif isinstance(context, Context) and (log := context.log) is not None:
            log.error(Pyjo.Exception.new(e).inspect())
        self.emit('exception', e, context)

    def _headers(self, c: 'Pyjoyment.Controller.object', request: dict[str, Any]) -> str | None:
        # What does not match between the headers of MCP and the body of the request, or None
        headers = c.req.headers
        params = _object(request.get('params'))
        meta = _object(params.get('_meta'))

        version = headers.header('MCP-Protocol-Version')
        if version is None:
            return 'Missing MCP-Protocol-Version header'
        if (expected := meta.get(MCP.META_PROTOCOL_VERSION)) is not None and expected != version:
            return f"MCP-Protocol-Version header value '{version}' does not match body value '{expected}'"

        method = request.get('method')
        if (sent := headers.header('Mcp-Method')) is None:
            return 'Missing Mcp-Method header'
        if sent != method:
            return f"Mcp-Method header value '{sent}' does not match body value '{method}'"

        if isinstance(method, str) and (key := _NAMES.get(method)) is not None:
            if (name := headers.header('Mcp-Name')) is None:
                return 'Missing Mcp-Name header'
            if (decoded := _decode(name)) is None:
                return 'Invalid Mcp-Name header'
            if decoded != params.get(key):
                return f"Mcp-Name header value '{decoded}' does not match body value '{params.get(key)}'"

        if method == 'tools/call':
            tool = next((tool for tool in self.tools if tool.name == params.get('name')), None)
            arguments = params.get('arguments')
            for name, path, type in tool.header_params if tool is not None else []:
                value = _value(arguments, path)
                header = headers.header(f'Mcp-Param-{name}')
                if value is None:
                    if header is not None:
                        return f'Unexpected Mcp-Param-{name} header'
                    continue
                if header is None:
                    return f'Missing Mcp-Param-{name} header'
                if (decoded := _decode(header)) is None:
                    return f'Invalid Mcp-Param-{name} header'
                if not _match(type, decoded, value):
                    body = value if isinstance(value, str) else Pyjo.JSON.to_json(value)
                    return f"Mcp-Param-{name} header value '{decoded}' does not match body value '{body}'"
        return None

    def _listen(self, context: Context, **params: Any) -> Pyjo.Promise.object:
        self._meta(context, params)
        if context.stream is None:
            raise Pyjo.JSON.RPC.Error.new(Pyjo.JSON.RPC.INVALID_REQUEST, 'Subscriptions need a stream of events')

        # The notifications that the server sends, every one that the client asks for
        notifications = _object(params.get('notifications'))
        honored: dict[str, Any] = {key: True for key in _LIST_CHANGED.values() if notifications.get(key) is True}
        uris = notifications.get('resourceSubscriptions')
        if uris := [uri for uri in cast(list[Any], uris) if isinstance(uri, str)] if isinstance(uris, list) else []:
            honored['resourceSubscriptions'] = uris

        promise = Pyjo.Promise.new()
        subscriptions = self._subscriptions
        loop = Pyjo.IOLoop.singleton
        timer: str | None = None
        finish: Any = None

        def remove() -> None:
            if subscription in subscriptions:
                subscriptions.remove(subscription)
            if timer is not None:
                loop.remove(timer)
            if finish is not None:
                loop.unsubscribe('finish', finish)

        # The server ends the subscription gracefully with its response
        def end() -> None:
            remove()
            promise.resolve(self._result({'_meta': {MCP.META_SUBSCRIPTION_ID: context.id}}))

        # The client ends it without one
        def cancelled(context: Context) -> None:
            remove()
            promise.resolve(None)

        context.on('cancelled', cancelled)
        subscription = _Subscription(context, honored, end)
        subscriptions.append(subscription)
        subscription.notify('notifications/subscriptions/acknowledged', {'notifications': honored})

        # A connection of HTTP gets the comments that keep it open, and ends with a graceful stop of the event loop
        if (c := context.controller) is not None:
            if self.heartbeat:
                timer = loop.recurring(self.heartbeat, lambda loop: c.write_sse({'comment': 'keepalive'}))

            def stopping(loop: Any) -> None:
                end()

            finish = loop.once('finish', stopping)
        return promise

    def _meta(self, context: Context, params: dict[str, Any]) -> None:
        # The fields of _meta of the request, which every request has
        meta_ = _object(params.get('_meta'))
        version = meta_.get(MCP.META_PROTOCOL_VERSION)
        if not isinstance(version, str):
            context.status = 400
            raise Pyjo.JSON.RPC.Error.new(Pyjo.JSON.RPC.INVALID_PARAMS, 'Missing protocol version')
        if version not in MCP.SUPPORTED_VERSIONS:
            context.status = 400
            data = {'supported': list(MCP.SUPPORTED_VERSIONS), 'requested': version}
            raise Pyjo.JSON.RPC.Error.new(MCP.UNSUPPORTED_PROTOCOL_VERSION, 'Unsupported protocol version', data)
        capabilities = meta_.get(MCP.META_CLIENT_CAPABILITIES)
        if not isinstance(capabilities, dict):
            context.status = 400
            raise Pyjo.JSON.RPC.Error.new(Pyjo.JSON.RPC.INVALID_PARAMS, 'Missing client capabilities')
        info = meta_.get(MCP.META_CLIENT_INFO)
        context.meta = meta_
        context.protocol_version = version
        context.client_capabilities = cast(dict[str, Any], capabilities)
        context.client_info = _object(info)
        context.log_level = level if isinstance(level := meta_.get(MCP.META_LOG_LEVEL), str) else None
        context.progress_token = meta_.get('progressToken')

    def _notify(
        self, wants: Callable[[dict[str, Any]], bool], method: str, params: dict[str, Any] | None = None
    ) -> int:
        # A notification to the subscriptions that want it
        return sum(
            subscription.notify(method, params)
            for subscription in list(self._subscriptions)
            if wants(subscription.notifications)
        )

    def _result(self, result: dict[str, Any], cacheable: bool = False) -> dict[str, Any]:
        # A result with its type, the name and the version of the server, and the hints of the cache
        result = {'resultType': 'complete', **result}
        if cacheable:
            result.update(ttlMs=self.cache_ttl, cacheScope=self.cache_scope)
        meta = _object(result.get('_meta'))
        result['_meta'] = {**meta, MCP.META_SERVER_INFO: {'name': self.name, 'version': self.version}}
        return result

    def _prompt(self, name: str | None, cb: Callable[..., Any], options: dict[str, Any]) -> Callable[..., Any]:
        self.prompts.append(Prompt.new(cb, name=name, **options))
        return cb

    def _prompts_get(self, context: Context, **params: Any) -> Pyjo.Promise.object:
        self._meta(context, params)
        name = params.get('name')
        if (prompt := next((prompt for prompt in self.prompts if prompt.name == name), None)) is None:
            raise Pyjo.JSON.RPC.Error.new(Pyjo.JSON.RPC.INVALID_PARAMS, f'Unknown prompt: {name}')
        arguments = params.get('arguments', {})
        if not isinstance(arguments, dict):
            raise Pyjo.JSON.RPC.Error.new(Pyjo.JSON.RPC.INVALID_PARAMS, 'Invalid arguments')
        return prompt.get_p(cast(dict[str, Any], arguments), context).then(self._result)

    def _prompts_list(self, context: Context, **params: Any) -> dict[str, Any]:
        self._meta(context, params)
        self._cursor(params)
        return self._result({'prompts': [prompt.__json__() for prompt in self.prompts]}, cacheable=True)

    def _resource(self, uri: str, cb: Callable[..., Any], options: dict[str, Any]) -> Callable[..., Any]:
        self.resources.append(Resource.new(uri, cb, **options))
        return cb

    def _resources_list(self, context: Context, **params: Any) -> dict[str, Any]:
        self._meta(context, params)
        self._cursor(params)
        return self._result({'resources': [resource.__json__() for resource in self.resources]}, cacheable=True)

    def _resources_read(self, context: Context, **params: Any) -> Pyjo.Promise.object:
        self._meta(context, params)
        uri = params.get('uri')
        if (resource := next((resource for resource in self.resources if resource.uri == uri), None)) is None:
            raise Pyjo.JSON.RPC.Error.new(Pyjo.JSON.RPC.INVALID_PARAMS, 'Resource not found', {'uri': uri})

        def result(value: dict[str, Any]) -> dict[str, Any]:
            return self._result(value, cacheable=True)

        return resource.read_p(context).then(result)

    @property
    def _subscriptions(self) -> list['_Subscription']:
        if (subscriptions := getattr(self._local, 'subscriptions', None)) is None:
            subscriptions = self._local.subscriptions = []
        return cast(list[_Subscription], subscriptions)

    def _tool(self, name: str | None, cb: Callable[..., Any], options: dict[str, Any]) -> Callable[..., Any]:
        self.tools.append(Tool.new(cb, name=name, **options))
        return cb

    def _tools_call(self, context: Context, **params: Any) -> Pyjo.Promise.object:
        self._meta(context, params)
        name = params.get('name')
        if (tool := next((tool for tool in self.tools if tool.name == name), None)) is None:
            raise Pyjo.JSON.RPC.Error.new(Pyjo.JSON.RPC.INVALID_PARAMS, f'Unknown tool: {name}')
        arguments = params.get('arguments', {})
        if not isinstance(arguments, dict):
            raise Pyjo.JSON.RPC.Error.new(Pyjo.JSON.RPC.INVALID_PARAMS, 'Invalid arguments')
        return tool.call_p(cast(dict[str, Any], arguments), context).then(self._result)

    def _tools_list(self, context: Context, **params: Any) -> dict[str, Any]:
        self._meta(context, params)
        self._cursor(params)
        return self._result({'tools': [tool.__json__() for tool in self.tools]}, cacheable=True)


class _Subscription:
    # A subscription of subscriptions/listen, whose messages name its request, which the server ends with end
    __slots__ = ('context', 'end', 'notifications')

    def __init__(self, context: Context, notifications: dict[str, Any], end: Callable[[], None]) -> None:
        self.context = context
        self.end = end
        self.notifications = notifications

    def notify(self, method: str, params: dict[str, Any] | None = None) -> bool:
        return self.context.notify(method, {'_meta': {MCP.META_SUBSCRIPTION_ID: self.context.id}, **(params or {})})


# The filters of the notifications of the changes of the lists of a subscription
_LIST_CHANGED = {'tools': 'toolsListChanged', 'prompts': 'promptsListChanged', 'resources': 'resourcesListChanged'}

# The levels of the log messages of a client, as the ones of syslog
_LEVELS = {
    level: number
    for number, level in enumerate(('debug', 'info', 'notice', 'warning', 'error', 'critical', 'alert', 'emergency'))
}

# The status of the response of HTTP of an error of JSON-RPC
_STATUS = {
    Pyjo.JSON.RPC.PARSE_ERROR: 400,
    Pyjo.JSON.RPC.INVALID_REQUEST: 400,
    Pyjo.JSON.RPC.METHOD_NOT_FOUND: 404,
    Pyjo.JSON.RPC.INTERNAL_ERROR: 500,
}


def _decode(value: str) -> str | None:
    # A value of a header, decoded from Base64 of UTF-8, or None for one that is not valid
    if (match := _BASE64.fullmatch(value)) is not None:
        try:
            return base64.b64decode(match[1], validate=True).decode()
        except (binascii.Error, UnicodeDecodeError):
            return None
    return value if _PLAIN.fullmatch(value) else None


def _error(id: Any, code: int, message: str) -> dict[str, Any]:
    return {'jsonrpc': '2.0', 'id': id, 'error': {'code': code, 'message': message}}


def _id(id: Any) -> str | int | None:
    # An id of JSON-RPC, a string or a number, or None for another value
    return id if isinstance(id, str | int) and not isinstance(id, bool) else None


def _object(value: Anything) -> dict[str, Any]:
    # An object of JSON, or an empty one for another value
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _match(type: str, header: str, value: Any) -> bool:
    # A header of an argument and the value of the argument, the integers compared as numbers
    if type == 'integer':
        try:
            return float(header) == value and not isinstance(value, bool)
        except ValueError:
            return False
    if type == 'boolean':
        return isinstance(value, bool) and header == ('true' if value else 'false')
    return header == value


def _value(arguments: Any, path: list[str]) -> Any:
    # The value of an argument at the path of its properties
    for key in path:
        if not isinstance(arguments, dict):
            return None
        arguments = cast(dict[str, Any], arguments).get(key)
    return arguments


new = Pyjo_MCP_Server.new
object = Pyjo_MCP_Server
Server = Pyjo_MCP_Server
