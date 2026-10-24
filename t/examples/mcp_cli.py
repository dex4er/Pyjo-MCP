import Pyjo.IOLoop
import Pyjo.MCP.Server
import Pyjo.Test.Pyjo
import Pyjo.UserAgent
import Pyjoyment

from Pyjo.File import curfile
from Pyjo.Test import *

import contextlib
import importlib.util
import io
import json
import re


# The client of the command line of examples/mcp_cli.py, whose user agent requests the applications of the test, without
# a server of their own
ROOT = curfile().dirname().dirname().dirname()
spec = importlib.util.spec_from_file_location('mcp_cli', ROOT.child('examples', 'mcp_cli.py').to_str())
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


def app(path):
    loaded = Pyjo.Test.Pyjo.new(path).app
    loaded.log.level = 'fatal'
    return loaded


def run(application, *args):
    # A user agent of its own for each application, which its server keeps, with the blocking requests on the event loop
    # of the singleton, as Pyjo.Test.Pyjo has them, as the server of the application settles its promises there, which
    # the event loop of a blocking request of its own would not run
    cli.ua.close()
    cli.ua = Pyjo.UserAgent.new(ioloop=Pyjo.IOLoop.singleton)
    cli.ua.server.app = application
    with contextlib.redirect_stdout(io.StringIO()) as stdout, contextlib.redirect_stderr(io.StringIO()) as stderr:
        code = cli.main(['-u', '/mcp', *args])
    return code, stdout.getvalue(), stderr.getvalue()


calculator = app(ROOT.child('examples', 'calculator.py'))
shop = app(ROOT.child('docs', 'guides', 'tutorial', 'schemas.py'))

# A server of a tool with the headers of x-mcp-header, which it checks, and an argument of an array
sql = Pyjoyment.new()
sql.log.level = 'fatal'
server = Pyjo.MCP.Server.new(name='sql')
schema = {
    'type': 'object',
    'properties': {
        'region': {'type': 'string', 'description': 'The region', 'x-mcp-header': 'Region'},
        'query': {'type': 'string', 'description': 'The SQL query'},
        'limit': {'type': 'integer', 'x-mcp-header': 'Limit'},
        'tags': {'type': 'array', 'items': {'type': 'string'}},
    },
    'required': ['region', 'query'],
}
server.tool(
    'execute_sql',
    lambda region, query, limit=None, tags=(): f'{region}: {query} {limit} {list(tags)}',
    input_schema=schema,
)
sql.routes.any('/mcp').to(cb=server.to_action())

with subtest('Commands'):
    code, out, err = run(calculator)
    is_ok(code, 0, 'success')
    like_ok(out, re.compile(r'^Usage: python mcp_cli\.py \[OPTIONS\] \[COMMAND\] \[OPTIONS\]$', re.M), 'usage')
    like_ok(out, re.compile(r'^Commands:\n  add       Add two numbers\.\n  subtract  ', re.M), 'commands')
    like_ok(out, re.compile(r'^  divide    Divide the first number by the second one\.$', re.M), 'command')
    is_ok(err, '', 'no errors')
    is_ok(run(calculator, 'help')[1], out, 'help')
    is_ok(run(calculator, '--help')[1], out, '--help')

with subtest('Help of a command'):
    code, out, err = run(calculator, 'divide', '--help')
    is_ok(code, 0, 'success')
    is_ok(
        out,
        'Usage: python mcp_cli.py divide [OPTIONS]\n'
        '\n'
        'Divide the first number by the second one.\n'
        '\n'
        'Options:\n'
        '  -a, --a <number>      required\n'
        '  -b, --b <number>      required\n'
        '  -f, --format <name>   Format of the result, "text" or "json", defaults to\n'
        '                        "text"\n'
        '  -h, --help            Show this summary of available options\n',
        'usage',
    )
    code, out, err = run(shop, 'search', '-h')
    like_ok(
        out,
        re.compile(r'^  -q, --query <string>  +Part of the name of an item, in any case, required$', re.M),
        'string',
    )
    like_ok(
        out,
        re.compile(r'^  -l, --limit <integer>  +How many items at most, from 1 to 10, defaults to 5$', re.M),
        'integer',
    )
    like_ok(out, re.compile(r'^  -s, --sort <string>  +Order of the items, one of "name", "price"', re.M), 'enum')
    like_ok(out, re.compile(r'^  -i, --in-stock  +Only the items that are in stock, defaults to false$', re.M), 'flag')
    code, out, err = run(sql, 'execute-sql', '--help')
    like_ok(out, re.compile(r'^  -t, --tags <json>$', re.M), 'JSON')
    like_ok(out, re.compile(r'^  -r, --region <string>  +The region, required$', re.M), 'short option')

