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

:mod:`Pyjo.Test.Pyjo` tests a server without starting it, as any application
of Pyjoyment, with the requests of MCP that a client sends:

.. literalinclude:: tutorial/hello_test.py
    :language: python

.. code-block:: console

    $ uv run python -m Pyjo.Prove hello_test.py

More
----

The API of the server and of the tools is in :mod:`Pyjo.MCP.Server` and
:mod:`Pyjo.MCP.Tool`, and the deployment of an application, with the servers
of Pyjoyment and a container, in its :doc:`cookbook <pyjoyment:guides/cookbook>`.
