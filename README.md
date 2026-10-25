[![Home](https://img.shields.io/badge/%F0%9F%8F%A0-Pyjoyment-02a7a0)](https://github.com/dex4er/Pyjoyment)
[![GitHub](https://img.shields.io/github/stars/dex4er/Pyjo-MCP?style=flat&label=GitHub%20%E2%AD%90&logo=github)](https://github.com/dex4er/Pyjo-MCP)
[![Documentation](https://img.shields.io/badge/docs-Read_the_Docs-blue?logo=readthedocs&logoColor=white)](https://pyjoyment.readthedocs.io/projects/pyjo-mcp/en/latest/)
[![License](https://img.shields.io/github/license/dex4er/Pyjo-MCP.svg)](https://github.com/dex4er/Pyjo-MCP/blob/main/LICENSE)
[![Tests](https://github.com/dex4er/Pyjo-MCP/actions/workflows/tests.yaml/badge.svg?branch=main)](https://github.com/dex4er/Pyjo-MCP/actions/workflows/tests.yaml)

# Pyjo-MCP

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/dex4er/Pyjoyment/main/Pyjoyment/resources/public/pyjo/logo-white-4x.png">
    <img src="https://raw.githubusercontent.com/dex4er/Pyjoyment/main/Pyjoyment/resources/public/pyjo/logo-black-4x.png" alt="Pyjoyment" width="322">
  </picture>
</p>

[Model Context Protocol](https://modelcontextprotocol.io) server and client
for [Pyjoyment](https://github.com/dex4er/Pyjoyment), of the revision
2026-07-28 of the specification.

## Installation

From the Git repository, as neither the distribution nor the revival of
Pyjoyment is on PyPI yet; with uv, Pyjoyment comes from its Git repository too:

```sh
uv add git+https://github.com/dex4er/Pyjo-MCP
```

## Usage

A server of MCP is a route of an application of Pyjoyment, whose tools are
functions, with the schemas of their type hints and the descriptions of their
docstrings:

```python
from Pyjo.MCP.Server import Server
from Pyjo.MCP.Tool import Error
from Pyjoyment.Lite import *

server = Server(name='calculator', version='1.0.0')


@server.tool
def divide(a: float, b: float) -> float:
    """Divide the first number by the second one."""
    if b == 0:
        raise Error.new('Division by zero')
    return a / b


# Host and Origin of localhost only, against DNS rebinding
plugin('AllowedHosts')

any('/mcp', server.to_action())

app.start()
```

```sh
uv run python calculator.py daemon -l http://127.0.0.1:3000
```

Its endpoint is `http://127.0.0.1:3000/mcp`, of the transport Streamable HTTP.
The whole calculator is [`examples/calculator.py`](examples/calculator.py).

[`examples/weather.py`](examples/weather.py) is a gateway to the weather of
[Open-Meteo](https://open-meteo.com), which needs no key, with the tools
`find_places`, `current_weather`, `forecast` and `hourly_forecast`, which
request the API with the non-blocking user agent of the application. A client of MCP, as Claude Code,
connects to it over HTTP:

```sh
uv run python examples/weather.py daemon -l http://127.0.0.1:3000
claude mcp add --transport http weather http://127.0.0.1:3000/mcp
```

[`examples/mcp_cli.py`](examples/mcp_cli.py) is a client of the command line
for the tools of any server of MCP: a tool is a command, in kebab-case, and its
arguments are options, with the descriptions and the constraints of its
`inputSchema` in the help of the command. The result is text, with tables of
the lists of objects, or JSON:

```sh
uv run python examples/mcp_cli.py --help
uv run python examples/mcp_cli.py forecast --place Kraków --language pl --days 2
uv run python examples/mcp_cli.py hourly-forecast -p Warsaw -H 6 -f json
```

## Documentation

The tutorial, which makes servers of MCP step by step, and the API of the package
are on [Read the Docs](https://pyjoyment.readthedocs.io/projects/pyjo-mcp/en/latest/).

## Status

A server of the tools of MCP over Streamable HTTP, with `server/discover`,
`tools/list` and `tools/call`. Prompts, resources, the subscriptions, the
streams of SSE, the transport stdio and the client are to come.

## License

The Artistic License 2.0, as Pyjoyment.
