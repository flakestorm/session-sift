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

## Choose Your Integration Path

Use one of these, depending on what your client supports:

- `refine`: for saved session payloads on disk
- `proxy`: for clients that expose a custom API endpoint / `base_url`
- `mcp`: for clients that support custom MCP servers and tool calls

## Proxy

```bash
session-sift proxy --provider openclaw --upstream-url http://localhost:3000
```

Only works if your client is configured to send its model traffic to `http://127.0.0.1:9978`.

## MCP

```bash
session-sift mcp
```

This is now the default stdio MCP transport and is the recommended path for Claude Code, Codex, and Cursor-style runtimes.

Only works if your client is configured to register and call the local MCP server.

Verify the stdio MCP handshake locally before wiring a client:

```bash
session-sift verify mcp
```

Recommended MCP config after `pip install session-sift`:

```json
{
	"mcpServers": {
		"session-sift": {
			"command": "session-sift",
			"args": ["mcp"],
			"env": {}
		}
	}
}
```

Fallback if the client cannot resolve `session-sift` on PATH:

```json
{
	"mcpServers": {
		"session-sift": {
			"command": "python",
			"args": ["-m", "session_sift", "mcp"],
			"env": {}
		}
	}
}
```

Legacy TCP transport remains available for custom integrations:

```bash
session-sift mcp --transport tcp --host 127.0.0.1 --port 9977
```

## Status

```bash
session-sift status
```

This shows the status of a newly created local engine instance. It does not inspect a separately running proxy or MCP process.

## Contributing From Source

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .[dev]
pytest -q
```
