Tutorial
========

Make a server of the Model Context Protocol with Pyjoyment.

A quick example-driven introduction to the servers of :mod:`Pyjo.MCP.Server`,
whose tools a language model calls, as Claude, through a client of MCP, as
Claude Code. A server is a route of an application of :mod:`Pyjoyment`, so
what the :doc:`tutorial of Pyjoyment <pyjoyment:guides/tutorial>` teaches
applies here too: the commands, the user agent, the tests and the servers.

A first server
--------------

A tool is a function. Its name, its description and the schema of its
arguments are those of the function: its name, the first paragraph of its
docstring, and its type hints, with the descriptions of the fields
``:param`` of its docstring. The server is the action of a route, and
:mod:`Pyjoyment.Plugin.AllowedHosts` validates ``Host`` and ``Origin``, which
the specification requires of a server on ``localhost``, as a page of another
site could otherwise reach it through DNS rebinding.

.. literalinclude:: tutorial/hello.py
    :language: python

The command ``daemon`` serves it, or ``pyjo-reload``, which restarts it when a
file changes, and Claude Code connects to it over HTTP:

.. code-block:: console

    $ uv run pyjo-reload -l http://127.0.0.1:3000 hello.py
    $ claude mcp add --transport http hello http://127.0.0.1:3000/mcp

Claude Code then lists the tool ``greet`` with its description and the schema
of its argument, and calls it when a conversation asks for a greeting. Every
request of MCP is a POST of JSON-RPC to the endpoint, with the revision of the
specification and the capabilities of the client in its ``_meta`` and in its
headers, as the protocol has no session:

.. code-block:: sh

    curl http://127.0.0.1:3000/mcp \
      -H 'MCP-Protocol-Version: 2026-07-28' -H 'Mcp-Method: tools/call' -H 'Mcp-Name: greet' \
      -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "greet", "arguments": {"name": "Pyjo"},
           "_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28", "io.modelcontextprotocol/clientCapabilities": {}}}}'

The response is the result of the tool, with the name and the version of the
server in its ``_meta``:

.. code-block:: json

    {
      "id": 1,
      "jsonrpc": "2.0",
      "result": {
        "_meta": {"io.modelcontextprotocol/serverInfo": {"name": "hello", "version": "1.0.0"}},
        "content": [{"text": "Hello, Pyjo!", "type": "text"}],
        "isError": false,
        "resultType": "complete"
      }
    }

Schemas
-------

The type hints are the ``inputSchema`` of the tool, as
:meth:`~Pyjo.JSON.Schema.Pyjo_JSON_Schema.parameters` of
:mod:`Pyjo.JSON.Schema` gives it: a parameter without a default is required,
a ``Literal`` is an ``enum``, and ``Annotated`` adds a description or the
keywords of JSON Schema, as ``minimum`` and ``maximum``. The annotation of
what the function returns is the ``outputSchema``, here a list of
``TypedDict``, whose description is its docstring.

.. literalinclude:: tutorial/schemas.py
    :language: python

A result of an ``outputSchema`` is the ``structuredContent`` of the result of
the tool, which a client validates, and its JSON the text of its ``content``,
which the language model reads. A function that returns a string has no
``outputSchema``: the string is the text. ``annotations`` tell a client how the
tool behaves, as ``readOnlyHint`` of a tool that changes nothing, as hints that
the client weighs, not as guarantees.

The server validates the arguments with the ``inputSchema`` before it calls
the function, so the function gets the arguments that it declares. The values
are those of JSON, as a string of a date, which the function converts itself.

Errors
------

A tool has two kinds of errors. An error of its execution, as arguments that
are not valid or a date in the past, is a result with ``isError``, whose text
the language model reads to call the tool again with other arguments: the
arguments that the ``inputSchema`` does not validate are one, and so is a
:class:`Pyjo.MCP.Tool.Error` that the function raises. An error of the
protocol, as a tool that does not exist, is an error of JSON-RPC, and an
exception of the function is an error of the server, which the application
logs, and whose message the client does not see.

.. literalinclude:: tutorial/errors.py
    :language: python

Asynchronous tools
------------------

A tool can return a :mod:`Pyjo.Promise` or be a coroutine, as a function
``async``, which awaits the non-blocking :mod:`Pyjo.UserAgent` of the
application, so that the server answers other requests while the tool waits
for another service. :mod:`Pyjo.DOM` takes a web page apart:

.. literalinclude:: tutorial/title.py
    :language: python

