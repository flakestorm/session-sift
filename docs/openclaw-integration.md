# OpenClaw Integration Guide

OpenClaw is the primary proxy integration target for Session Sift.

## Why OpenClaw is a strong fit

OpenClaw already acts as a gateway in front of one or more LLM backends. Session Sift fits naturally in front of it:

```text
Agent / Client -> Session Sift proxy -> OpenClaw -> selected LLM
```

Session Sift does not need to know which model OpenClaw chooses downstream as long as OpenClaw is speaking the OpenAI-style request family upstream of Session Sift.

## Start Session Sift in front of OpenClaw

```bash
session-sift proxy --host 127.0.0.1 --port 9978 --provider openclaw --upstream-url http://localhost:3000
```

Then point your agent or client to:

```text
http://127.0.0.1:9978
```

instead of pointing it directly at OpenClaw.

## What the proxy forwards

Session Sift accepts OpenAI-style chat payloads at:

```text
POST /v1/chat/completions
```

It prunes the `messages` array, then forwards the normalized request to OpenClaw.

## Quick verification

Check the proxy health endpoint:

```bash
curl http://127.0.0.1:9978/healthz
```

Expected shape:

```json
{
  "status": "ok",
  "service": "session-sift-proxy",
  "upstream_provider": "openclaw",
  "upstream_url": "http://localhost:3000"
}
```

Check live proxy status after requests flow through it:

```bash
curl http://127.0.0.1:9978/status
```

Expected fields include:

- `turn_count`
- `total_savings_tokens`
- `proxy.requests_handled`
- `proxy.last_provider`
- `proxy.last_savings_pct`
- `last_report`

## Example request path

If your client supports a custom OpenAI-compatible `base_url`, configure it to use Session Sift:

```text
base_url = http://127.0.0.1:9978
```

The resulting path is:

```text
client -> http://127.0.0.1:9978/v1/chat/completions -> OpenClaw -> model
```

## What this does not do

- It does not automatically intercept closed clients that do not let you override their upstream endpoint.
- It does not inspect the downstream model chosen by OpenClaw.
- It does not require OpenClaw to use a specific model vendor.

## Production recommendation

If Session Sift is positioned around two primary propositions, they should be:

1. MCP for tool-driven coding agents
2. OpenClaw proxying for cost-sensitive OpenAI-style gateway deployments