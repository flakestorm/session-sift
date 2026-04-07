# Integrations

Session Sift is not a transparent interceptor for every AI client. It only works when the client is explicitly configured to either:

1. send model traffic through the local proxy, or
2. register and call the local MCP server

## Compatibility Summary

| Client / Runtime | Proxy | MCP | Notes |
|---|---|---|---|
| OpenAI-compatible clients | Yes | No | Best path when the client exposes a custom `base_url` |
| OpenClaw | Yes | No | Primary proxy target; point clients at Session Sift, then Session Sift at OpenClaw |
| Cursor | Maybe | Yes | Primary MCP target; stdio transport recommended |
| Claude Code | Maybe | Yes | Primary MCP target; stdio transport recommended |
| Windsurf / Roo Code | Maybe | Yes | MCP is the intended path in current OSS docs |
| Codex | Yes | Yes | Primary MCP target; stdio transport recommended |
| GitHub Copilot Chat in VS Code | No | Not verified | Running Session Sift locally does not automatically intercept Copilot traffic |

## MCP

Run:

```bash
session-sift mcp
```

Then configure your agent runtime to connect to the local MCP server and expose the `session_sift_refine` tool.

Use MCP when the runtime is tool-driven and supports custom MCP server registration. Session Sift now defaults to stdio transport for MCP-native clients. This is the recommended path for Claude Code, Codex, Cursor, Windsurf, and Roo Code.

See [mcp-integration.md](mcp-integration.md) for real setup commands.

## Proxy

Session Sift proxy mode is not OpenAI-only. It normalizes requests for multiple upstream shapes.

Use proxy mode only when the client lets you change its upstream API endpoint to the local Session Sift proxy.

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

See [openclaw-integration.md](openclaw-integration.md) for the recommended production wiring and proxy verification steps.

## What Will Not Work Automatically

- Starting `session-sift proxy` does not make GitHub Copilot, Cursor, Claude Code, or any other client use it automatically.
- Starting `session-sift mcp` does not make a client call `session_sift_refine` automatically unless the client is configured for that MCP server.
- If a client does not expose either a custom endpoint path or custom MCP configuration, Session Sift cannot see the traffic.
