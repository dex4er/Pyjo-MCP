from Pyjo.MCP.Server import Server
from Pyjoyment.Lite import *

from typing import Annotated, Literal, TypedDict


server = Server(name='shop', version='1.0.0')


class Item(TypedDict):
    """An item of the shop."""

    name: str
    price: Annotated[float, 'Price in EUR']
    stock: int


ITEMS = [
    Item(name='Pyjo mug', price=12.5, stock=3),
    Item(name='Pyjo shirt', price=25.0, stock=0),
    Item(name='Pyjo sticker', price=1.5, stock=100),
]


@server.tool(annotations={'readOnlyHint': True})
def search(
    query: str,
    limit: Annotated[int, {'minimum': 1, 'maximum': 10}] = 5,
    sort: Literal['name', 'price'] = 'name',
    in_stock: bool = False,
) -> list[Item]:
    """Search the items of the shop.

    :param query: Part of the name of an item, in any case.
    :param limit: How many items at most.
    :param sort: Order of the items.
    :param in_stock: Only the items that are in stock.
    """
    found = [item for item in ITEMS if query.lower() in item['name'].lower()]
    if in_stock:
        found = [item for item in found if item['stock']]
    return sorted(found, key=lambda item: item[sort])[:limit]


plugin('AllowedHosts')

any('/mcp', server.to_action())

app.start()
