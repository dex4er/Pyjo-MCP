import Pyjo.MCP

from Pyjo.Test import *

import re


# The package of the distribution, in the namespace Pyjo of Pyjoyment, which extend_path keeps open

with subtest('Namespace'):
    import Pyjo.URL

    like_ok(Pyjo.MCP.__file__, r'Pyjo[\\/]MCP[\\/]__init__\.py$', 'package of the distribution')
    ok(Pyjo.URL.new('http://example.com').host == 'example.com', 'modules of Pyjoyment')

with subtest('Versions'):
    like_ok(Pyjo.MCP.__version__, re.compile(r'^\d+\.\d+\.\d+$'), 'version of the distribution')
    is_ok(Pyjo.MCP.PROTOCOL_VERSION, '2026-07-28', 'revision of the protocol')

done_testing()
