from Pyjo.MCP.Server import Server
from Pyjoyment.Lite import *


server = Server(name='notes', version='1.0.0')
server.list_changed = server.subscribe = True
notes: list[str] = []


@server.resource('notes://all', mime_type='text/markdown')
def all_notes() -> str:
    """All the notes, as a list of Markdown."""
    return ''.join(f'* {note}\n' for note in notes)


@server.tool
def add_note(text: str) -> int:
    """Add a note, which is a resource of its own too, and return its number.

    :param text: The text of the note.
    """
    notes.append(text)
    number = len(notes)
    server.resource(f'notes://{number}', lambda: text, name=f'note_{number}', description=f'Note {number}.')
    server.notify_list_changed('resources')
    server.notify_resource_updated('notes://all')
    return number


plugin('AllowedHosts')
hook('before_server_start', server.to_stdio())

any('/mcp', server.to_action())

app.start()
