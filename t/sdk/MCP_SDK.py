from Pyjo.File import curfile
from Pyjo.Test import *

import asyncio
import importlib.util
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request


# The client of the MCP SDK, of the dependency group "sdk", calls the server of examples/calculator.py, which runs in a
# process of its own, as the client runs the event loop of asyncio in the process of the test, over Streamable HTTP and
# over stdio

if not importlib.util.find_spec('mcp'):
    plan(skip_all='the MCP SDK is required, as of the dependency group "sdk"')

from mcp import Client, StdioServerParameters  # noqa: E402


EXAMPLE = curfile().dirname().dirname().sibling('examples', 'calculator.py').to_str()


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


async def session(server):
    # The debug mode of asyncio of the development mode of Python, whose loop logs a callback slower than 0.1 seconds, as
    # PYJO_ASYNCIO_SLOW_CALLBACK does for the loops of Pyjoyment
    asyncio.get_running_loop().slow_callback_duration = 5
    async with Client(server) as mcp:
        tools = (await mcp.list_tools()).tools
        divide = await mcp.call_tool('divide', {'a': 7, 'b': 2})
        zero = await mcp.call_tool('divide', {'a': 1, 'b': 0})
        invalid = await mcp.call_tool('add', {'a': 'x', 'b': 0})
        try:
            await mcp.call_tool('power', {'a': 1, 'b': 2})
            unknown = None
        except Exception as e:
            unknown = str(e)
        return tools, divide, zero, invalid, unknown


def check(tools, divide, zero, invalid, unknown):
    is_deeply_ok([tool.name for tool in tools], ['add', 'subtract', 'multiply', 'divide'], 'tools/list')
    is_deeply_ok(tools[3].input_schema['required'], ['a', 'b'], 'inputSchema')
    is_deeply_ok(tools[3].output_schema, {'type': 'number'}, 'outputSchema')
    ok(not divide.is_error, 'tools/call')
    is_ok(divide.structured_content, 3.5, 'structuredContent')
    ok(zero.is_error, 'error of the tool')
    is_ok(zero.content[0].text, 'Division by zero', 'text of the error')
    ok(invalid.is_error, 'invalid arguments')
    is_ok(unknown, 'Unknown tool: power', 'unknown tool')


listen = port()
env = {**os.environ, 'PYJO_LOG_LEVEL': 'fatal'}
env.pop('PYTHONDEVMODE', None)
env.pop('PYTHONWARNINGS', None)
server = subprocess.Popen(
    [sys.executable, EXAMPLE, 'daemon', '-l', f'http://127.0.0.1:{listen}'], env=env, stdout=subprocess.DEVNULL
)
try:
    deadline = time.monotonic() + 30
    while True:
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{listen}/', timeout=1):
                break
        except urllib.error.HTTPError as e:
            e.close()
            break
        except OSError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.1)

    with subtest('Client of the MCP SDK over Streamable HTTP'):
        check(*asyncio.run(session(f'http://127.0.0.1:{listen}/mcp')))
finally:
    server.terminate()
    server.wait(10)

# The client starts the server of the command stdio itself, and ends it when it closes its standard input
with subtest('Client of the MCP SDK over stdio'):
    check(*asyncio.run(session(StdioServerParameters(command=sys.executable, args=[EXAMPLE, 'stdio'], env=env))))

done_testing()
