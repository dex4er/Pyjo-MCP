"""
Pyjo.MCP - Model Context Protocol for Pyjoyment
===============================================
::

    import Pyjo.MCP

    print(Pyjo.MCP.PROTOCOL_VERSION)

    # Pyjoyment.Lite
    from Pyjo.MCP.Server import Server
    from Pyjoyment.Lite import *

    server = Server(name='calculator', version='1.0.0')

    @server.tool
    def add(a: int, b: int) -> int:
        \"\"\"Add two numbers.\"\"\"
        return a + b

    plugin('AllowedHosts')
    any('/mcp', server.to_action())

    app.start()

:mod:`Pyjo.MCP` is the namespace of the `Model Context Protocol
<https://modelcontextprotocol.io>`_ for :mod:`Pyjoyment`, a server and a client
made with Pyjoyment, of the revision :data:`PROTOCOL_VERSION` of the
specification, whose core is stateless: every request carries its version and
the capabilities of its client in its ``_meta``, without a session.

:mod:`Pyjo.MCP.Server` is the server, whose tools are :mod:`Pyjo.MCP.Tool`
objects, :mod:`Pyjo.MCP.Client` is the client, and the messages are those of
:mod:`Pyjo.JSON.RPC`.

See also
--------

:mod:`Pyjo.MCP.Server`, :mod:`Pyjo.MCP.Tool`, :mod:`Pyjo.MCP.Client`,
:mod:`Pyjoyment`, https://github.com/dex4er/Pyjoyment.

It is inspired by the distribution `MCP <https://metacpan.org/pod/MCP>`_ of
CPAN, built on Mojolicious.
"""

__version__ = '0.1.0'

PROTOCOL_VERSION = '2026-07-28'
"""The revision of the specification of the Model Context Protocol, as ``MCP-Protocol-Version`` names it."""

SUPPORTED_VERSIONS = (PROTOCOL_VERSION,)
"""The revisions that the server supports, as ``server/discover`` gives them."""

HEADER_MISMATCH = -32020
"""The code of the error of a header of HTTP that does not match the body of the request, or that is missing."""
MISSING_REQUIRED_CLIENT_CAPABILITY = -32021
"""The code of the error of a request that needs a capability that its client does not declare."""
UNSUPPORTED_PROTOCOL_VERSION = -32022
"""The code of the error of a request of a revision that the server does not support."""

META_CLIENT_CAPABILITIES = 'io.modelcontextprotocol/clientCapabilities'
"""The key of ``_meta`` of a request with the capabilities of its client."""
META_CLIENT_INFO = 'io.modelcontextprotocol/clientInfo'
"""The key of ``_meta`` of a request with the name and the version of its client."""
META_LOG_LEVEL = 'io.modelcontextprotocol/logLevel'
"""The key of ``_meta`` of a request with the level of the log messages that its client wants."""
META_PROTOCOL_VERSION = 'io.modelcontextprotocol/protocolVersion'
"""The key of ``_meta`` of a request with its revision of the specification."""
META_SERVER_INFO = 'io.modelcontextprotocol/serverInfo'
"""The key of ``_meta`` of a result with the name and the version of its server."""
