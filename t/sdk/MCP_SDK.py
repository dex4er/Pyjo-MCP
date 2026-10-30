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


# The client of the MCP SDK, of the dependency group "sdk", calls the server of examples/calculator.py, and the ones of
# the progress, of the prompts and resources, of the resource templates, of the input and of the subscriptions of the
# tutorial, which run in a process of their own, as the client runs the event loop of asyncio in the process of the test,
# over Streamable HTTP and over stdio

if not importlib.util.find_spec('mcp'):
    plan(skip_all='the MCP SDK is required, as of the dependency group "sdk"')

from mcp import Client, StdioServerParameters  # noqa: E402


EXAMPLE = curfile().dirname().dirname().sibling('examples', 'calculator.py').to_str()
PROGRESS = curfile().dirname().dirname().sibling('docs', 'guides', 'tutorial', 'progress.py').to_str()
REVIEW = curfile().dirname().dirname().sibling('docs', 'guides', 'tutorial', 'review.py').to_str()
NOTES = curfile().dirname().dirname().sibling('docs', 'guides', 'tutorial', 'notes.py').to_str()
PROJECT = curfile().dirname().dirname().sibling('docs', 'guides', 'tutorial', 'project.py').to_str()
CONFIRM = curfile().dirname().dirname().sibling('docs', 'guides', 'tutorial', 'confirm.py').to_str()


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


async def library(server):
    # The prompts and the resources
    asyncio.get_running_loop().slow_callback_duration = 5
    async with Client(server) as mcp:
        prompts = (await mcp.list_prompts()).prompts
        prompt = await mcp.get_prompt('review', {'code': 'x = "1"', 'focus': 'style'})
        resources = (await mcp.list_resources()).resources
        style = await mcp.read_resource('docs://style')
        limits = await mcp.read_resource('config://limits')
        try:
            await mcp.read_resource('docs://missing')
            missing = None
        except Exception as e:
            missing = str(e)
        return prompts, prompt, resources, style, limits, missing


async def templates(server):
    # The resource templates, whose URIs the client reads
    asyncio.get_running_loop().slow_callback_duration = 5
    async with Client(server) as mcp:
        listed = (await mcp.list_resource_templates()).resource_templates
        hello = await mcp.read_resource('file:///project/hello.py')
        try:
            await mcp.read_resource('file:///project/../tutorial.rst')
            outside = None
        except Exception as e:
            outside = str(e)
        return listed, hello, outside


def check_templates(listed, hello, outside):
    is_deeply_ok(
        [(template.uri_template, template.name, template.mime_type) for template in listed],
        [('file:///project/{+path}', 'project_file', 'text/x-python')],
        'resources/templates/list',
    )
    is_ok(str(hello.contents[0].uri), 'file:///project/hello.py', 'URI of the resource')
    like_ok(hello.contents[0].text, r'^from Pyjo.MCP.Server import Server', 'resources/read')
    is_ok(outside, 'Resource not found', 'outside of the directory')


async def inputs(server):
    # The input of the user and of the language model, which the callbacks of the client give in the rounds of a request
    asyncio.get_running_loop().slow_callback_duration = 5
    from mcp import types

    asked = []

    async def elicitation(context, params):
        asked.append(params.message)
        return types.ElicitResult(action='accept' if 'todo' in params.message else 'decline')

    async def sampling(context, params):
        asked.append(params.messages[0].content.text)
        return types.CreateMessageResult(
            role='assistant', content=types.TextContent(type='text', text='Groceries.'), model='test'
        )

    async with Client(server, elicitation_callback=elicitation, sampling_callback=sampling) as mcp:
        kept = await mcp.call_tool('delete', {'name': 'notes.txt'})
        deleted = await mcp.call_tool('delete', {'name': 'todo.txt'})
        summary = await mcp.call_tool('summarize', {'name': 'notes.txt'})
    return asked, kept, deleted, summary


def check_inputs(asked, kept, deleted, summary):
    is_deeply_ok(
        asked,
        ['Delete notes.txt?', 'Delete todo.txt?', 'Summarize in a few words:\nBuy milk, eggs and bread.'],
        'input of the user and of the language model',
    )
    is_ok(kept.content[0].text, 'Kept notes.txt', 'declined')
    is_ok(deleted.content[0].text, 'Deleted todo.txt', 'accepted')
    is_ok(summary.content[0].text, 'Groceries.', 'sampled')


