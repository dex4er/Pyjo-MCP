# Agent Guide: Pyjo-MCP

## Overview

`Pyjo.MCP` is a server and a client of the Model Context Protocol made with
Pyjoyment, without the MCP SDK, in a distribution of its own, as the protocol
changes faster than the framework. It follows the revision 2026-07-28 of the
specification only, whose core is stateless. The conventions are those of
Pyjoyment: read its `AGENTS.md` in the checkout next to this one,
`../Pyjoyment/AGENTS.md`. The plan, and what goes to the core of Pyjoyment
first, is in the issue of Pyjoyment about MCP.

The reference is the distribution `MCP` of CPAN, built on Mojolicious, under
the MIT license.

## The Server

`Pyjo.MCP.Server` is made on `Pyjo.JSON.RPC` of Pyjoyment: its methods,
`server/discover`, `tools/list` and `tools/call`, are methods of a dispatcher
of JSON-RPC that get the `Context` of the request, and `dispatch_p` takes a
message of any transport. A batch and a request with the `id` of `null` are
invalid requests, as MCP has neither. Each method checks the `_meta` of its
request first, as the protocol is stateless: there is no `initialize`, and
every request carries its revision and the capabilities of its client.

`to_action` is the transport Streamable HTTP. The status of HTTP of an error
is not a function of its code: `-32602` is `400 Bad Request` for a `_meta`
without its required fields, as the specification requires, but `200 OK` for
an unknown tool, as the example of the specification of the tools has it. So
the check that raises the error sets `status` of the `Context`, and the codes
give the status otherwise: `-32601` is `404 Not Found`, which tells a modern
server from a legacy one, `-32603` is `500 Internal Server Error`, and
`-32700` and `-32600` are `400 Bad Request`. The headers of MCP,
`MCP-Protocol-Version`, `Mcp-Method`, `Mcp-Name` and the `Mcp-Param-{name}` of
the `x-mcp-header` of a tool, are checked against the body before the
dispatch, for a request only, as the specification defines no headers of a
notification. `to_action` does not check `Host` and `Origin`:
`Pyjoyment.Plugin.AllowedHosts` does, as the application knows its hosts.

The notifications of a request, as its progress and its log messages, go
before its result, through `stream` of its `Context`, which the transport
sets. Over Streamable HTTP, the first notification turns the response into a
stream of events, so a request without notifications, also an asynchronous
one, is answered with JSON, as before, where `MCP::Server` of the Perl `MCP`
opens the stream for every result that is a promise. The stream needs a client
that has `text/event-stream` in its `Accept`; for another one the notifications
go nowhere and the result is JSON. The stream has no inactivity timeout, as a
tool may take long between two notifications, and `X-Accel-Buffering: no`, so
that nginx passes each event at once. The connection of the stream that closes
before the result cancels the `Context`, which emits `cancelled` once, and the
result of a cancelled request is not written. A notification that the client
did not ask for, progress without a `progressToken` or a log message below its
`logLevel`, is not sent at all.

## The Transport stdio

