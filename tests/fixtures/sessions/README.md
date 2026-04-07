# Session Corpus

This directory contains a curated regression and benchmark corpus for Session Sift.

Each fixture is a representative long-session transcript shaped to exercise a specific trust-critical behavior:

- `structural_pruning.json`: Pass 1 structural artifacts such as file trees, install logs, large JSON payloads, long code fences, git diffs, and tool-result wrappers
- `resolved_error.json`: Pass 2 temporal pruning where a file-specific error becomes stale after a later write
- `semantic_compression.json`: Pass 3 compression of low-signal conversational turns while preserving paths and numbers

These fixtures are used by:

- [tests/test_session_corpus.py](../../test_session_corpus.py)
- [benchmarks/benchmark_corpus.py](../../../benchmarks/benchmark_corpus.py)

The corpus is intentionally versioned with the repo so benchmark and regression evidence stays reproducible.