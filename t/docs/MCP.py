import Pyjo.Test.Pyjo

from Pyjo.Test import *

import contextlib
import io


META = {'io.modelcontextprotocol/protocolVersion': '2026-07-28', 'io.modelcontextprotocol/clientCapabilities': {}}

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
    t = Pyjo.Test.Pyjo.new()
    headers = {'MCP-Protocol-Version': '2026-07-28', 'Mcp-Method': 'tools/call', 'Mcp-Name': 'add'}
    params = {'name': 'add', 'arguments': {'a': 1, 'b': 2}, '_meta': META}
    t.post_ok('/mcp', headers, json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': params})
    t.status_is(200).json_is('/result/structuredContent', 3)
    t.post_ok('/mcp', {**headers, 'Host': 'evil.com'}, json={'jsonrpc': '2.0', 'id': 1}).status_is(421)

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

t.ua.close()

done_testing()
