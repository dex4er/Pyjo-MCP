import Pyjo.JSON.RPC
import Pyjo.MCP.Prompt
import Pyjo.Promise

from Pyjo.Test import *

import enum
import re

from typing import Literal


# A prompt of a server of MCP, of a function


def get(prompt, arguments, context=None):
    results = []
    prompt.get_p(arguments, context).then(results.append, lambda e: results.append(e)).wait()
    return results[0]


with subtest('Function'):

    def review(code: str, language: str = 'Python') -> str:
        """Review a piece of code.

        More about the review.

        :param code: The code to review.
        :param language: The language of the code.
        """
        return f'Review this {language} code:\n{code}'

    prompt = Pyjo.MCP.Prompt.new(review)
    is_ok(prompt.name, 'review', 'name of the function')
    is_ok(prompt.title, None, 'no title')
    is_ok(prompt.description, 'Review a piece of code.', 'first paragraph of the docstring')
    is_deeply_ok(
        prompt.arguments,
        [
            {'name': 'code', 'description': 'The code to review.', 'required': True},
            {'name': 'language', 'description': 'The language of the code.', 'required': False},
        ],
        'arguments of the parameters',
    )
    is_deeply_ok(
        prompt.__json__(),
        {'name': 'review', 'description': 'Review a piece of code.', 'arguments': prompt.arguments},
        'definition',
    )
    is_deeply_ok(
        get(prompt, {'code': 'x = 1'}),
        {'messages': [{'role': 'user', 'content': {'type': 'text', 'text': 'Review this Python code:\nx = 1'}}]},
        'one message of the user',
    )
    is_ok(
        get(prompt, {'code': 'x = 1', 'language': 'Perl'})['messages'][0]['content']['text'],
        'Review this Perl code:\nx = 1',
        'optional argument',
    )

with subtest('Options'):

    def explain(topic):
        return f'Explain {topic}'

    prompt = Pyjo.MCP.Prompt.new(explain, name='teach', title='Teaching', description='Explain a topic.')
    is_deeply_ok(
        prompt.__json__(),
        {
            'name': 'teach',
            'title': 'Teaching',
            'description': 'Explain a topic.',
            'arguments': [{'name': 'topic', 'required': True}],
        },
        'definition',
    )
    arguments = [{'name': 'topic', 'description': 'What to explain.', 'required': False}]
    prompt = Pyjo.MCP.Prompt.new(lambda **args: f'Explain {args.get("topic", "it")}', name='given', arguments=arguments)
    is_deeply_ok(prompt.arguments, arguments, 'arguments of its own')
    is_ok(prompt.description, '', 'no description')
    is_ok(get(prompt, {})['messages'][0]['content']['text'], 'Explain it', 'no arguments')

    def nothing():
        pass

    is_deeply_ok(Pyjo.MCP.Prompt.new(nothing).arguments, [], 'no arguments of a function without parameters')

with subtest('Completions'):

    class Focus(enum.Enum):
        BUGS = 'bugs'
        STYLE = 'style'

    def review(code: str, language: Literal['Perl', 'Python'] = 'Python', focus: Focus = Focus.BUGS) -> str:
        return code

    prompt = Pyjo.MCP.Prompt.new(review)
    is_deeply_ok(prompt.complete, {'language': ['Perl', 'Python'], 'focus': ['bugs', 'style']}, 'Literal and Enum')
    is_deeply_ok(prompt.__json__()['arguments'][1], {'name': 'language', 'required': False}, 'not in the definition')

    def completer(value, arguments):
        return ['x']

    prompt = Pyjo.MCP.Prompt.new(review, complete={'language': ['PHP'], 'code': completer})
    is_deeply_ok(
        prompt.complete, {'language': ['PHP'], 'focus': ['bugs', 'style'], 'code': completer}, 'over the type hints'
    )
    prompt = Pyjo.MCP.Prompt.new(lambda **args: '', arguments=[{'name': 'code'}], complete={'code': ['x']})
    is_deeply_ok(prompt.complete, {'code': ['x']}, 'arguments of their own')
    is_deeply_ok(Pyjo.MCP.Prompt.new(lambda code: code).complete, {}, 'none')

