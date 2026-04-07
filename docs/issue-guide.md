# Issue Guide

Use this guide before opening a GitHub issue.

## Bug Reports

Include:

- what you expected to happen
- what actually happened
- the exact command you ran
- provider and upstream URL shape if relevant
- a minimal input or transcript sample if one can be shared safely
- traceback, HTTP status, or failing test output
- OS and Python version

Good bug reports are reproducible. If the issue only appears with a real provider, say whether it reproduces with a local mock or fixture.

## Feature Requests

Include:

- the problem you are trying to solve
- why current behavior is insufficient
- the workflow you want to enable
- whether the change affects CLI, SDK, MCP, proxy, or docs
- any compatibility concerns for OpenAI-compatible backends or OpenClaw

## Questions And Support

Use issues for actionable bugs and concrete feature requests. If a topic is still vague, write it as a proposal with examples instead of a broad brainstorming thread.

## Before Filing

- confirm you are on the latest repo state
- read [README.md](../README.md)
- check [docs/quickstart.md](quickstart.md)
- search existing issues first