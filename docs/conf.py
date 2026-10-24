# Sphinx configuration: https://www.sphinx-doc.org/en/master/usage/configuration.html

import Pyjo.MCP

import functools
import importlib.util
import inspect
import os
import re
import subprocess
import sys
import tomllib


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# The module is imported from the environment of uv sync, where the project is installed in editable mode, with
# Pyjoyment, which it imports
with open(os.path.join(ROOT, 'pyproject.toml'), 'rb') as f:
    PROJECT = tomllib.load(f)['project']

project = PROJECT['name']
author = ', '.join(a['name'] for a in PROJECT['authors'])
copyright = f'2026, {author}'
version = release = Pyjo.MCP.__version__

extensions = ['sphinx.ext.autodoc', 'sphinx.ext.intersphinx', 'sphinx.ext.linkcode']

# The modules of Pyjoyment, as Pyjo.UserAgent, are links to its documentation
intersphinx_mapping = {
    'pyjoyment': ('https://pyjoyment.readthedocs.io/en/latest/', None),
}

# The commit that the links to the source point to: the one that Read the Docs builds, or the one of the checkout
COMMIT = (
    os.environ.get('READTHEDOCS_GIT_COMMIT_HASH')
    or subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    or 'main'
)

SOURCE = f'https://github.com/dex4er/Pyjo-MCP/blob/{COMMIT}'


# The link [source] of a class, a function or a method goes to the lines of its source on GitHub; an object of
# Pyjoyment, as a method that the class inherits, has none, as its source is not in this repository
def linkcode_resolve(domain, info):
    if domain != 'py' or not info['module']:
        return None
    obj = sys.modules.get(info['module'])
    for part in info['fullname'].split('.'):
        obj = getattr(obj, part, None)
    if isinstance(obj, property):
        obj = obj.fget
    elif isinstance(obj, functools.cached_property):
        obj = obj.func
    try:
        obj = inspect.unwrap(obj)
        path = inspect.getsourcefile(obj)
        lines, start = inspect.getsourcelines(obj)
    except (TypeError, OSError, ValueError):
        return None
    if not path or not os.path.abspath(path).startswith(ROOT + os.sep):
        return None
    file = os.path.relpath(path, ROOT).replace(os.sep, '/')
    return f'{SOURCE}/{file}#L{start}-L{start + len(lines) - 1}'


# A class under a second name, as `object`, or a method of the class as a function of the module, as `new`, is an alias
# that is not documented twice: the class documents it under its own name.
def skip_alias(app, what, name, obj, skip, options):
    if what == 'module' and (inspect.ismethod(obj) or isinstance(obj, type) and obj.__name__ != name):
        return True
    return None


# The link "Page source" goes to the file on GitHub: the module of a page of its API, as the page itself is mostly the
# directive that documents it, or the page itself, rendered, where the theme links to its text in _sources
def source_link(app, pagename, templatename, context, doctree):
    if not context.get('sourcename'):
        return
    path = app.env.doc2path(pagename)
    automodule = re.search(r'^\.\. automodule:: (\S+)', path.read_text('UTF-8'), re.M)
    if automodule:
        path = importlib.util.find_spec(automodule.group(1)).origin
    url = f'{SOURCE}/{os.path.relpath(path, ROOT).replace(os.sep, "/")}'
    pathto, sources = context['pathto'], '_sources/' + context['sourcename']
    context['pathto'] = lambda uri, *args, **kwargs: url if uri == sources else pathto(uri, *args, **kwargs)


def setup(app):
    app.connect('autodoc-skip-member', skip_alias)
    app.connect('html-page-context', source_link)


# The table of contents lists the page, not the classes and functions that autodoc documents on it.
toc_object_entries = False

exclude_patterns = ['_build']

html_theme = 'alabaster'
html_theme_options = {
    'github_user': 'dex4er',
    'github_repo': 'Pyjo-MCP',
    'show_powered_by': False,
    # The way back to the documentation of Pyjoyment, whose project this one is a subproject of on Read the Docs
    'extra_nav_links': {
        'Pyjoyment': 'https://pyjoyment.readthedocs.io/en/latest/',
        'Distributions': 'https://pyjoyment.readthedocs.io/en/latest/distributions.html',
    },
    # The sans-serif font of the system, where Alabaster has Georgia, as in Pyjoyment
    'font_family': "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
    'head_font_family': "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
}
