from Pyjo.Test import *

import contextlib
import io


def output():
    return contextlib.redirect_stdout(io.StringIO())


with subtest('Synopsis'):
    from Pyjo.MCP.Prompt import Prompt

    def review(code: str, language: str = 'Python') -> str:
        """Review a piece of code.

        :param code: The code to review.
        :param language: The language of the code.
        """
        return f'Review this {language} code:\n{code}'

    prompt = Prompt(review)
    with output() as stdout:
        print(prompt.name, prompt.description, prompt.arguments)
    is_ok(
        stdout.getvalue(),
        "review Review a piece of code. [{'name': 'code', 'description': 'The code to review.', 'required': True},"
        " {'name': 'language', 'description': 'The language of the code.', 'required': False}]\n",
        'prompt',
    )

    # Or import the module, as in Google Python Style Guide

    import Pyjo.MCP.Prompt

    prompt = Pyjo.MCP.Prompt.new(review, name='code_review', title='Code review')
    with output() as stdout:
        prompt.get_p({'code': 'x = 1'}).then(print).wait()
    is_ok(
        stdout.getvalue(),
        "{'messages': [{'role': 'user', 'content': {'type': 'text', 'text': 'Review this Python code:\\nx = 1'}}]}\n",
        'get_p',
    )

with subtest('new'):
    prompt = Pyjo.MCP.Prompt.new(review)
    prompt = Pyjo.MCP.Prompt.new(review, name='code_review', title='Code review')
    is_ok(prompt.title, 'Code review', 'title')
    prompt = Pyjo.MCP.Prompt.new(lambda **args: ..., arguments=[{'name': 'code', 'required': True}])
    is_deeply_ok(prompt.arguments, [{'name': 'code', 'required': True}], 'arguments')
    prompt = Pyjo.MCP.Prompt.new(lambda context, code: ..., context=True)
    ok(prompt.context, 'context')

with subtest('Attributes'):
    prompt = Pyjo.MCP.Prompt.new(review)
    arguments = prompt.arguments
    is_deeply_ok([argument['name'] for argument in arguments], ['code', 'language'], 'arguments')
    cb = prompt.cb
    is_ok(cb, review, 'cb')
    boolean = prompt.context
    is_ok(boolean, False, 'boolean')
    description = prompt.description
    is_ok(description, 'Review a piece of code.', 'description')
    name = prompt.name
    is_ok(name, 'review', 'name')
    title = prompt.title
    is_ok(title, None, 'title')

with subtest('__json__'):
    definition = prompt.__json__()
    is_deeply_ok(list(definition), ['name', 'description', 'arguments'], 'definition')

with subtest('get_p'):
    results = []
    promise = prompt.get_p({'code': 'x = 1'})
    promise.then(results.append).wait()
    promise = prompt.get_p({'code': 'x = 1'}, None)
    promise.then(results.append).wait()
    is_deeply_ok(results[0], results[1], 'promise')

    with output() as stdout:
        prompt.get_p({'code': 'x = 1'}).then(print).wait()
    is_ok(
        stdout.getvalue(),
        "{'messages': [{'role': 'user', 'content': {'type': 'text', 'text': 'Review this Python code:\\nx = 1'}}]}\n",
        'printed',
    )

with subtest('result'):
    result = prompt.result('Review this code')
    is_deeply_ok(result, Pyjo.MCP.Prompt.text_result('Review this code'), 'text')
    result = prompt.result([{'role': 'assistant', 'content': {'type': 'text', 'text': 'Done'}}])
    is_ok(result['messages'][0]['role'], 'assistant', 'messages')

with subtest('text_result'):
    result = Pyjo.MCP.Prompt.text_result('Review this code')
    is_deeply_ok(
        result, {'messages': [{'role': 'user', 'content': {'type': 'text', 'text': 'Review this code'}}]}, 'result'
    )
    result = Pyjo.MCP.Prompt.text_result('Here is the review', role='assistant')
    is_ok(result['messages'][0]['role'], 'assistant', 'role')

done_testing()
