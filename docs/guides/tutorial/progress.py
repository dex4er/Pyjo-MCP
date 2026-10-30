import Pyjo.Promise

from Pyjo.MCP.Server import Server
from Pyjoyment.Lite import *


server = Server(name='counter', version='1.0.0')


@server.tool(context=True)
async def count(context, to: int) -> int:
    """Count slowly to a number.

    :param to: The number to count to.
    """
    context.notify_log('info', f'Counting to {to}')
    counted = 0
    while counted < to and not context.is_cancelled:
        await Pyjo.Promise.timer(0.1)
        counted += 1
        context.notify_progress(counted, to, f'Counted to {counted}')
    return counted


plugin('AllowedHosts')
hook('before_server_start', server.to_stdio())

any('/mcp', server.to_action())

app.start()
