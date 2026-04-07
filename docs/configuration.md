# Configuration

## Environment Variables

| Variable | Purpose | Default |
|---|---|---|
| `SESSION_SIFT_REGISTRY_PATH` | SQLite registry path | `.session-sift/registry.db` |
| `SESSION_SIFT_DNA_PATH` | Project DNA path | `.session-sift/dna.json` |
| `SESSION_SIFT_PROXY_HOST` | Proxy bind host | `127.0.0.1` |
| `SESSION_SIFT_PROXY_PORT` | Proxy bind port | `9978` |
| `SESSION_SIFT_MCP_HOST` | MCP bind host | `127.0.0.1` |
| `SESSION_SIFT_MCP_PORT` | MCP bind port | `9977` |
| `SESSION_SIFT_UPSTREAM_PROVIDER` | Upstream provider adapter | `openai` |
| `SESSION_SIFT_UPSTREAM_URL` | Upstream base URL | `https://api.openai.com` |

Persistent local config can also be written to `.session-sift/config.json` with:

```bash
session-sift config set decay_lambda 0.08
session-sift config set pruning_threshold 0.20
```

Pass 3 runtime configuration includes:

- `pass3_model`
- `pass3_provider`
- `pass3_base_url`
- `pass3_api_key_env`
- `pass3_timeout_secs`
- `pass3_target_ratio`

## Provider Values

Supported `--provider` values:

- `openai`
- `openai-compatible`
- `openclaw`
- `anthropic`
- `google`

The proxy is multi-provider. The default examples use OpenAI only because that is a common OpenAI-compatible shape, not because the OSS core is limited to OpenAI.
