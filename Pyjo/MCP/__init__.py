"""
Pyjo.MCP - Model Context Protocol for Pyjoyment
===============================================
::

    import Pyjo.MCP

    print(Pyjo.MCP.PROTOCOL_VERSION)

:mod:`Pyjo.MCP` is the namespace of the `Model Context Protocol
<https://modelcontextprotocol.io>`_ for :mod:`Pyjoyment`, a server and a client
made with Pyjoyment, of the revision :data:`PROTOCOL_VERSION` of the
specification, whose core is stateless.

See also
--------

:mod:`Pyjoyment`, https://github.com/dex4er/Pyjoyment.

It has no counterpart in Mojolicious, and is inspired by the distribution
`MCP <https://metacpan.org/pod/MCP>`_ of CPAN, built on Mojolicious.
"""

__version__ = '0.1.0'

PROTOCOL_VERSION = '2026-07-28'
"""The revision of the specification of the Model Context Protocol, as ``MCP-Protocol-Version`` names it."""
