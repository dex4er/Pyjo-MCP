from Pyjo.MCP.Server import Server
from Pyjo.MCP.Tool import Error
from Pyjoyment.Lite import *


server = Server(name='files', version='1.0.0')
files = {'notes.txt': 'Buy milk, eggs and bread.', 'todo.txt': 'Write the tutorial.'}


@server.tool(context=True)
def delete(context, name: str) -> str:
    """Delete a file, once the user confirms it.

    :param name: The name of the file.
    """
    if name not in files:
        raise Error(f'No such file: {name}')
    if context.elicit('confirm', f'Delete {name}?')['action'] != 'accept':
        return f'Kept {name}'
    del files[name]
    return f'Deleted {name}'


@server.tool(context=True)
def summarize(context, name: str) -> str:
    """Summarize a file with the language model of the client.

    :param name: The name of the file.
    """
    if name not in files:
        raise Error(f'No such file: {name}')
    result = context.sample('summary', f'Summarize in a few words:\n{files[name]}', 50)
    return result['content']['text']


app.secrets = ['s3cret']
plugin('AllowedHosts')
hook('before_server_start', server.to_stdio())

any('/mcp', server.to_action())

app.start()