The example ``examples/weather.py`` of the distribution is a gateway to the
weather of Open-Meteo, made this way, with the tools ``find_places``,
``current_weather``, ``forecast`` and ``hourly_forecast``.

Context
-------

A tool with ``context`` gets the :class:`~Pyjo.MCP.Server.Context` of the
request before its arguments, with what the ``_meta`` of the request tells, as
the name of the client and the revision of the protocol, and the
:mod:`Pyjoyment.Controller` of the request of HTTP, with its headers and the
helpers of the application.

.. literalinclude:: tutorial/context.py
    :language: python

The protocol is stateless: a server does not keep anything of a client
between its requests. A tool that needs a state, as a basket of a shop,
returns a handle of it, which the language model passes to the next tool.

Progress
--------

A tool that takes long tells the client how far it is with
:meth:`~Pyjo.MCP.Server.Context.notify_progress`, and what it does with
:meth:`~Pyjo.MCP.Server.Context.notify_log`, before its result. The client
asks for them in the ``_meta`` of its request, with a ``progressToken`` and
the lowest level of the log messages that it wants, and the notifications that
it did not ask for go nowhere. Over Streamable HTTP, the first notification
turns the response into a stream of events, which ends with the result, when
the client accepts one, and a client that closes the connection before the
result cancels the request, which
:attr:`~Pyjo.MCP.Server.Context.is_cancelled` tells. Over the transport stdio,
the notifications are messages of the same stream:

.. literalinclude:: tutorial/progress.py
    :language: python

Prompts and resources
---------------------

A tool is what the language model calls; a prompt and a resource are what the
user picks. A prompt is a template of messages, as a task that the user starts
with its arguments, and a resource is data of the server, as a document or a
configuration, which the client reads by its URI and gives the language model
as its context. Both are functions too: the name and the description of a
prompt are those of its function, and its arguments are the parameters, whose
values are strings, of which those without a default are required. A resource
has its URI, and its media type, ``text/plain`` by default.

.. literalinclude:: tutorial/review.py
    :language: python

A prompt returns a string, which is one message of the user, or the messages
themselves, here with the style guide embedded as a resource before the
question. A resource returns a string, which is its text, :class:`bytes`,
which are its ``blob`` in Base64, or another value, whose JSON is the text, as
the limits here. Like a tool, both can return a :mod:`Pyjo.Promise` or be
coroutines, and get the :class:`~Pyjo.MCP.Server.Context` of the request with
``context``. The values of an argument with ``Literal``, as ``focus`` here, or
with an ``Enum``, are the completions that ``completion/complete`` gives a
client while the user types it.

Claude Code lists the prompts as commands, as ``/mcp__reviewer__review``,
which ask for the arguments, and the resources as mentions, as
``@reviewer:docs://style``, which put their contents into the conversation.

Resource templates
------------------

The resources that a server cannot list, as the files of a directory, are a
resource template, a URI Template of :rfc:`6570`: the client lists the
templates with ``resources/templates/list``, makes a URI of one of them, and
reads it with ``resources/read``. A URI with variables is a template, whose
function gets their values as keyword arguments, here the path of a file of
the directory of the script:

.. literalinclude:: tutorial/project.py
    :language: python

The values come from the client, so a URI whose value has a segment ``..``,
an absolute path or the character NUL, which would read a file outside of the
directory, has no resource, unless the template is made with ``safe=False``. A
function that finds nothing raises the error of JSON-RPC itself. A resource
that the server lists comes before a template that matches its URI too, and
the templates are tried in their order.

The option ``complete`` gives the completions of the values of the variables,
or of the arguments of a prompt: a list of the values, which the server filters
by what the user has typed, or a function, as here, that gets it and the values
of the other variables, and returns the values that fit, of which the server
gives at most 100.

Subscriptions
-------------

The lists of a server and its resources can change while it runs. A client
that wants to know opens a subscription with ``subscriptions/listen``, a
request that stays in progress, with the notifications that it asks for: of a
change of the list of the tools, of the prompts or of the resources, and of a
change of a resource of its URI. The application tells the server what changed
with :meth:`~Pyjo.MCP.Server.Pyjo_MCP_Server.notify_list_changed` and
:meth:`~Pyjo.MCP.Server.Pyjo_MCP_Server.notify_resource_updated`, and declares
that it does with ``list_changed`` and ``subscribe``, which
``server/discover`` tells the clients:

.. literalinclude:: tutorial/notes.py
    :language: python

