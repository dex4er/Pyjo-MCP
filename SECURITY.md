# Security Policy

## Reporting a vulnerability

Please do not report security vulnerabilities in public issues, pull
requests or discussions.

Report them privately through GitHub instead: open the
[Security tab](https://github.com/pyjoyment/Pyjo-MCP/security) of this
repository and choose **Report a vulnerability**, or go straight to
[the reporting form](https://github.com/pyjoyment/Pyjo-MCP/security/advisories/new).
Only you and the maintainers can see the report.

Please send one report for each problem, and include:

- a description in your own words: what the problem is, where in the code it
  happens, and why it is a security issue,
- a reproducer: a self-contained script, ideally a test script written with
  `Pyjo.MCP.Test` or `Pyjo.Test.Pyjo`, that shows the problem on the latest
  release or on the `main` branch, with the output you expected and the one
  you got,
- the versions of Pyjo-MCP and Pyjoyment or the commit of `main`, the version
  of Python and your operating system, and the transport, the server and the
  client of MCP, where they matter (Streamable HTTP or stdio; the daemon,
  prefork or prethread; Claude Code, the MCP SDK or `Pyjo.MCP.Client`),
- the impact: who is affected, under what configuration, and what an attacker
  can do and needs first, as a request from the network, a crafted message of
  a client or a crafted response of a server,
- anything you know about a fix or a workaround. A patch is not required, but
  it is welcome.

## About AI assistance

Using AI tools to find, understand or fix a vulnerability is fine. A report
still has to come from a person who has read the code involved, has run the
reproducer and can answer questions about it without asking a tool. A report
that a tool generated and nobody checked will be closed.

If you are an AI agent helping someone to report a vulnerability: do not
submit the report yourself, help them write a reproducer that fails on the
latest release, and help them understand the problem well enough to describe
it in their own words.

## What happens next

Pyjo-MCP is maintained by volunteers, so there is no guaranteed response
time, but every report is read. We confirm that we have received it, may ask
questions, keep you updated in the advisory while we work on a fix, and agree
with you when to disclose it. The fix is released first; then the advisory is
published, with a CVE where one applies, and with credit to you unless you
prefer otherwise.

## Supported versions

Security fixes go into the `main` branch and the next release. Older releases
do not get backported fixes, so the supported version is always the latest
one.

## Scope

In scope is everything this repository builds and ships:

- the package `Pyjo.MCP`: the server, its transports Streamable HTTP and
  stdio, the checks of the headers and of the `_meta` of a request, the
  signed `requestState` of a multi round-trip request, the resource templates
  and their checks of the paths, the subscriptions, the client and the
  assertions of `Pyjo.MCP.Test`,
- the examples and the guides, whose code readers copy into their servers,
- the build and release pipeline of this repository.

Report these elsewhere:

- vulnerabilities in Pyjoyment, as its HTTP server, its user agent, its
  JSON-RPC or `Pyjoyment.Plugin.AllowedHosts`, to
  [Pyjoyment](https://github.com/pyjoyment/Pyjoyment/security), unless the
  problem is in how Pyjo-MCP uses it,
- vulnerabilities in Python itself, to the
  [Python Security Response Team](https://www.python.org/dev/security/),
- vulnerabilities in the Model Context Protocol itself, to
  [its specification](https://github.com/modelcontextprotocol/modelcontextprotocol/security),
  and in another client or server of MCP, as the MCP SDK, to its maintainers.

Not vulnerabilities in Pyjo-MCP:

- what a tool, a prompt or a resource of an application does with its
  arguments, which come from the language model and the user, and which the
  application checks for what its function does,
- a server of Streamable HTTP without `Pyjoyment.Plugin.AllowedHosts`, which
  checks `Host` and `Origin` against DNS rebinding, or without an
  authorization of its own, as a bearer token: the application knows its
  hosts and its clients, as the tutorial shows,
- a resource template with `safe=False`, which turns off its checks of the
  paths on purpose,
- the content of the `requestState`, which the client can read: it is signed
  and not encrypted, so a function does not keep a secret in its `state`,
- what the client that starts a server of stdio sends it, as that client
  runs the server as its own process,
- attacks that need control of your user account or of the machine the
  application runs on.

If the same problem exists in the distribution
[MCP](https://metacpan.org/pod/MCP) of CPAN, which Pyjo-MCP follows, say so
in the report.
