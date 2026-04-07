# Session Sift

![Python](https://img.shields.io/badge/python-3.11%2B-3776AB)
![Tests](https://img.shields.io/badge/tests-90%20passing-2ea043)
![License](https://img.shields.io/badge/license-Apache%202.0-2ea043)
![PyPI Version](https://img.shields.io/pypi/v/session-sift)
![Savings](https://img.shields.io/badge/avg%20savings-38%25--82%25-brightgreen)

**Context management middleware for AI agents — strips transcript rot before it reaches the model.**

[Quickstart](docs/quickstart.md) · [MCP Guide](docs/mcp-integration.md) · [OpenClaw Guide](docs/openclaw-integration.md) · [Examples](docs/examples.md) · [Integrations](docs/integrations.md) · [CLI Reference](docs/cli-reference.md) · [Configuration](docs/configuration.md) · [Proxy OpenAPI](docs/openapi-proxy.yaml) · [Benchmarks](docs/performance-baseline.md) · [Contributing](CONTRIBUTING.md)

---

## The Problem Nobody Talks About

You open a Claude Code or Cursor session. Start coding. 30 turns later, things feel slow. The model starts losing the thread. It suggests fixes you already applied. It repeats itself. It hallucinates about files it read 20 turns ago.

It is not the model getting dumber. **It is your context window filling up with garbage.**

A typical 100-turn coding session accumulates:

| Junk Category | Avg % of Tokens |
|---|---|
| Resolved stack traces (already fixed) | ~18% |
| Intermediate reasoning that was superseded | ~12% |
| Redundant file trees printed with minor deltas | ~9% |
| Tool call echoes / JSON scaffolding wrapping tiny payloads | ~8% |
| Acknowledgments, confirmations, conversational filler | ~7% |

**That is ~54% of your context window occupied by content the model no longer needs.** At frontier model pricing (claude-sonnet-4.6, gpt-5.4, gemini-3.6-flash), this translates to $0.40–$4.00 in wasted spend per long session, per day, per developer.

Session Sift solves this. It intercepts the context, cuts the rot, and forwards a leaner payload — in under 15ms on deterministic passes.

---

## What Session Sift Actually Does

Session Sift is a **three-pass pruning pipeline** that runs between your agent and the upstream model API. It is not a summarizer, not a RAG system, not a memory database. It is a local, deterministic-first context optimizer.

### Pass 1 — Structural Pruning (deterministic, <20ms)

Regex-driven pattern matching collapses known high-volume artifacts:

- ASCII file trees (`├── src/components/...`) → `[SESSION SIFT: file tree collapsed, 47 nodes]`
- Python/Node/Java stack traces → `[SESSION SIFT: 12-frame traceback: AttributeError: 'NoneType'...]`
- Large JSON response bodies (>500 chars) → `[SESSION SIFT: JSON dict collapsed, 18 top-level keys]`
- Code fences over 40 lines → collapsed with line count preserved
- npm/pip install output→ collapsed
- Git diff headers → collapsed, only `+/-` lines kept
- Duplicate content across turns → deduplicated with pointer reference
- Tool call scaffolding wrappers → inner content extracted, wrapper stripped

Everything with a `STRICT`, `TODO`, or `FIXME` annotation is **never touched**. System messages are **never touched**. The last N turns (configurable recency window) are **never touched**.

### Pass 2 — Temporal Pruning (SQLite-backed, deterministic)

Pass 2 tracks file writes via tool calls. When an agent writes to `src/utils.py`, every prior error message referencing `src/utils.py` is **tombstoned** — because the error is resolved. No semantic understanding required. Just event correlation.

The registry is a local SQLite database at `.session-sift/registry.db`. It survives across sessions.

### Pass 3 — Semantic Compression (optional, LLM-assisted)

Only fires when the context after Passes 1+2 still exceeds 70% of your max window. Uses `claude-haiku-3-5` or `gpt-4o-mini` to batch-compress low-signal messages (scored by a fluff detector) down to ~30% of their original size. Falls back silently if no API key is present or if the call times out (5s hard limit).

### RetentionWeight — the math behind what stays

Every message gets a retention score: `W = S(m) · e^(−λ · age) · R(m) · P(m)`

- `S(m)`: structural importance (code definitions, file paths, config values raise it; fluff and duplicates lower it)
- `e^(−λ · age)`: exponential decay — an old unimportant message naturally drifts below the pruning threshold
- `R(m)`: recency boost — last 5 turns always get a 3× multiplier
- `P(m)`: protection override — annotated messages jump to 10× and are never pruned

Messages below the threshold (default `θ = 0.15`) become Pass 3 candidates.

---

## Sample Output

### CLI — `session-sift refine session.json --report`

```
┌─ SESSION SIFT SAVINGS REPORT ─ Turn 1 ────────────────────────
│  Original: 12,440 tokens -> Refined: 2,229 tokens
│  Saved:    10,211 tokens (82.1%)
│  Pass 1 (Structural): 610
│  Pass 2 (Temporal):   0
│  Pass 3 (Semantic):   0
│  Cost saved: ~$0.0306 USD
│  Latency: 0.4ms
└──────────────────────────────────────────────────────────────
```

A heavy structural fixture (duplicate file trees, collapsed traces) — 82% savings in under 1ms.

### CLI — resolved-error fixture

```
┌─ SESSION SIFT SAVINGS REPORT ─ Turn 1 ────────────────────────
│  Original: 3,906 tokens -> Refined: 3,006 tokens
│  Saved:    900 tokens (23.0%)
│  Pass 1 (Structural): 34
│  Pass 2 (Temporal):   27
│  Pass 3 (Semantic):   0
│  Cost saved: ~$0.0027 USD
│  Latency: 50.6ms
└──────────────────────────────────────────────────────────────
```

Mixed session with a resolved error: Pass 2 tombstoned error messages because the file was written to after the error turn.

### What the transcript looks like before and after

**Before (sent to model):**
```
Traceback (most recent call last):
  File "/app/utils.py", line 84, in parse_config
    return json.loads(raw)
  File "/usr/lib/python3.11/json/__init__.py", line 346, in loads
    return _default_decoder.decode(s)
  File "/usr/lib/python3.11/json/decoder.py", line 337, in decode
    ...
json.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```

**After Pass 1:**
```
[SESSION SIFT: 4-frame traceback: json.JSONDecodeError: Expecting value: line 1 column 1 (char 0)]
```

**After Pass 2 (if utils.py was written to later):**
```
[SESSION SIFT: tombstoned — resolved error for utils.py at turn 14]
```

### Proxy mode — what the proxy header looks like

Each proxied response comes back with:
```
X-Session-Sift-Savings: 8241
```

Your agent sees a normal response. The upstream model received a smaller, cleaner payload.

### Python SDK

```python
import asyncio
from session_sift import SessionSiftSDK

sdk = SessionSiftSDK()

async def run():
    messages = [
        {"role": "user", "content": "Fix the TypeError in utils.py"},
        # ... 40 more turns of session history
    ]
    refined, report = await sdk.refine(messages)
    print(report.to_console())
    print(f"Sent {report.refined_tokens:,} tokens instead of {report.original_tokens:,}")

asyncio.run(run())
```

---

## Quick Start

```bash
pip install session-sift
```

**Option 1 — Refine a saved session file directly:**

```bash
session-sift refine session.json --output refined.json --report
```

**Option 2 — Proxy mode:**

Use proxy mode when your client lets you change its upstream `base_url` or API endpoint. Point the client at `localhost:9978` instead of the real API:

```bash
# OpenAI / OpenAI-compatible
session-sift proxy --provider openai --upstream-url https://api.openai.com

# Anthropic
session-sift proxy --provider anthropic --upstream-url https://api.anthropic.com

# Google-compatible
session-sift proxy --provider google --upstream-url https://your-endpoint.example.com

# OpenClaw
session-sift proxy --provider openclaw --upstream-url http://localhost:3000
```

Your agent keeps using its normal API calls, but only if the client supports a custom API endpoint. If the client does not let you change the upstream URL, proxy mode will not see any traffic.

**Option 3 — MCP server (primary path for Claude Code, Codex, Cursor-style runtimes):**

```bash
session-sift mcp
```

Use MCP mode when the client supports custom MCP servers and tool calls. Session Sift now speaks the standard MCP lifecycle and tools protocol over stdio, which is the primary transport used by MCP-native clients. Configure the client to launch `session-sift mcp` as a local MCP server process.

Recommended packaged-install MCP command after `pip install session-sift`:

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

If the client cannot resolve `session-sift` on PATH, use `python -m session_sift mcp` or an absolute interpreter path instead.

Smoke test the MCP handshake locally:

```bash
session-sift verify mcp
```

**Option 4 — Python SDK (embed in your own agent loop):**

```python
from session_sift import SessionSiftSDK

sdk = SessionSiftSDK()
refined, report = await sdk.refine(messages)
```

---

## Benchmarked Numbers

Measured locally against 50 generated session fixtures:

| Metric | Result |
|---|---|
| Average savings across 50 fixtures | **38.6%** |
| Structural-heavy sessions (file trees + traces) | up to **82%** |
| Pass 1+2 latency (deterministic path) | **~15ms avg** |
| MCP server P50 latency (200 calls) | **1.6ms** |
| MCP server P99 latency (200 calls) | **2.8ms** (spec target: <150ms) |
| SQLite registry under 10,000 concurrent writes | **0 corruption**, 69.75 writes/sec |

Run it yourself:

```bash
python benchmarks/benchmark_corpus.py --iterations 3
python benchmarks/benchmark_slo.py --calls 200 --writes 10000
```

---

## Project DNA — Context That Survives Session Restarts

Every time you start a new agent session on the same project, the agent starts cold. It re-reads files it already knows. It re-discovers your patterns. You re-explain your stack.

Session Sift's **Project DNA registry** solves this. It exports a structured snapshot of what the agent knows about your project — files touched, key decisions made, errors resolved — into a single `.session-sift/dna.json` file.

```bash
# Export at the end of a session
session-sift dna-export --output .session-sift/dna.json

# Import at the start of the next session
session-sift dna-import .session-sift/dna.json
```

The next session starts warm. The agent knows your project. No repetition.

---

## Integrations

### Primary integration targets

- **MCP** for Claude Code, Codex, and Cursor-style runtimes
- **OpenClaw proxy** for cost-sensitive OpenAI-compatible gateway deployments

### What each client needs

| Client / Runtime | Works through proxy? | Works through MCP? | What you need to configure |
|---|---|---|---|
| OpenAI-compatible clients | Yes | No | Change `base_url` to `http://127.0.0.1:9978` |
| OpenClaw | Yes | No | This is the primary proxy integration target |
| Cursor | Maybe | Yes | MCP over stdio is the intended path |
| Claude Code | Maybe | Yes | MCP over stdio is the intended path |
| Windsurf / Roo Code | Maybe | Yes | MCP is the intended path unless you have a verified custom endpoint path |
| Codex | Yes | Yes | Prefer MCP over stdio; proxy remains available when Codex is acting as an API client |
| GitHub Copilot Chat in VS Code | No | Not verified | Running Session Sift locally does not automatically intercept Copilot traffic |

Session Sift is middleware. It only works when the client is explicitly configured to send traffic through the proxy or to call the MCP server.

### Proxy

| Provider | Command |
|---|---|
| OpenAI / OpenAI-compatible | `session-sift proxy --provider openai --upstream-url https://api.openai.com` |
| Anthropic | `session-sift proxy --provider anthropic --upstream-url https://api.anthropic.com` |
| Google | `session-sift proxy --provider google --upstream-url https://your-endpoint` |
| OpenClaw | `session-sift proxy --provider openclaw --upstream-url http://localhost:3000` |

Use this only with clients that let you override the upstream endpoint. Change the client's `base_url` to `http://127.0.0.1:9978`.

For OpenClaw specifically, see [docs/openclaw-integration.md](docs/openclaw-integration.md).

### MCP

```bash
session-sift mcp
```

Then in your MCP config (`.mcp.json`, `.cursor/mcp.json`, Codex config, or equivalent), register a local stdio server that launches `session-sift mcp`.

Example config shape:

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

This is the recommended template for users who installed Session Sift with `pip install session-sift`.

If the client does not inherit a PATH that contains the `session-sift` executable, fall back to:

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

Use this path for runtimes such as Claude Code, Codex, Cursor, Windsurf, and Roo Code when they support custom MCP server registration. The tools `session_sift_refine`, `session_sift_status`, and `session_sift_export_dna` become available to the client.

For exact Claude Code and Codex setup commands, see [docs/mcp-integration.md](docs/mcp-integration.md).

Checked-in example configs:

- Claude Code / project MCP config: [.mcp.json](.mcp.json)
- Codex config: [.codex/config.toml](.codex/config.toml)

### Python SDK

```python
from session_sift import SessionSiftSDK
from session_sift.config import SessionSiftConfig

config = SessionSiftConfig(
    token_threshold=50_000,
    recency_window=5,
    pruning_threshold=0.15,
)
sdk = SessionSiftSDK(config)

refined, report = await sdk.refine(messages)
print(report.to_console())
```

Full SDK reference: [docs/cli-reference.md](docs/cli-reference.md)

---

## Configuration

The config file lives at `.session-sift/config.json`. Create it with:

```bash
session-sift config set token_threshold 80000
session-sift config show
```

Key settings:

| Setting | Default | What It Does |
|---|---|---|
| `token_threshold` | `50000` | Only prune when session exceeds this many tokens |
| `recency_window` | `5` | Protect last N turns from all pruning |
| `pruning_threshold` | `0.15` | RetentionWeight below this → Pass 3 candidate |
| `decay_lambda` | `0.05` | How fast old messages lose weight (higher = faster decay) |
| `pass3_enabled` | `false` | Enable LLM-assisted semantic compression |
| `pass3_model` | `claude-haiku-3-5` | Model for semantic compression |
| `proxy_port` | `9978` | Local proxy listen port |
| `mcp_port` | `9977` | Local MCP server port |

Full reference: [docs/configuration.md](docs/configuration.md)

---

## What Is Never Pruned

Session Sift is conservative by design. These are always preserved regardless of age or weight:

- Messages containing `STRICT`, `TODO`, or `FIXME` annotations
- System messages (`role: system`)
- The most recent `recency_window` turns (default: last 5)
- Any message with a `RetentionWeight` >= pruning threshold
- File paths, function names, variable names, error messages, numeric config values (always preserved verbatim in Pass 3 summaries)

---

## Repository Layout

```
session_sift/       Python package — engine, MCP server, proxy, SDK, providers
  engine.py         SessionSiftEngine — the core refine() loop
  passes/pass1.py   StructuralPruner — deterministic regex collapser
  passes/pass2.py   TemporalPruner — SQLite-backed resolved-error pruning
  passes/pass3.py   SemanticCompressor — LLM-assisted fluff summarization
  server_mcp.py     JSON-RPC MCP server
  server_proxy.py   aiohttp proxy with streaming SSE reconstruction
  registry.py       FileRegistry — SQLite persistence layer
  models.py         SavingsReport dataclass
  sdk.py            SessionSiftSDK public API

tests/              90 passing tests — unit, integration, streaming edge cases
benchmarks/         Deterministic benchmark harness (corpus, SLO, model comparison)
docs/               Quickstart, CLI reference, configuration, integrations
scripts/            CI savings gate (check_savings_gate.py)
.github/workflows/  GitHub Actions CI — savings regression guard
```

---

## Install & Verify

```bash
pip install session-sift
```

```bash
# Run tests
pytest -q

# Run corpus benchmark (50 fixtures, 3 iterations)
python benchmarks/benchmark_corpus.py --iterations 3

# Run SLO benchmark (200 MCP calls, 10k registry writes)
python benchmarks/benchmark_slo.py --calls 200 --writes 10000
```

Expected test output: `90 passed`  
Expected benchmark: `avg_savings_pct: 38.6%`, MCP P99 < 150ms

Upgrade:

```bash
pip install --upgrade session-sift
```

Contributor setup from source: [CONTRIBUTING.md](CONTRIBUTING.md)

---

## OSS vs Cloud

| Feature | OSS (now) | Cloud (roadmap) |
|---|---|---|
| Pass 1 structural pruning (deterministic) | ✅ | ✅ |
| Pass 2 temporal pruning (SQLite registry) | ✅ | ✅ |
| Pass 3 semantic compression (BYO API key) | ✅ | ✅ |
| Local MCP server | ✅ | ✅ |
| Local proxy (OpenAI, Anthropic, Google, OpenClaw) | ✅ | ✅ |
| Project DNA export / import | ✅ | ✅ |
| Python SDK | ✅ | ✅ |
| GitHub Actions savings gate | ✅ | ✅ |
| SavingsReport (console) | ✅ | ✅ |
| Team dashboard & aggregate savings trends | — | ✅ |
| Cloud DNA Sync (shared project context across team) | — | ✅ |
| Shared rules (org-wide `.session-sift/rules`) | — | ✅ |
| Centralized audit history | — | ✅ |
| SavingsReport web dashboard + Slack bot | — | ✅ |
| GitHub App (no workflow setup needed) | — | ✅ |
| SAML SSO / on-prem deployment | — | ✅ Enterprise |
| Compliance export (SOC 2, HIPAA) | — | ✅ Enterprise |

The OSS core is the foundation. Cloud is additive — your local setup never breaks when cloud features ship.

**Waitlist / announcements:** [https://sessionsift.dev](https://sessionsift.dev)

---

## License

Apache 2.0 — see [LICENSE](LICENSE).

## Security

See [SECURITY.md](SECURITY.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Use [docs/issue-guide.md](docs/issue-guide.md) before opening an issue.

