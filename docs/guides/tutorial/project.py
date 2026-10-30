import Pyjo.File
import Pyjo.JSON.RPC

from Pyjo.MCP.Server import Server
from Pyjoyment.Lite import *

import os


server = Server(name='project', version='1.0.0')
root = Pyjo.File.curfile().dirname()


def project_paths(value: str, arguments: dict[str, str]) -> list[str]:
    """The paths of the files of the project that start with the value."""
    paths = (str(file.to_rel(root)).replace(os.sep, '/') for file in root.list_tree())
    return sorted(path for path in paths if path.startswith(value))


@server.resource('file:///project/{+path}', mime_type='text/x-python', complete={'path': project_paths})
def project_file(path: str) -> str:
    """A file of the project, by its path in the project."""
    file = root.child(*path.split('/'))
    if not os.path.isfile(file):
        uri = f'file:///project/{path}'
        raise Pyjo.JSON.RPC.Error.new(Pyjo.JSON.RPC.INVALID_PARAMS, 'Resource not found', {'uri': uri})
    return file.slurp('UTF-8')


plugin('AllowedHosts')
hook('before_server_start', server.to_stdio())

any('/mcp', server.to_action())

app.start()
