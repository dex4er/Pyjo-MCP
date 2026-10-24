from Pyjo.MCP.Server import Server
from Pyjoyment.Lite import *


server = Server(name='context', version='1.0.0')


@server.tool(context=True)
def whoami(context) -> str:
    """Tell who calls the server."""
    client = context.client_info.get('name', 'an unknown client')
    agent = context.controller.req.headers.user_agent
    return f'{client} {context.protocol_version}, with {agent}'


plugin('AllowedHosts')

any('/mcp', server.to_action())

app.start()
