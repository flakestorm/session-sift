# Performance Baseline

This document records the local benchmark evidence added for the OSS audit gaps around corpus coverage, registry concurrency, and MCP latency.

Date: 2026-04-07

## Commands

```powershell
c:/Users/fhumarang/Projects/sieve/.venv/Scripts/python.exe benchmarks/benchmark_corpus.py --iterations 3
c:/Users/fhumarang/Projects/sieve/.venv/Scripts/python.exe benchmarks/benchmark_slo.py --calls 200 --writes 10000
```

## Corpus Benchmark

Command:

```powershell
c:/Users/fhumarang/Projects/sieve/.venv/Scripts/python.exe benchmarks/benchmark_corpus.py --iterations 1
```

Observed output:

```json
{
  "summary": {
    "fixture_count": 50,
    "iterations": 1,
    "avg_elapsed_ms": 15.295,
    "avg_savings_pct": 38.601
  },
  "fixtures": [
    {
      "fixture": "resolved_error_00",
      "iterations": 1,
      "avg_elapsed_ms": 50.56,
      "avg_total_savings": 50,
      "avg_pass1_savings": 34,
      "avg_pass2_savings": 27,
      "avg_pass3_savings": 0,
      "avg_savings_pct": 23.041
    },
    {
      "fixture": "semantic_compression_01",
      "iterations": 1,
      "avg_elapsed_ms": 0.526,
      "avg_total_savings": 25,
      "avg_pass1_savings": 12,
      "avg_pass2_savings": 0,
      "avg_pass3_savings": 11,
      "avg_savings_pct": 13.021
    },
    {
      "fixture": "structural_pruning_02",
      "iterations": 1,
      "avg_elapsed_ms": 0.374,
      "avg_total_savings": 611,
      "avg_pass1_savings": 610,
      "avg_pass2_savings": 0,
      "avg_pass3_savings": 0,
      "avg_savings_pct": 82.124
    }
  ]
}
```

The full run covered 50 generated fixture variants. The excerpt above shows the first three representative entries and the aggregate summary.

## SLO Benchmark

Command:

```powershell
c:/Users/fhumarang/Projects/sieve/.venv/Scripts/python.exe benchmarks/benchmark_slo.py --calls 200 --writes 10000
```

Observed output:

```json
{
  "registry": {
    "writes": 10000,
    "elapsed_ms": 143372.598,
    "writes_per_sec": 69.75,
    "verified_count": 10000
  },
  "mcp": {
    "calls": 200,
    "p50_ms": 1.637,
    "p95_ms": 2.167,
    "p99_ms": 2.78,
    "max_ms": 3.889
  }
}
```

## Notes

- The MCP latency baseline is comfortably below the spec's 150ms deterministic-path target on this machine.
- The registry benchmark now demonstrates integrity and throughput at the spec-scale 10k write target.
- The benchmark corpus now exercises 50 generated fixture variants built from the repo's versioned seed sessions.
- Live Pass 3 model comparison is documented in [docs/pass3-model-benchmark.md](pass3-model-benchmark.md) and becomes executable as soon as upstream API keys are configured.