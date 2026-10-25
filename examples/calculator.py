from Pyjo.MCP.Server import Server
from Pyjo.MCP.Tool import Error
from Pyjoyment.Lite import *


# A server of MCP whose tools are the operations of a calculator
server = Server(name='calculator', version='1.0.0', instructions='Arithmetic of two numbers, without mistakes.')


@server.tool(annotations={'readOnlyHint': True})
def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b


@server.tool(annotations={'readOnlyHint': True})
def subtract(a: float, b: float) -> float:
    """Subtract the second number from the first one."""
    return a - b


@server.tool(annotations={'readOnlyHint': True})
def multiply(a: float, b: float) -> float:
    """Multiply two numbers."""
    return a * b


@server.tool(annotations={'readOnlyHint': True})
def divide(a: float, b: float) -> float:
    """Divide the first number by the second one."""
    if b == 0:
        raise Error.new('Division by zero')
    return a / b


# Host and Origin of localhost only, against DNS rebinding
plugin('AllowedHosts')

any('/mcp', server.to_action())

# The transport stdio too, of the command stdio
hook('before_server_start', server.to_stdio())

app.start()