async def subscriptions(server):
    # A subscription to the list of the resources and to one of them, which a tool changes, until the client closes it
    asyncio.get_running_loop().slow_callback_duration = 5
    events = []
    async with Client(server) as mcp:
        async with mcp.listen(resources_list_changed=True, resource_subscriptions=['notes://all']) as subscription:
            honored = subscription.honored
            added = await mcp.call_tool('add_note', {'text': 'Buy milk'})
            async for event in subscription:
                events.append(event)
                if len(events) == 2:
                    break
        notes = await mcp.read_resource('notes://all')
        resources = (await mcp.list_resources()).resources
    return honored, added, events, notes, resources


def check_subscriptions(honored, added, events, notes, resources):
    ok(honored.resources_list_changed, 'acknowledged list')
    is_deeply_ok(honored.resource_subscriptions, ['notes://all'], 'acknowledged resources')
    is_ok(added.structured_content, 1, 'tools/call')
    is_deeply_ok(
        [(type(event).__name__, getattr(event, 'uri', None)) for event in events],
        [('ResourcesListChanged', None), ('ResourceUpdated', 'notes://all')],
        'notifications',
    )
    is_ok(notes.contents[0].text, '* Buy milk\n', 'resource read again')
    is_deeply_ok([str(resource.uri) for resource in resources], ['notes://all', 'notes://1'], 'list read again')


def check_library(prompts, prompt, resources, style, limits, missing):
    is_deeply_ok([prompt.name for prompt in prompts], ['review'], 'prompts/list')
    is_deeply_ok(
        [(argument.name, argument.required) for argument in prompts[0].arguments],
        [('code', True), ('focus', False)],
        'arguments',
    )
    is_ok(prompt.messages[0].content.resource.uri, 'docs://style', 'embedded resource')
    is_ok(prompt.messages[1].content.text, 'Review this code for style:\nx = "1"', 'prompts/get')
    is_deeply_ok(
        [(str(resource.uri), resource.mime_type) for resource in resources],
        [('docs://style', 'text/markdown'), ('config://limits', 'application/json')],
        'resources/list',
    )
    like_ok(style.contents[0].text, r'^# Style guide', 'resources/read')
    is_ok(limits.contents[0].text, '{"line_length":120}', 'JSON')
    is_ok(missing, 'Resource not found', 'unknown resource')


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

with subtest('Prompts and resources over Streamable HTTP'):
    with daemon(REVIEW) as url:
        check_library(*asyncio.run(library(url)))

with subtest('Resource templates over Streamable HTTP'):
    with daemon(PROJECT) as url:
        check_templates(*asyncio.run(templates(url)))

with subtest('Input over Streamable HTTP'):
    with daemon(CONFIRM) as url:
        check_inputs(*asyncio.run(inputs(url)))

with subtest('Subscriptions over Streamable HTTP'):
    with daemon(NOTES) as url:
        check_subscriptions(*asyncio.run(subscriptions(url)))

# The client starts the server of the command stdio itself, and ends it when it closes its standard input
with subtest('Client of the MCP SDK over stdio'):
    check(*asyncio.run(session(StdioServerParameters(command=sys.executable, args=[EXAMPLE, 'stdio'], env=env))))

with subtest('Notifications over stdio'):
    check_progress(
        *asyncio.run(progress(StdioServerParameters(command=sys.executable, args=[PROGRESS, 'stdio'], env=env)))
    )

with subtest('Prompts and resources over stdio'):
    check_library(*asyncio.run(library(StdioServerParameters(command=sys.executable, args=[REVIEW, 'stdio'], env=env))))

with subtest('Resource templates over stdio'):
    check_templates(
        *asyncio.run(templates(StdioServerParameters(command=sys.executable, args=[PROJECT, 'stdio'], env=env)))
    )

with subtest('Input over stdio'):
    check_inputs(*asyncio.run(inputs(StdioServerParameters(command=sys.executable, args=[CONFIRM, 'stdio'], env=env))))

with subtest('Subscriptions over stdio'):
    check_subscriptions(
        *asyncio.run(subscriptions(StdioServerParameters(command=sys.executable, args=[NOTES, 'stdio'], env=env)))
    )

done_testing()