A notification tells only what changed, so the client reads the list or the
resource again. Over Streamable HTTP, a subscription is a stream of events,
which a comment keeps open while nothing changes, and which the server ends
with a response when it stops gracefully. Over the transport stdio, its
messages share the stream with the others, and the client cancels it with
``notifications/cancelled``. The subscriptions are those of a worker, a
process of ``prefork`` or a thread of ``prethread``, so the worker that changes
a list notifies only its own clients.

Input
-----

A tool, a prompt or a resource can ask the client for input before it
answers: the user, with a form of ``elicitation/create``, the language model
of the client, with ``sampling/createMessage``, or the directories that the
client works on, with ``roots/list``. The server keeps no connection open for
it: the result ``input_required`` gives the client the requests, and the
client sends the same request again with their responses, a round of the
request each time. A function asks with
:meth:`~Pyjo.MCP.Server.Context.elicit`,
:meth:`~Pyjo.MCP.Server.Context.sample` or
:meth:`~Pyjo.MCP.Server.Context.list_roots` of its context, with a key that
names the request in every round, and gets the response once the client has
given it:

.. literalinclude:: tutorial/confirm.py
    :language: python

The function runs again from its beginning in each round, so what it does
before it asks has to be safe to repeat, as here deleting the file only once
the user confirms. The responses of the rounds before, and the values that the
function keeps in :attr:`~Pyjo.MCP.Server.Context.state`, come back with the
``requestState`` of the result, which the ``secrets`` of the application sign,
as they sign its cookies, and which expires after ten minutes: the client can
read it, but not change it. A client that does not declare the capability of
a request, ``elicitation``, ``sampling`` or ``roots``, gets the error
``-32021`` instead.

Security
--------

A server on ``localhost`` binds to ``127.0.0.1``, not to all the interfaces,
and :mod:`Pyjoyment.Plugin.AllowedHosts` takes the hosts of a deployment with
a name of its own. With ``hook=False``, it checks only the routes under its
helper ``allowed_hosts``, as here the endpoint of MCP, under a callback that
checks the bearer token of the client too, while the other pages of the
application stay open:

.. literalinclude:: tutorial/security.py
    :language: python

Claude Code sends the token with the header that it is given:

.. code-block:: console

    $ claude mcp add --transport http secure http://127.0.0.1:3000/mcp --header 'Authorization: Bearer sesame'

Standard input and output
-------------------------

The transport stdio needs no port, no ``Host`` and no token: the client
starts the server as its child process, and sends a message of JSON-RPC on
each line of its standard input, whose responses come on the lines of its
standard output. :meth:`~Pyjo.MCP.Server.Pyjo_MCP_Server.to_stdio` is the hook
that serves the tools so, when the command
:mod:`stdio <pyjoyment:Pyjoyment.Command.stdio>` starts the application, and
the same application still serves Streamable HTTP with ``daemon``:

.. literalinclude:: tutorial/stdio.py
    :language: python

The log of the application goes to the standard error, as anything else that
the tools print, so that only the messages of MCP are on the standard output.
The server ends when the client closes its standard input, once the requests
in progress have their responses. Claude Code starts it with the command:

.. code-block:: console

    $ claude mcp add hello -- uv run python stdio.py stdio

Testing
-------

:mod:`Pyjo.MCP.Test` tests a server without starting it, as
:mod:`Pyjo.Test.Pyjo` tests any application of Pyjoyment, with the requests
that :mod:`Pyjo.MCP.Client` sends: the ``_meta`` and the headers of MCP are
made for each request, the arguments of a tool are keyword arguments after its
name, and the assertions check the result, its text, its ``structuredContent``
and ``isError``, the tools of ``tools/list``, the notifications of a
subscription and the errors of JSON-RPC:

.. literalinclude:: tutorial/hello_test.py
    :language: python

.. code-block:: console

    $ uv run python -m Pyjo.Prove hello_test.py

More
----

The API of the server, of the tools, of the prompts, of the resources, of the
resource templates, of the client and of the tests is in
:mod:`Pyjo.MCP.Server`, :mod:`Pyjo.MCP.Tool`, :mod:`Pyjo.MCP.Prompt`,
:mod:`Pyjo.MCP.Resource`, :mod:`Pyjo.MCP.ResourceTemplate`,
:mod:`Pyjo.MCP.Client` and :mod:`Pyjo.MCP.Test`, and the deployment of an application, with the servers
of Pyjoyment and a container, in its :doc:`cookbook <pyjoyment:guides/cookbook>`.
