# Contributing

Thanks for contributing to Session Sift.

This repository should stay useful as a local-first context management tool. Changes that make the codebase harder to trust, harder to run locally, or more provider-specific than necessary will usually be rejected.

## Development Setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .[dev]
pytest -q
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
pytest -q
```

## Before You Open A PR

- search existing issues and pull requests first
- keep changes focused on one problem
- update docs when behavior or setup changes
- include tests for bug fixes and behavior changes
- avoid mixing refactors with feature changes unless strictly necessary

## Expectations

- keep the deterministic path trustworthy
- do not break protected-message guarantees
- do not add provider-specific hacks without tests
- add tests for behavior changes
- keep local OSS workflows usable without hidden services

## Pull Requests

Please include:

- a short problem statement
- the behavior change
- tests added or updated
- any compatibility note for providers or integrations

## Good First Contributions

- add missing tests around provider normalization and stream handling
- improve docs and runnable examples
- tighten deterministic pruning heuristics without reducing safety
- improve error messages and operator visibility

## Reporting Bugs And Proposing Features

Use the issue templates in GitHub. Before filing, read [docs/issue-guide.md](docs/issue-guide.md) so reports come with enough context to reproduce.
