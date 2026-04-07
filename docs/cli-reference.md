# CLI Reference

## Install

```bash
pip install session-sift
```

## Commands

### `session-sift refine`

Refine a saved conversation payload.

```bash
session-sift refine session.json --output refined.json --report
```

### `session-sift mcp`

Start the local MCP server.

```bash
session-sift mcp
```

This starts the standard MCP stdio server and is the recommended path for Claude Code, Codex, and Cursor-style runtimes.

Use this when your runtime supports custom MCP servers and tool calls. Running the MCP server alone does nothing until the client is configured to call `session_sift_refine`.

Recommended packaged-install MCP config:

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

Fallback if PATH resolution fails:

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

Legacy TCP transport is still available for custom integrations:

```bash
session-sift mcp --transport tcp --host 127.0.0.1 --port 9977
```

### `session-sift verify mcp`

Run a local stdio MCP smoke test.

```bash
session-sift verify mcp
```

This verifies that Session Sift can complete the MCP initialize handshake, list tools, and call `session_sift_status` locally.

### `session-sift proxy`

Start the local proxy.

```bash
session-sift proxy --host 127.0.0.1 --port 9978 --provider openai --upstream-url https://api.openai.com
```

Use this when your client exposes a custom upstream API endpoint or `base_url`. Running the proxy alone does nothing until the client is configured to send traffic to `http://127.0.0.1:9978`.

Live proxy verification endpoints:

```bash
curl http://127.0.0.1:9978/healthz
curl http://127.0.0.1:9978/status
```

### `session-sift status`

Print current engine status.

```bash
session-sift status
```

This command reports a fresh local engine instance. It does not inspect a separately running `session-sift mcp` or `session-sift proxy` process.

### `session-sift report`

Render a saved report in console form.

```bash
session-sift report refined.json
```

### `session-sift config show|get|set`

Inspect or update persisted config.

```bash
session-sift config show
session-sift config get pruning_threshold
session-sift config set pruning_threshold 0.20
```

### `session-sift dna export|import`

Export or import Project DNA.

```bash
session-sift dna export --output .session-sift/dna.json
session-sift dna import .session-sift/dna.json
```