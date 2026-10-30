import Pyjo.MCP.Test

from Pyjo.Test import *

import contextlib
import io


with subtest('Synopsis'):
    with contextlib.redirect_stdout(io.StringIO()) as stdout:
        import Pyjo.MCP

        print(Pyjo.MCP.PROTOCOL_VERSION)
    is_ok(stdout.getvalue(), '2026-07-28\n', 'protocol version')

    # Pyjoyment.Lite
    from Pyjo.MCP.Server import Server
    from Pyjoyment.Lite import *

    server = Server(name='calculator', version='1.0.0')

    @server.tool
    def add(a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    plugin('AllowedHosts')
    any('/mcp', server.to_action())

    # Instead of app.start(), the application of Pyjoyment.Lite of the test
    app.log.level = 'fatal'
    t = Pyjo.MCP.Test.new()
    t.call_ok('add', a=1, b=2).status_is(200).structured_content_is(3)
    t.list_tools_ok(headers={'Host': 'evil.com'}).status_is(421)

with subtest('Constants'):
    is_deeply_ok(Pyjo.MCP.SUPPORTED_VERSIONS, ('2026-07-28',), 'SUPPORTED_VERSIONS')
    is_deeply_ok(
        [Pyjo.MCP.HEADER_MISMATCH, Pyjo.MCP.MISSING_REQUIRED_CLIENT_CAPABILITY, Pyjo.MCP.UNSUPPORTED_PROTOCOL_VERSION],
        [-32020, -32021, -32022],
        'codes of the errors',
    )
    is_ok(Pyjo.MCP.META_PROTOCOL_VERSION, 'io.modelcontextprotocol/protocolVersion', 'META_PROTOCOL_VERSION')
    is_ok(Pyjo.MCP.META_CLIENT_CAPABILITIES, 'io.modelcontextprotocol/clientCapabilities', 'META_CLIENT_CAPABILITIES')
    is_ok(Pyjo.MCP.META_CLIENT_INFO, 'io.modelcontextprotocol/clientInfo', 'META_CLIENT_INFO')
    is_ok(Pyjo.MCP.META_LOG_LEVEL, 'io.modelcontextprotocol/logLevel', 'META_LOG_LEVEL')
    is_ok(Pyjo.MCP.META_SERVER_INFO, 'io.modelcontextprotocol/serverInfo', 'META_SERVER_INFO')
    is_ok(Pyjo.MCP.META_SUBSCRIPTION_ID, 'io.modelcontextprotocol/subscriptionId', 'META_SUBSCRIPTION_ID')

t.ua.close()

done_testing()
