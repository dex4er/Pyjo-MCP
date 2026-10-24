import Pyjoyment.Plugin.AllowedHosts

from Pyjo.MCP.Server import Server
from Pyjoyment.Lite import *

import hmac
import os


server = Server(name='secure', version='1.0.0')


@server.tool
def secret() -> str:
    """A secret, for the clients with the token only."""
    return 'The cake is a lie.'


# A page of the application, which anybody can see
get('/', {'text': 'The MCP endpoint is /mcp.'})

# The hosts of localhost and of the deployment, checked only for the routes under the helper allowed_hosts
plugin('AllowedHosts', hosts=[*Pyjoyment.Plugin.AllowedHosts.HOSTS, 'mcp.example.com'], hook=False)

TOKEN = os.environ.get('MCP_TOKEN', '')


def authorized(c):
    # Host and Origin first, then the bearer token, as an MCP client sends it in Authorization
    if not c.allowed_hosts():
        return False
    sent = c.req.headers.authorization or ''
    if TOKEN and hmac.compare_digest(sent, f'Bearer {TOKEN}'):
        return True
    c.res.headers.header('WWW-Authenticate', 'Bearer')
    c.render(json={'error': 'Unauthorized'}, status=401)
    return False


# The routes after under are its own, so it comes last
under('/mcp', authorized)
any('/', server.to_action())

app.start()