with subtest('Text'):
    code, out, err = run(calculator, 'add', '-a', '1', '-b', '2')
    # 3.0 of the json module, or 3 of the port of Mojo::JSON
    like_ok(out, re.compile(r'^3(?:\.0)?\n\Z'), 'scalar')
    is_deeply_ok(run(calculator, 'divide', '--a', '7', '--b', '2'), (0, '3.5\n', ''), 'long options')
    code, out, err = run(shop, 'search', '-q', 'PYJO', '-s', 'price')
    is_ok(
        out,
        'name          price  stock\nPyjo sticker  1.5    100\nPyjo mug      12.5   3\nPyjo shirt    25.0   0\n',
        'table in the order of the outputSchema',
    )
    code, out, err = run(shop, 'search', '-q', 'pyjo', '--in-stock', '-l', '1')
    is_ok(out, 'name      price  stock\nPyjo mug  12.5   3\n', 'flag and integer')
    code, out, err = run(shop, 'search', '-q', 'shirt', '--no-in-stock')
    like_ok(out, re.compile(r'^Pyjo shirt  25\.0   0$', re.M), 'negated flag')
    is_ok(run(shop, 'search', '-q', 'nothing')[1], '[]\n', 'empty list as the text of the server')

with subtest('JSON'):
    code, out, err = run(calculator, '-f', 'json', 'divide', '-a', '7', '-b', '2')
    is_deeply_ok((code, json.loads(out)), (0, 3.5), 'format before the command')
    code, out, err = run(shop, 'search', '-q', 'mug', '--format', 'json')
    is_deeply_ok(json.loads(out), [{'name': 'Pyjo mug', 'price': 12.5, 'stock': 3}], 'format after the command')
    like_ok(out, re.compile(r'^\[\n  \{\n    "name": "Pyjo mug",\n    "price": 12\.5,'), 'indented in order')

with subtest('Headers of the arguments'):
    code, out, err = run(sql, 'execute-sql', '-r', 'Hello, 世界', '-q', 'SELECT 1', '-l', '5', '--tags', '["a", "b"]')
    is_deeply_ok((code, out, err), (0, "Hello, 世界: SELECT 1 5 ['a', 'b']\n", ''), 'Mcp-Param- in Base64 and plain')
    code, out, err = run(sql, 'execute-sql', '-r', 'eu', '-q', 'SELECT 1')
    is_deeply_ok((code, out), (0, 'eu: SELECT 1 None []\n'), 'no header without the argument')
    code, out, err = run(sql, 'execute-sql', '-r', 'eu', '-q', 'x', '--tags', '[1')
    is_ok(code, 2, 'invalid JSON')
    like_ok(err, re.compile(r'tags'), 'message of the option')

with subtest('Errors'):
    code, out, err = run(calculator, 'divide', '-a', '1', '-b', '0')
    is_deeply_ok((code, out, err), (1, '', 'Division by zero\n'), 'error of the tool')
    code, out, err = run(calculator, 'add', '-a', '1')
    is_deeply_ok((code, err), (2, 'Missing --b, see python mcp_cli.py add --help\n'), 'missing option')
    code, out, err = run(calculator, 'add', '-a', 'x', '-b', '1')
    is_ok(code, 2, 'invalid number')
    like_ok(err, re.compile(r'\ba\b'), 'message of the option')
    code, out, err = run(shop, 'search', '-q', 'pyjo', '-s', 'stock')
    is_ok(code, 2, 'not one of the choices')
    code, out, err = run(shop, 'search', '-q', 'pyjo', '-l', '11')
    is_deeply_ok((code, err), (1, 'Invalid arguments:\n/limit: Greater than the maximum 10.\n'), 'invalid argument')
    code, out, err = run(calculator, 'add', '-a', '1', '-b', '2', 'extra')
    is_deeply_ok((code, err), (2, 'Unexpected arguments: extra\n'), 'arguments that are not options')
    code, out, err = run(calculator, 'power')
    is_deeply_ok((code, err), (2, 'Unknown command "power", see python mcp_cli.py --help\n'), 'unknown command')
    code, out, err = run(calculator, '--bogus')
    is_ok(code, 2, 'unknown option before the command')
    code, out, err = run(calculator, '-f', 'xml', 'add')
    is_ok(code, 2, 'unknown format')
    code, out, err = run(Pyjoyment.new(), 'add')
    is_ok(code, 1, 'not a server of MCP')
    like_ok(err, re.compile(r'^/mcp: 404 Not Found$'), 'message of HTTP')

cli.ua.close()

done_testing()
