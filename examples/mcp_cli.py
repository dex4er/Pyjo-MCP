"""
Usage: python mcp_cli.py [OPTIONS] [COMMAND] [OPTIONS]

  python weather.py daemon  # starts a server of MCP at port 3000
  python mcp_cli.py
  python mcp_cli.py forecast --help
  python mcp_cli.py forecast --place Kraków --days 2 --language pl
  python mcp_cli.py hourly-forecast -p Warsaw -H 6 -f json
  python calculator.py daemon -l http://*:3001  # starts another one at port 3001
  python mcp_cli.py -u http://127.0.0.1:3001/mcp add -a 1 -b 2

A command line client of the tools of a server of MCP: a tool is a command, its
name in kebab-case, and its arguments are the options of the command, with the
names of the properties of its inputSchema, a string, an integer, a number, a
flag of a boolean, or JSON for an array or an object. The result is text,
tables of the lists of objects, or the JSON of its structuredContent.

The commands are the tools of the server, so another server has other ones,
which python mcp_cli.py lists.

Options:
  -f, --format <name>   Format of the result, "text" or "json", defaults to
                        "text"
  -h, --help            Show this summary of available options and commands
  -u, --url <url>       URL of the endpoint of MCP, defaults to the value of
                        MCP_URL or "http://127.0.0.1:3000/mcp"
"""

import Pyjo.Exception
import Pyjo.GetOpt
import Pyjo.JSON
import Pyjo.JSON.RPC
import Pyjo.MCP.Client
import Pyjo.UserAgent
import Pyjo.YAML

from Pyjo.Util import tablify

import json
import os
import re
import sys


# The user agent of the requests, blocking, as a command waits for its result
ua = Pyjo.UserAgent.new()

# The options of every command, which the options of the arguments of a tool do not take
FORMATS = ('text', 'json')
RESERVED = {'f', 'h', 'format', 'help'}


def describe(schema, required):
    # The description of an option, with the constraints of the schema of its property
    parts = [schema.get('description', '').rstrip('.')] if schema.get('description') else []
    if 'enum' in schema:
        parts.append('one of ' + ', '.join(Pyjo.JSON.to_json(value) for value in schema['enum']))
    if 'minimum' in schema and 'maximum' in schema:
        parts.append(f'from {schema["minimum"]} to {schema["maximum"]}')
    elif 'minimum' in schema:
        parts.append(f'at least {schema["minimum"]}')
    elif 'maximum' in schema:
        parts.append(f'at most {schema["maximum"]}')
    if required:
        parts.append('required')
    elif schema.get('default') is not None:
        parts.append(f'defaults to {Pyjo.JSON.to_json(schema["default"])}')
    return ', '.join(parts)


def kebab(name):
    return re.sub(r'(?<=[a-z0-9])(?=[A-Z])', '-', name).replace('_', '-').lower()


def kind(schema):
    # The type of a property, without the null of an optional one
    type = schema.get('type')
    if isinstance(type, list):
        type = next((each for each in type if each != 'null'), None)
    return type


def options(definition):
    # The options of a tool, each with the name of its property, its specification, its label and its description
    schema = definition['inputSchema']
    required = set(schema.get('required', []))
    used = set(RESERVED)
    found = []
    for name, property in schema.get('properties', {}).items():
        long = kebab(name)
        if long in used:
            long = f'{long}-arg'
        short = next((letter for letter in (long[0], long[0].upper()) if letter.isalpha() and letter not in used), None)
        used.update((long, short))
        type = kind(property)
        suffix = {'string': '=s', 'integer': '=i', 'number': '=f', 'boolean': '!'}.get(type, '=s')
        names = f'{short}|{long}' if short else long
        label = f'-{short}, --{long}' if short else f'    --{long}'
        if type != 'boolean':
            label += f' <{type if type in ("string", "integer", "number") else "json"}>'
        found.append((name, long, names + suffix, label, describe(property, name in required), property, type))
    return found


def plain(value):
    # A scalar of JSON in a cell of a table or after a key
    if value is None:
        return ''
    if isinstance(value, bool | float | int):
        return Pyjo.JSON.to_json(value)
    return str(value)


def resolve(schema, root):
    # A schema of the outputSchema, through a $ref to its $defs
    while isinstance(schema, dict) and isinstance(ref := schema.get('$ref'), str) and ref.startswith('#/$defs/'):
        schema = root.get('$defs', {}).get(ref.removeprefix('#/$defs/'), {})
    return schema if isinstance(schema, dict) else {}


def text(value, schema, root, indent=''):
    # The text of a value: a table of a list of flat objects, the keys of an object, and YAML of the rest
    if isinstance(value, list) and value and all(isinstance(item, dict) for item in value):
        items = resolve(resolve(schema, root).get('items'), root)
        keys = [key for key in items.get('properties', {}) if any(key in item for item in value)]
        keys += [key for item in value for key in item if key not in keys]
        if not any(isinstance(item.get(key), dict | list) for item in value for key in keys):
            rows = [keys, *[[plain(item.get(key)) for key in keys] for item in value]]
            return ''.join(f'{indent}{line}\n' for line in tablify(rows).splitlines())
    if isinstance(value, dict):
        properties = resolve(schema, root).get('properties', {})
        keys = [key for key in properties if key in value] + [key for key in value if key not in properties]
        scalars = [[f'{key}:', plain(value[key])] for key in keys if not isinstance(value[key], dict | list)]
        output = ''.join(f'{indent}{line}\n' for line in tablify(scalars).splitlines()) if scalars else ''
        for key in keys:
            if isinstance(value[key], dict | list):
                output += f'{indent}{key}:\n' + text(value[key], properties.get(key, {}), root, indent + '  ')
        return output
    if isinstance(value, list):
        return ''.join(f'{indent}{line}\n' for line in Pyjo.YAML.dump(value).splitlines() if line != '---')
    return f'{indent}{plain(value)}\n'


