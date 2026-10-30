from Pyjo.File import curfile
from Pyjo.Test import *

import asyncio
import contextlib
import importlib.util
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request


# The client of the MCP SDK, of the dependency group "sdk", calls the server of examples/calculator.py, and the one of
# the progress of the tutorial, which run in a process of their own, as the client runs the event loop of asyncio in the
# process of the test, over Streamable HTTP and over stdio

if not importlib.util.find_spec('mcp'):
    plan(skip_all='the MCP SDK is required, as of the dependency group "sdk"')

from mcp import Client, StdioServerParameters  # noqa: E402


EXAMPLE = curfile().dirname().dirname().sibling('examples', 'calculator.py').to_str()
PROGRESS = curfile().dirname().dirname().sibling('docs', 'guides', 'tutorial', 'progress.py').to_str()


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


async def progress(server):
    # The log messages and the progress of a tool, which the client asks for in the _meta of its request
    asyncio.get_running_loop().slow_callback_duration = 5
    logs, steps = [], []

    async def logging(params):
        logs.append((params.level, params.data))

    async def step(progress, total, message):
        steps.append((progress, total, message))

    async with Client(server, logging_callback=logging, log_level='info') as mcp:
        result = await mcp.call_tool('count', {'to': 3}, progress_callback=step)
    return result, logs, steps


def check_progress(result, logs, steps):
    is_ok(result.structured_content, 3, 'result after the notifications')
    is_deeply_ok(logs, [('info', 'Counting to 3')], 'log message')
    is_deeply_ok(steps, [(1, 3, 'Counted to 1'), (2, 3, 'Counted to 2'), (3, 3, 'Counted to 3')], 'progress')


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


env = {**os.environ, 'PYJO_LOG_LEVEL': 'fatal'}
env.pop('PYTHONDEVMODE', None)
env.pop('PYTHONWARNINGS', None)


@contextlib.contextmanager
def daemon(example):
    # The server of the example in a process of its own, and the URL of its endpoint once it listens
    listen = port()
    server = subprocess.Popen(
        [sys.executable, example, 'daemon', '-l', f'http://127.0.0.1:{listen}'], env=env, stdout=subprocess.DEVNULL
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
        yield f'http://127.0.0.1:{listen}/mcp'
    finally:
        server.terminate()
        server.wait(10)


with subtest('Client of the MCP SDK over Streamable HTTP'):
    with daemon(EXAMPLE) as url:
        check(*asyncio.run(session(url)))

with subtest('Notifications over Streamable HTTP'):
    with daemon(PROGRESS) as url:
        check_progress(*asyncio.run(progress(url)))

# The client starts the server of the command stdio itself, and ends it when it closes its standard input
with subtest('Client of the MCP SDK over stdio'):
    check(*asyncio.run(session(StdioServerParameters(command=sys.executable, args=[EXAMPLE, 'stdio'], env=env))))

with subtest('Notifications over stdio'):
    check_progress(
        *asyncio.run(progress(StdioServerParameters(command=sys.executable, args=[PROGRESS, 'stdio'], env=env)))
    )

done_testing()