`to_stdio` is the hook `before_server_start` that serves the server on the
standard input and output of `Pyjo.Server.Stdio`, when the command `stdio` of
Pyjoyment starts the application, and does nothing for another server, so that
one application serves both transports. The stream, its framing of lines, the
protection of the standard output and the end at the end of the input are those
of Pyjoyment (`Pyjo.IOLoop.Stdio`, `Pyjo.IOLoop.Messages`, dex4er/Pyjoyment#361):
the distribution only connects them.

`serve` hands each message to `Pyjo.JSON.RPC.serve` with its `dispatch_p`
(dex4er/Pyjoyment#375), not to the dispatcher of JSON-RPC directly, for two
reasons. Each request needs a `Context` of its own, as `_meta` writes the
revision and the capabilities of the client into it, while the `context` of
`serve` is one for all the requests of the stream, which are served at the same
time. And `dispatch_p` of the server rejects the batches and the `id` of
`null`, which the dispatcher of JSON-RPC accepts. The `Context` has no
controller over stdio, so it carries the log of the application, which gets the
errors of the server that the controller logs over HTTP.
The `stream` of the `Context` sends a notification of the request with `notify`
of the client of the peer, so it is a message of the same stream, before the
response.

## The Client

`Pyjo.MCP.Client` follows `MCP::Client` of the Perl `MCP`: it builds the
requests itself, with the `_meta` of the client over the one of the
parameters, and not with the client of `Pyjo.JSON.RPC`, as an id of its own
and the headers made from the body belong to each request. Its methods block,
as those of the Perl client, and each has a form `_p` with a promise, as
`Pyjo.UserAgent` has them. The prompts, the resources, `subscriptions/listen`
and the options of the multi round-trip requests come with them in the server.

A client knows the `x-mcp-header` of a tool only from its definition, so the
headers `Mcp-Param-{name}` of a call come from `tools`, which the last
response of `tools/list` that `read_response` reads gives, and a call before
it sends none, which the server rejects for a tool with such a header. A tool whose `x-mcp-header` the specification does
not allow is left out of the result of `list_tools`, as the specification
requires of a client, with the event `invalid_tool`, which tells why.

`build_tx` subscribes the event `sse` of the content of the response, as
`Pyjo.Content` parses the events of a stream with a `Content-Length` or one
that the connection ends, and takes them from the body, so the response of
JSON-RPC among them is kept by the transaction, in a weak dictionary, until
the response is read. A chunked stream, as a server of a framework that
streams its response writes, is not parsed by `Pyjo.Content`: its events stay
in the body, which the client parses at the end. Every other message of the
stream is the event `notification`.

## The Tests

`Pyjo.MCP.Test` is a subclass of `Pyjo.Test.Pyjo`, in the package of the
distribution, as the namespace `Pyjo.Test` of Pyjoyment is not open, and the
revision and the headers of MCP change faster than Pyjoyment. A request is the
transaction of `build_tx` of its `client`, which `request_ok` sends, so that a
test sends what the client sends, and `read_response` of the client reads the
response of JSON-RPC into `response`, from JSON or from a stream of events,
which the assertions test, as `json_is` of `Pyjo.Test.Pyjo` reads only a body
of JSON. `mcp_ok` changes the `id`, the `_meta` and the headers of a request
after the client builds it, as a test of a server sends what a client must
not.

The name of a tool is positional only in `call_ok`, and its arguments are
keyword arguments, so that no argument of a tool clashes with a parameter of
the method; the headers and the `_meta` of a call go through `mcp_ok`, or
`headers` of the client for all the requests. A private method of the class
has a name that `Pyjo.Test.Pyjo` does not have, as a subclass would replace
the one that its own assertions call, as `_text` of `text_is`. The default
description of an assertion names what it checks, not the value, which can
have a new line that would break the line of TAP.

## The Tools

A tool is a function, whose `inputSchema` and `outputSchema` are those of
`Pyjo.JSON.Schema` of its type hints. Arguments that the `inputSchema` does
not validate give a result with `isError`, not the error `-32602`: the
specification counts the validation of the input among the errors of the
execution of a tool, which the language model reads to correct its call,
while an unknown tool and arguments that are not an object are errors of the
protocol. A function that returns a string, or the annotation of a string, an
enum of strings or a date, gets no `outputSchema`, and its value is the text of
the content; a value of an `outputSchema` that does not validate is an error
of the server, not of the language model.

## The Guides

The guides are pages of `docs/guides`, as the guides of Pyjoyment: an example
that is a whole application is a file of its own, in a directory with the name
of the page, as `docs/guides/tutorial/`, which the page includes with
`literalinclude`, and which the test of the guide, as
`t/docs/guides_tutorial.py`, loads with `Pyjo.Test.Pyjo` and calls with the
requests of MCP, so that what the reader sees is what is tested. A remote
service of an example is answered by a mock, a route of the test, where the
event `start` of the user agent of the application sends the requests, as
the tests do not use the network. The guides link to the documentation of
Pyjoyment with intersphinx, as `:doc:` with the prefix `pyjoyment:`, for what
it teaches already, as the commands and the servers.

## Imports of the Package

The modules of the distribution import the package and each other relatively,
`from .. import MCP` and `from . import Tool`, not as `import Pyjo.MCP.Tool`:
pyright takes `Pyjo` for the regular package of Pyjoyment in `.venv`, which
hides the namespace that `extend_path` keeps open, so it does not find
`Pyjo.MCP` of the checkout. The tests and the documentation import them as
`Pyjo.MCP.Server`, which Python finds through `extend_path`.

## The MCP SDK

`t/sdk` runs the client of the MCP SDK, of the dependency group `sdk`, against
the server of `examples/calculator.py`, as an implementation of the
specification of its own; without the group, the test is skipped. The server
runs in a process of its own, as the client runs the event loop of asyncio in
the process of the test, and the job `sdk` of the workflow Tests runs it:

```sh
mise exec -- uv run --group sdk --with-editable ../Pyjoyment python -m Pyjo.Prove -l -r t/sdk
```

## Development

The distribution depends on Pyjoyment of its Git repository, as the revival
of Pyjoyment is not on PyPI yet (`[tool.uv.sources]` of `pyproject.toml`). A
path to the checkout next to this one cannot be the source: uv applies the
sources of a dependency of Git, so whoever installs the distribution from Git
would get a subdirectory of this repository that does not exist. The tests lay
the checkout next to this one over it with `--with-editable`, so that they
test what is there:

```sh
mise exec -- uv sync
mise exec -- uv run --with-editable ../Pyjoyment python -m Pyjo.Prove -l -r t
```

Perl's `prove` runs them too, with `.proverc`, under `uv run`, whose `python`
is the one of the environment, where Pyjoyment and the distribution are
installed, so that it needs no `PYTHONPATH`, unlike in Pyjoyment:

```sh
mise exec -- uv run --with-editable ../Pyjoyment prove -r t
```

The package is in the namespace `Pyjo` of Pyjoyment, which `extend_path` keeps
open, so the tests of Pyjoyment run with the distribution installed as well:

```sh
cd ../Pyjoyment
mise exec -- uv run --project ../Pyjo-MCP --with-editable . python -m Pyjo.Prove -l -j 4 -r t
```

Trunk checks the files with the linters of Pyjoyment, from `.trunk/trunk.yaml`:

```sh
trunk check --all
```

actionlint is the one of the maintained fork kjanat/actionlint, whose releases
continue those of rhysd/actionlint after 1.7.12, as in Pyjoyment: `downloads`
in `.trunk/trunk.yaml` replaces the URLs of the plugin with those of the fork,
whose files have the same names.

Its pyright needs the environment of `uv sync`, `.venv`, which `tool.pyright` of
`pyproject.toml` names, as the package imports Pyjoyment; Trunk Check of CI
runs `uv sync` first. The tests and `docs/conf.py` are not checked by pyright:
for them it takes the regular package `Pyjo` of Pyjoyment, which hides
`Pyjo.MCP` of the checkout.

The wheel has only the package `Pyjo.MCP` (`only-include` of hatchling), not
the `__init__.py` of `Pyjo`, which is the one of Pyjoyment; the workflow Build
checks it.

The documentation is on Read the Docs, a subproject of the one of Pyjoyment:
the docstrings of the package, which autodoc imports, as in Pyjoyment. Read the
Docs installs it with `uv sync` of `uv.lock` and the group `docs`, not with pip
and a `docs/requirements.txt` as Pyjoyment does: pip does not read
`[tool.uv.sources]`, so it would take Pyjoyment from PyPI. The links to the
modules of Pyjoyment come from intersphinx. The workflow Docs builds it with
`-W`, as Read the Docs does, with the Pyjoyment of `uv.lock`:

```sh
mise exec -- uv run --group docs --with-editable ../Pyjoyment sphinx-build -W --keep-going -b html docs docs/_build/html
```

`t/docs/MCP.py` runs the synopsis of the package, as `t/docs` of Pyjoyment
does.