with subtest('Context'):

    def whoami(context, greeting: str) -> str:
        return f'{greeting} {context}'

    prompt = Pyjo.MCP.Prompt.new(whoami, context=True)
    is_deeply_ok([argument['name'] for argument in prompt.arguments], ['greeting'], 'context is not an argument')
    is_ok(get(prompt, {'greeting': 'Hello'}, 'context')['messages'][0]['content']['text'], 'Hello context', 'first')

with subtest('Results'):
    messages = [
        {'role': 'user', 'content': {'type': 'text', 'text': 'Hello'}},
        {'role': 'assistant', 'content': {'type': 'text', 'text': 'Hi'}},
    ]
    prompt = Pyjo.MCP.Prompt.new(lambda: messages, name='list')
    is_deeply_ok(get(prompt, {}), {'messages': messages}, 'messages')
    result = {'description': 'A greeting', 'messages': messages}
    prompt = Pyjo.MCP.Prompt.new(lambda: result, name='dict')
    is_deeply_ok(get(prompt, {}), result, 'result as it is')
    prompt = Pyjo.MCP.Prompt.new(lambda: None, name='none')
    is_deeply_ok(get(prompt, {}), Pyjo.MCP.Prompt.text_result(''), 'None')
    prompt = Pyjo.MCP.Prompt.new(lambda: 42, name='number')
    is_deeply_ok(get(prompt, {}), Pyjo.MCP.Prompt.text_result('42'), 'string of a value')
    is_deeply_ok(
        Pyjo.MCP.Prompt.text_result('Hello'),
        {'messages': [{'role': 'user', 'content': {'type': 'text', 'text': 'Hello'}}]},
        'text_result',
    )
    is_deeply_ok(
        Pyjo.MCP.Prompt.text_result('Hi', role='assistant'),
        {'messages': [{'role': 'assistant', 'content': {'type': 'text', 'text': 'Hi'}}]},
        'text_result of the assistant',
    )

with subtest('Promises and coroutines'):

    def later(text: str) -> str:
        return Pyjo.Promise.timer(0.01, text)

    is_deeply_ok(get(Pyjo.MCP.Prompt.new(later), {'text': 'Hi'}), Pyjo.MCP.Prompt.text_result('Hi'), 'promise')

    async def twice(text: str) -> str:
        await Pyjo.Promise.timer(0.01)
        return text * 2

    is_deeply_ok(get(Pyjo.MCP.Prompt.new(twice), {'text': 'Hi'}), Pyjo.MCP.Prompt.text_result('HiHi'), 'coroutine')

    async def broken() -> str:
        raise ValueError('Secret')

    isa_ok(get(Pyjo.MCP.Prompt.new(broken), {}), ValueError, 'exception of a coroutine rejects')

with subtest('Errors'):

    def explain(topic: str) -> str:
        return f'Explain {topic}'

    prompt = Pyjo.MCP.Prompt.new(explain)
    error = get(prompt, {})
    isa_ok(error, Pyjo.JSON.RPC.Error, 'missing argument')
    is_ok(error.code, Pyjo.JSON.RPC.INVALID_PARAMS, 'invalid params')
    is_ok(error.message, 'Missing required argument: topic', 'message')
    error = get(prompt, {'topic': 'MCP', 'level': 'expert'})
    isa_ok(error, Pyjo.JSON.RPC.Error, 'argument that the function does not take')
    is_ok(error.code, Pyjo.JSON.RPC.INVALID_PARAMS, 'invalid params')
    like_ok(error.message, re.compile(r"^Invalid arguments: got an unexpected keyword argument 'level'"), 'message')

    def broken():
        raise ValueError('Secret')

    isa_ok(get(Pyjo.MCP.Prompt.new(broken), {}), ValueError, 'exception of a function rejects')

with subtest('Python constructor'):
    from Pyjo.MCP.Prompt import Prompt

    prompt = Prompt(lambda: None, name='python')
    isa_ok(prompt, Pyjo.MCP.Prompt.object, 'prompt')

done_testing()
