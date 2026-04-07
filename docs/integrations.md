# Integrations

## MCP

Run:

```bash
session-sift mcp --host 127.0.0.1 --port 9977
```

Then configure your agent runtime to connect to the local MCP server.

## Proxy

Session Sift proxy mode is not OpenAI-only. It normalizes requests for multiple upstream shapes.

### OpenAI-compatible

Run:

```bash
session-sift proxy --provider openai --upstream-url https://api.openai.com
```

### Anthropic-style

Run:

```bash
session-sift proxy --provider anthropic --upstream-url https://api.anthropic.com
```

### Google-compatible

Run:

```bash
session-sift proxy --provider google --upstream-url https://your-endpoint.example.com
```

### OpenClaw

Run:

```bash
session-sift proxy --provider openclaw --upstream-url http://localhost:3000
```

OpenClaw support is surfaced through the same OpenAI-compatible proxy path.
