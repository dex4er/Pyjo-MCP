from Pyjo.Test import *

import contextlib
import io


with subtest('Synopsis'):
    with contextlib.redirect_stdout(io.StringIO()) as stdout:
        import Pyjo.MCP

        print(Pyjo.MCP.PROTOCOL_VERSION)
    is_ok(stdout.getvalue(), '2026-07-28\n', 'protocol version')

done_testing()
