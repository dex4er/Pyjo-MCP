from Pyjo.MCP.Server import Server
from Pyjoyment.Lite import *

from typing import Literal


server = Server(name='reviewer', version='1.0.0')

STYLE = """\
# Style guide

* Single quotes for strings.
* Lines of 120 characters at most.
"""


@server.resource('docs://style', mime_type='text/markdown')
def style() -> str:
    """The style guide of the project."""
    return STYLE


@server.resource('config://limits', mime_type='application/json')
def limits() -> dict:
    """The limits that the linter checks."""
    return {'line_length': 120}


@server.prompt(title='Code review')
def review(code: str, focus: Literal['bugs', 'style'] = 'bugs') -> list:
    """Review a piece of code against the style guide.

    :param code: The code to review.
    :param focus: What to look for, as bugs or style.
    """
    return [
        {
            'role': 'user',
            'content': {
                'type': 'resource',
                'resource': {'uri': 'docs://style', 'mimeType': 'text/markdown', 'text': STYLE},
            },
        },
        {'role': 'user', 'content': {'type': 'text', 'text': f'Review this code for {focus}:\n{code}'}},
    ]


plugin('AllowedHosts')
hook('before_server_start', server.to_stdio())

any('/mcp', server.to_action())

app.start()
