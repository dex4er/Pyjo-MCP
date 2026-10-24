from Pyjo.MCP.Server import Server
from Pyjo.MCP.Tool import Error
from Pyjoyment.Lite import *


server = Server(name='titles', version='1.0.0')


@server.tool(annotations={'readOnlyHint': True, 'openWorldHint': True})
async def title(url: str) -> str:
    """The title of a web page.

    :param url: URL of the page.
    """
    # Non-blocking, so the server answers other requests while the page loads
    tx = await app.ua.get_p(url)
    if (res := tx.result).is_error:
        raise Error.new(f'The page answered {res.code} {res.message}')
    if (element := res.dom().at('title')) is None:
        raise Error.new('The page has no title')
    return element.text


plugin('AllowedHosts')

any('/mcp', server.to_action())

app.start()
