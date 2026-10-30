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
`server/discover`, `tools/list`, `tools/call`, `prompts/list`, `prompts/get`,
`resources/list`, `resources/templates/list`, `resources/read`,
`subscriptions/listen` and `completion/complete`, are methods of a dispatcher
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
response. `notifications/cancelled` of the peer cancels the `Context` of the
request of its `requestId`, as a connection that closes does over Streamable
HTTP, and `serve` drops the response of a cancelled request, as the
specification asks of a server.

## The Client

`Pyjo.MCP.Client` follows `MCP::Client` of the Perl `MCP`: it builds the
requests itself, with the `_meta` of the client over the one of the
parameters, and not with the client of `Pyjo.JSON.RPC`, as an id of its own
and the headers made from the body belong to each request. Its methods block,
as those of the Perl client, and each has a form `_p` with a promise, as
`Pyjo.UserAgent` has them. `listen` gives the messages of a subscription to a
function, as `listen` of the Perl client does, which closes it by returning
`False`, not any false value, as a function of Python that returns nothing
returns `None`. The options `input_responses` and `request_state` of
`call_tool`, `get_prompt` and `read_resource` send a round of a multi
round-trip request, as the options of the Perl client do, and a result
`input_required` is a result, which the caller answers, as the client does not
know the user nor a language model.

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

## The Prompts and the Resources

A prompt and a resource are functions, as a tool, but without the schemas of
JSON Schema: an argument of a prompt has only its name, its description and
whether it is required, as the specification gives it no type, and its values
are strings, so the parameters of the function are those of `parameters` of
`Pyjo.JSON.Schema`, without their schemas. A missing required argument, or one
that the function does not take, is the error `-32602` of the protocol, not a
result with `isError` as of a tool, as the result of a prompt has no
`isError`. An unknown prompt is `-32602` with `200 OK`, as an unknown tool, and
an unknown resource `-32602` with the message `Resource not found` and its URI
in `data`, as the specification has it.

The result of `resources/read` is cacheable, with the `ttlMs` and the
`cacheScope` of the server, as the results of the lists, and the one of
`prompts/get` is not, as the specification has them. A resource is a URI of
its own, as `file:///` or a scheme of the server.

A URI of `resource` with variables is a resource template, a URI Template of
RFC 6570, whose `Pyjo.URL.Template` of Pyjoyment matches the URIs of
`resources/read` that no resource has, in the order of the templates, and
whose function gets the values of the variables as keyword arguments. The
RFC leaves the match to the implementations, so it is the one of
`Pyjo.URL.Template`, linear in the length of the URI, and a template whose
expressions it cannot tell apart raises when it is added, not at its first
read. The values come from the client, and a function of a template that
reads files is the common case, so a value with a segment `..`, an absolute
path of Unix or of Windows or NUL has no resource by default, also when it
is percent-encoded, as the match decodes it; `safe=False` turns that off. A
URI without a value that the function requires has no resource either, as
the client made it, not the server.

`completion/complete` completes the value of an argument of a prompt or of a
variable of a resource template, from `complete` of the prompt or of the
template: a list, which the server filters by the prefix that the user has
typed, in any case, as a short list of names is the common case, or a
function, whose values the server takes as they are, as only the function
knows how to search what it has, and which gets the values of the other
arguments, the `context.arguments` of the request, as the owner of a
repository narrows its names. The values of a parameter of a prompt with
`Literal` or `Enum` complete by default, from the `enum` of the schema of
`Pyjo.JSON.Schema`. The result has at most 100 values, as the specification
allows, with `total` and `hasMore`, and `server/discover` declares
`completions` only for a server that has some. The request has no header
`Mcp-Name`, as the specification names it only for `tools/call`,
`prompts/get` and `resources/read`, and its parameter `context` is not the
`Context` of the method, which the dispatcher passes by its position.

## The Subscriptions

`subscriptions/listen` is a request that stays in progress: its method returns
a promise that the server settles when the subscription ends, gracefully with
the response that the specification has for it, or with `None` when the client
cancels it, whose response is not written. The acknowledgment is the first
notification of the `Context`, which opens the stream of events over Streamable
HTTP, as any notification does, and the request needs that stream, so a client
without `text/event-stream` in its `Accept` gets `-32600`. The acknowledgment
honors every notification that the client asks for, also a resource that the server does not have, which may come later; `list_changed`
and `subscribe` of the server only declare in `server/discover` that the
application sends them.

A server ends a subscription with a response, not with `notifications/cancelled`,
which the page of the cancellation names for it: the page of the subscriptions,
which describes the graceful closure, gives the response. Over Streamable HTTP, the event `finish` of the event loop, which a graceful
stop emits, ends the subscriptions of its connections, as a stream that stays
open would keep the server waiting until its timeout, and a recurring timer
writes a comment of the stream every `heartbeat` seconds, which keeps a proxy
from closing it. Over stdio, the end of the input ends the subscriptions of its
peer, as `Pyjo.JSON.RPC.serve` closes the stream only once the requests in
progress have their responses.

The subscriptions are kept in a `threading.local` of the server, as a stream is
written by the event loop of the thread of its connection, and the threads of
`Pyjo.Server.Prethread` share the server: `notify_list_changed` and
`notify_resource_updated` reach the subscriptions of their worker only, a
process of prefork or a thread of prethread, as the specification asks for no
more, and an application whose change all its workers must tell, as a file
that changes, watches it in each of them.

## The Input

A request that needs input of the client, `tools/call`, `prompts/get` or
`resources/read`, is a multi round-trip request: the server answers with the
result `input_required` of its `inputRequests`, and the client sends the same
request again with their `inputResponses`, as the revision 2026-07-28 has no
requests of the server to the client. A function asks for input with
`Context.input` and its forms `elicit`, `sample` and `list_roots`, which
return the response of a key once the client has given it, and raise
`InputRequired` before, so the function runs again from its beginning in each
round, and what it does before it asks has to be safe to repeat. The
alternative, a function that returns the requests and the state itself, needs
the same code in every function, and a coroutine cannot be suspended across
requests, which may come to another worker. `InputRequired` is an `Exception`,
not a `BaseException`, as the promises of the tools and the event loop catch
only an `Exception`, so a function that catches every `Exception` lets it go.

The client sends the responses of the last round only, so the server keeps
the ones of the rounds before, and the `state` of the function, in the
`requestState` of the result: JSON in Base64 for URLs, signed with HMAC-SHA256
of a secret of `secrets` of the server, or of the application of the request,
the first one signing and all of them verifying, as the signed cookies of
Pyjoyment, so that every worker of prefork and prethread verifies what another
one signed. The state is bound to the method, the name or the URI and a digest
of the arguments of the request, and expires after `state_timeout`, so that it
cannot be replayed on another request; it is signed and not encrypted, as the
standard library has no cipher, so the client reads it. A request that needs
a capability that the client does not declare, `elicitation`, `sampling` or
`roots`, is the error `-32021`, with `requiredCapabilities` in its `data`.

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
the server of `examples/calculator.py` and the ones of the tutorial, of the
progress, of the prompts and resources, of the resource templates and of the
subscriptions, as an implementation of the specification of its own; without
the group, the test is skipped. The server runs in a process of its own, as the
client runs the event loop of asyncio in the process of the test, and the job
`sdk` of the workflow Tests runs it:

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
