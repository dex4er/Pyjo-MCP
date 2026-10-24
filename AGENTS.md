# Agent Guide: Pyjo-MCP

## Overview

`Pyjo.MCP` is a server and a client of the Model Context Protocol made with
Pyjoyment, without the MCP SDK, in a distribution of its own, as the protocol
changes faster than the framework. It follows the revision 2026-07-28 of the
specification only, whose core is stateless. The conventions are those of
Pyjoyment: read its `AGENTS.md` in the checkout next to this one,
`../Pyjoyment/AGENTS.md`. The plan, and what goes to the core of Pyjoyment
first, is in the issue of Pyjoyment about MCP.

The reference is the distribution `MCP` of CPAN, built on Mojolicious, under
the MIT license.

## Development

The distribution depends on Pyjoyment of its Git repository, as the revival
of Pyjoyment is not on PyPI yet (`[tool.uv.sources]` of `pyproject.toml`). A
path to the checkout next to this one cannot be the source: uv applies the
sources of a dependency of Git, so whoever installs the distribution from Git
would get a subdirectory of this repository that does not exist. The tests lay
the checkout next to this one over it with `--with-editable`, so that they
test what is there:

```sh
mise exec -- uv sync
mise exec -- uv run --with-editable ../Pyjoyment python -m Pyjo.Prove -l -r t
```

Perl's `prove` runs them too, with `.proverc`, under `uv run`, whose `python`
is the one of the environment, where Pyjoyment and the distribution are
installed, so that it needs no `PYTHONPATH`, unlike in Pyjoyment:

```sh
mise exec -- uv run --with-editable ../Pyjoyment prove -r t
```

The package is in the namespace `Pyjo` of Pyjoyment, which `extend_path` keeps
open, so the tests of Pyjoyment run with the distribution installed as well:

```sh
cd ../Pyjoyment
mise exec -- uv run --project ../Pyjo-MCP --with-editable . python -m Pyjo.Prove -l -j 4 -r t
```

Trunk checks the files with the linters of Pyjoyment, from `.trunk/trunk.yaml`:

```sh
trunk check --all
```

actionlint is the one of the maintained fork kjanat/actionlint, whose releases
continue those of rhysd/actionlint after 1.7.12, as in Pyjoyment: `downloads`
in `.trunk/trunk.yaml` replaces the URLs of the plugin with those of the fork,
whose files have the same names.

Its pyright needs the environment of `uv sync`, `.venv`, which `tool.pyright` of
`pyproject.toml` names, as the package imports Pyjoyment; Trunk Check of CI
runs `uv sync` first. The tests and `docs/conf.py` are not checked by pyright:
for them it takes the regular package `Pyjo` of Pyjoyment, which hides
`Pyjo.MCP` of the checkout.

The wheel has only the package `Pyjo.MCP` (`only-include` of hatchling), not
the `__init__.py` of `Pyjo`, which is the one of Pyjoyment; the workflow Build
checks it.

The documentation is on Read the Docs, a subproject of the one of Pyjoyment:
the docstrings of the package, which autodoc imports, as in Pyjoyment. Read the
Docs installs it with `uv sync` of `uv.lock` and the group `docs`, not with pip
and a `docs/requirements.txt` as Pyjoyment does: pip does not read
`[tool.uv.sources]`, so it would take Pyjoyment from PyPI. The links to the
modules of Pyjoyment come from intersphinx. The workflow Docs builds it with
`-W`, as Read the Docs does, with the Pyjoyment of `uv.lock`:

```sh
mise exec -- uv run --group docs --with-editable ../Pyjoyment sphinx-build -W --keep-going -b html docs docs/_build/html
```

`t/docs/MCP.py` runs the synopsis of the package, as `t/docs` of Pyjoyment
does.
