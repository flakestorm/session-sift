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
session-sift mcp --host 127.0.0.1 --port 9977
```

### `session-sift proxy`

Start the local proxy.

```bash
session-sift proxy --host 127.0.0.1 --port 9978 --provider openai --upstream-url https://api.openai.com
```

### `session-sift status`

Print current engine status.

```bash
session-sift status
```

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