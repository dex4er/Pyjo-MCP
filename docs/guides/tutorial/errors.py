from Pyjo.MCP.Server import Server
from Pyjo.MCP.Tool import Error
from Pyjoyment.Lite import *

import datetime

from typing import Annotated


server = Server(name='flights', version='1.0.0')


@server.tool
def book(date: str, seats: Annotated[int, {'minimum': 1}] = 1) -> str:
    """Book seats of a flight.

    :param date: Date of the flight, in the future, as YYYY-MM-DD.
    :param seats: How many seats.
    """
    try:
        day = datetime.date.fromisoformat(date)
    except ValueError:
        raise Error.new(f'Invalid date {date}: expected YYYY-MM-DD.') from None
    if day <= datetime.date.today():
        raise Error.new(f'Invalid date {date}: the flight has to be in the future.')
    if seats > 9:
        raise RuntimeError('The booking system is down')
    return f'Booked {seats} seats on {date}.'


plugin('AllowedHosts')

any('/mcp', server.to_action())

app.start()
