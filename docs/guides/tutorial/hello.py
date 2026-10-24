from Pyjo.MCP.Server import Server
from Pyjoyment.Lite import *


server = Server(name='hello', version='1.0.0')


@server.tool
def greet(name: str) -> str:
    """Greet somebody by name.

    :param name: Name of the person to greet.
    """
    return f'Hello, {name}!'


# Host and Origin of localhost only, against DNS rebinding
plugin('AllowedHosts')

any('/mcp', server.to_action())

app.start()
