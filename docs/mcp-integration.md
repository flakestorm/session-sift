# MCP Integration Guide

Session Sift's primary integration path for Claude Code, Codex, Cursor-style runtimes, and other tool-driven agents is **MCP over stdio**.

## Why stdio is the primary path

Most real MCP clients start local servers as subprocesses and speak newline-delimited JSON-RPC over stdin/stdout. That is now Session Sift's default MCP transport.

Use this command as the server process:

```bash
session-sift mcp
```

That is the recommended packaged-install command after:

```bash
pip install session-sift
```

Verify the server locally before connecting a client:

```bash
session-sift verify mcp
```

Legacy TCP transport still exists for custom integrations:

```bash
session-sift mcp --transport tcp --host 127.0.0.1 --port 9977
```

## Tools exposed by the MCP server

- `session_sift_refine`: prune and compress a conversation transcript
- `session_sift_status`: inspect the live MCP server process status
- `session_sift_export_dna`: export Project DNA from the running session

## Claude Code

Claude Code supports local stdio MCP servers directly.

Add Session Sift:

```bash
claude mcp add --transport stdio session-sift -- session-sift mcp
```

If `session-sift` is not on your PATH, use Python directly:

```bash
claude mcp add --transport stdio session-sift -- python -m session_sift mcp
```

Project-scoped config example (`.mcp.json`):

```json
{
  "mcpServers": {
    "session-sift": {
      "type": "stdio",
      "command": "session-sift",
      "args": ["mcp"],
      "env": {}
    }
  }
}
```

This repo also ships that example as a checked-in file at [.mcp.json](../.mcp.json).

Fallback for source checkouts or clients that do not inherit a PATH containing `session-sift`:

```json
{
  "mcpServers": {
    "session-sift": {
      "type": "stdio",
      "command": "python",
      "args": ["-m", "session_sift", "mcp"],
      "env": {}
    }
  }
}
```

On Windows, the most reliable fallback is often an absolute interpreter path, for example:

```json
{
  "mcpServers": {
    "session-sift": {
      "type": "stdio",
      "command": "C:/Path/To/Python/python.exe",
      "args": ["-m", "session_sift", "mcp"],
      "env": {}
    }
  }
}
```

Verify inside Claude Code:

```text
/mcp
```

Then ask Claude to use `session_sift_refine` when the conversation gets long or noisy.

## Codex

Codex supports stdio MCP servers in both the CLI and the IDE extension.

Add Session Sift with the CLI:

```bash
codex mcp add session-sift -- session-sift mcp
```

Or in `.codex/config.toml`:

```toml
[mcp_servers.session-sift]
command = "session-sift"
args = ["mcp"]
```

If `session-sift` is not on your PATH:

```toml
[mcp_servers.session-sift]
command = "python"
args = ["-m", "session_sift", "mcp"]
```

This repo also ships that example as a checked-in file at [.codex/config.toml](../.codex/config.toml).

## Cursor

Cursor MCP configuration varies by release, but the local Session Sift server should be registered as a **stdio MCP server** using this command shape:

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

If your Cursor setup uses a project MCP config file such as `.cursor/mcp.json`, place the entry there. If your build exposes MCP configuration in the UI, use the same command and args.

## What success looks like

When the client connects successfully, it should discover these tools from Session Sift:

- `session_sift_refine`
- `session_sift_status`
- `session_sift_export_dna`

The simplest smoke test is to ask the client to call `session_sift_status`.

## Notes

- `session-sift status` in a shell is not the same thing as `session_sift_status` in MCP. The shell command creates a fresh local engine instance. The MCP tool inspects the live MCP server process.
- For Claude Code and Codex, stdio is the recommended path.
- Session Sift does not require proxy mode when MCP is available.