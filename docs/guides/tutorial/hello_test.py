import Pyjo.MCP.Test

from Pyjo.File import curfile
from Pyjo.Test import *


t = Pyjo.MCP.Test.new(curfile().sibling('hello.py'))

with subtest('Greeting'):
    t.call_ok('greet', name='Pyjo').status_is(200).text_content_is('Hello, Pyjo!').is_error_is(False)

with subtest('Without a name'):
    t.call_ok('greet').status_is(200).is_error_is(True).text_content_like(r'/name: Missing property')

with subtest('Tools'):
    t.list_tools_ok().status_is(200).tool_is('greet', '/inputSchema/required', ['name'])

done_testing()