def usage(definition, command):
    lines = [f'Usage: python mcp_cli.py {command} [OPTIONS]', '']
    if definition.get('description'):
        lines += [definition['description'], '']
    lines.append('Options:')
    for _, _, _, label, description, _, _ in options(definition):
        lines.append(f'  {label}   {description}'.rstrip())
    lines.append('  -f, --format <name>   Format of the result, "text" or "json", defaults to "text"')
    lines.append('  -h, --help   Show this summary of available options')
    return Pyjo.GetOpt.format_usage('\n'.join(lines)) + '\n'


def main(args=None):
    args = list(sys.argv[1:] if args is None else args)

    # The options before the command, as an option of a tool may have the name of one of them
    i = 0
    while i < len(args) and args[i].startswith('-') and args[i] != '--':
        i += 2 if args[i] in ('-u', '--url', '-f', '--format') else 1
    getopt = Pyjo.GetOpt.new()
    getopt.option('f|format=s', default='text', choices=FORMATS)
    getopt.option('h|help')
    getopt.option('u|url=s', default=os.environ.get('MCP_URL') or 'http://127.0.0.1:3000/mcp')
    head = args[:i]
    if not (opts := getopt.parse(head)) or head:
        return 2
    command, rest = (args[i], args[i + 1 :]) if i < len(args) else (None, [])
    client = Pyjo.MCP.Client.new(opts.url, ua=ua, name='mcp_cli')
    client.on(
        'invalid_tool',
        lambda client, definition, e: print(f'Tool {definition.get("name")} left out: {e.message}', file=sys.stderr),
    )

    try:
        # The tools by the names of their commands
        tools = {kebab(definition['name']): definition for definition in client.list_tools()['tools']}

        # The commands, with the first sentence of the description of each tool
        if command is None or command == 'help':
            print(Pyjo.GetOpt.format_usage(__doc__.strip()))
            rows = [
                [name, re.split(r'(?<=\.)\s', definition.get('description', ''), maxsplit=1)[0]]
                for name, definition in tools.items()
            ]
            print('\nCommands:')
            print(''.join(f'  {line}\n' for line in tablify(rows).splitlines()), end='')
            return 0

        if command not in tools:
            print(f'Unknown command "{command}", see python mcp_cli.py --help', file=sys.stderr)
            return 2
        definition = tools[command]

        # The options of the arguments of the tool
        found = options(definition)
        getopt = Pyjo.GetOpt.new()
        for _, _, spec, _, _, property, type in found:
            choices = property.get('enum') if type in ('string', 'integer', 'number') else None
            convert = Pyjo.JSON.from_json if type not in ('string', 'integer', 'number', 'boolean') else None
            getopt.option(spec, choices=choices, type=convert)
        getopt.option('f|format=s', default=opts.format, choices=FORMATS)
        getopt.option('h|help')
        if not (tool_opts := getopt.parse(rest)) or rest:
            if rest:
                print(f'Unexpected arguments: {" ".join(rest)}', file=sys.stderr)
            return 2
        if tool_opts.help or opts.help:
            print(usage(definition, command), end='')
            return 0
        arguments = {}
        for name, long, _, _, _, _, _ in found:
            if (value := getattr(tool_opts, long.replace('-', '_'))) is not None:
                arguments[name] = value
        if missing := [
            f'--{long}'
            for name, long, *_ in found
            if name in definition['inputSchema'].get('required', []) and name not in arguments
        ]:
            print(f'Missing {", ".join(missing)}, see python mcp_cli.py {command} --help', file=sys.stderr)
            return 2

        result = client.call_tool(definition['name'], arguments)
    except Pyjo.JSON.RPC.Error as e:
        print(
            f'{e.message} ({e.code})' + (f': {Pyjo.JSON.to_json(e.data)}' if e.data is not None else ''),
            file=sys.stderr,
        )
        return 1
    except Pyjo.Exception.object as e:
        print(e.message.rstrip(), file=sys.stderr)
        return 1

    # The result, or the error of the tool
    if result.get('isError'):
        print(''.join(item.get('text', '') for item in result.get('content', [])), file=sys.stderr)
        return 1
    structured = result.get('structuredContent')
    if tool_opts.format == 'json':
        print(
            json.dumps(
                structured if 'structuredContent' in result else result.get('content', []), indent=2, ensure_ascii=False
            )
        )
    elif isinstance(structured, dict | list) and structured:
        print(text(structured, definition.get('outputSchema', {}), definition.get('outputSchema', {})), end='')
    else:
        for item in result.get('content', []):
            label = ' '.join(part for part in (item.get('type'), item.get('mimeType')) if part)
            print(item['text'] if item.get('type') == 'text' else f'[{label}]')
    return 0


if __name__ == '__main__':
    sys.exit(main())
