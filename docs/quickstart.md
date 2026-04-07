# Quickstart

## Install

```bash
pip install session-sift
```

## Confirm Install

```bash
session-sift --help
```

If the shell cannot find the `session-sift` command yet, use:

```bash
python -m session_sift --help
```

## Refine A Session

```bash
session-sift refine session.json --output refined.json --report
```

## Proxy

```bash
session-sift proxy --provider openclaw --upstream-url http://localhost:3000
```

## MCP

```bash
session-sift mcp --host 127.0.0.1 --port 9977
```

## Status

```bash
session-sift status
```

## Contributing From Source

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .[dev]
pytest -q
```
