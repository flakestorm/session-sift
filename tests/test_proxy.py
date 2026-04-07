from __future__ import annotations

import asyncio
import json

import pytest
from aiohttp import ClientSession, web

from session_sift.config import SessionSiftConfig
from session_sift.engine import SessionSiftEngine
from session_sift.server_proxy import create_app


async def _start_site(app: web.Application) -> tuple[web.AppRunner, str]:
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    sockets = site._server.sockets
    port = sockets[0].getsockname()[1]
    return runner, f"http://127.0.0.1:{port}"


@pytest.mark.asyncio
async def test_proxy_non_streaming_openclaw_compatible() -> None:
    async def upstream_handler(request: web.Request) -> web.Response:
        body = await request.json()
        assert request.path == "/v1/chat/completions"
        return web.json_response(
            {
                "choices": [{"message": {"content": f"echo:{len(body['messages'])}"}}]
            }
        )

    upstream_app = web.Application()
    upstream_app.router.add_post("/v1/chat/completions", upstream_handler)
    upstream_runner, upstream_url = await _start_site(upstream_app)

    try:
        config = SessionSiftConfig(
            upstream_provider="openclaw",
            upstream_url=upstream_url,
            pass3_enabled=True,
        )
        engine = SessionSiftEngine(config)
        proxy_runner, proxy_url = await _start_site(create_app(config, engine))
        try:
            async with ClientSession() as session:
                async with session.post(
                    f"{proxy_url}/v1/chat/completions",
                    json={"messages": [{"role": "user", "content": "hello"} for _ in range(3)]},
                    headers={"X-Session-Sift-Upstream-Provider": "openclaw"},
                ) as response:
                    payload = await response.json()
                    assert payload["choices"][0]["message"]["content"] == "echo:3"
        finally:
            await proxy_runner.cleanup()
    finally:
        await upstream_runner.cleanup()


@pytest.mark.asyncio
async def test_proxy_streaming_reconstructs_text() -> None:
    async def upstream_stream_handler(request: web.Request) -> web.StreamResponse:
        response = web.StreamResponse(
            status=200,
            headers={"Content-Type": "text/event-stream"},
        )
        await response.prepare(request)
        await response.write(b'data: {"choices":[{"delta":{"content":"hello "}}]}\n\n')
        await response.write(b'data: {"choices":[{"delta":{"content":"world"}}]}\n\n')
        await response.write(b'data: [DONE]\n\n')
        await response.write_eof()
        return response

    upstream_app = web.Application()
    upstream_app.router.add_post("/v1/chat/completions", upstream_stream_handler)
    upstream_runner, upstream_url = await _start_site(upstream_app)

    try:
        config = SessionSiftConfig(upstream_provider="openai", upstream_url=upstream_url)
        engine = SessionSiftEngine(config)
        proxy_runner, proxy_url = await _start_site(create_app(config, engine))
        try:
            async with ClientSession() as session:
                async with session.post(
                    f"{proxy_url}/v1/chat/completions",
                    json={
                        "stream": True,
                        "messages": [{"role": "user", "content": f"hello {index}"} for index in range(10)],
                    },
                ) as response:
                    body = await response.text()
                    assert "hello " in body
                    assert "world" in body
            await asyncio.sleep(0.05)
            assert engine.status()["history_entries"] == 1
            assert engine._history[0]["content"] == "hello world"
        finally:
            await proxy_runner.cleanup()
    finally:
        await upstream_runner.cleanup()


@pytest.mark.asyncio
async def test_proxy_streaming_handles_partial_sse_chunks() -> None:
    async def upstream_stream_handler(request: web.Request) -> web.StreamResponse:
        response = web.StreamResponse(status=200, headers={"Content-Type": "text/event-stream"})
        await response.prepare(request)
        await response.write(b'data: {"choices":[{"delta":{"content":"hel')
        await response.write(b'lo "}}]}\n\n')
        await response.write(b'data: {"choices":[{"delta":{"content":"world"}}]}\n\n')
        await response.write(b'data: [DONE]\n\n')
        await response.write_eof()
        return response

    upstream_app = web.Application()
    upstream_app.router.add_post("/v1/chat/completions", upstream_stream_handler)
    upstream_runner, upstream_url = await _start_site(upstream_app)

    try:
        config = SessionSiftConfig(upstream_provider="openai", upstream_url=upstream_url)
        engine = SessionSiftEngine(config)
        proxy_runner, proxy_url = await _start_site(create_app(config, engine))
        try:
            async with ClientSession() as session:
                async with session.post(
                    f"{proxy_url}/v1/chat/completions",
                    json={
                        "stream": True,
                        "messages": [{"role": "user", "content": f"hello {index}"} for index in range(10)],
                    },
                ) as response:
                    body = await response.text()
                    assert "data:" in body
            await asyncio.sleep(0.05)
            assert engine._history[0]["content"] == "hello world"
        finally:
            await proxy_runner.cleanup()
    finally:
        await upstream_runner.cleanup()


@pytest.mark.asyncio
async def test_proxy_streaming_ignores_heartbeats_and_malformed_events() -> None:
    async def upstream_stream_handler(request: web.Request) -> web.StreamResponse:
        response = web.StreamResponse(status=200, headers={"Content-Type": "text/event-stream"})
        await response.prepare(request)
        await response.write(b': keep-alive\n\n')
        await response.write(b'data: not-json\n\n')
        await response.write(b'data: {"choices":[{"delta":{"content":"valid"}}]}\n\n')
        await response.write(b'data: [DONE]\n\n')
        await response.write_eof()
        return response

    upstream_app = web.Application()
    upstream_app.router.add_post("/v1/chat/completions", upstream_stream_handler)
    upstream_runner, upstream_url = await _start_site(upstream_app)

    try:
        config = SessionSiftConfig(upstream_provider="openai", upstream_url=upstream_url)
        engine = SessionSiftEngine(config)
        proxy_runner, proxy_url = await _start_site(create_app(config, engine))
        try:
            async with ClientSession() as session:
                async with session.post(
                    f"{proxy_url}/v1/chat/completions",
                    json={
                        "stream": True,
                        "messages": [{"role": "user", "content": f"hello {index}"} for index in range(10)],
                    },
                ) as response:
                    body = await response.text()
                    assert "not-json" in body
                    assert "valid" in body
            await asyncio.sleep(0.05)
            assert engine._history[0]["content"] == "valid"
        finally:
            await proxy_runner.cleanup()
    finally:
        await upstream_runner.cleanup()


@pytest.mark.asyncio
async def test_proxy_streaming_connection_drop_keeps_partial_reconstruction() -> None:
    async def upstream_stream_handler(request: web.Request) -> web.StreamResponse:
        response = web.StreamResponse(status=200, headers={"Content-Type": "text/event-stream"})
        await response.prepare(request)
        await response.write(b'data: {"choices":[{"delta":{"content":"partial output"}}]}\n\n')
        await response.write_eof()
        return response

    upstream_app = web.Application()
    upstream_app.router.add_post("/v1/chat/completions", upstream_stream_handler)
    upstream_runner, upstream_url = await _start_site(upstream_app)

    try:
        config = SessionSiftConfig(upstream_provider="openai", upstream_url=upstream_url)
        engine = SessionSiftEngine(config)
        proxy_runner, proxy_url = await _start_site(create_app(config, engine))
        try:
            async with ClientSession() as session:
                async with session.post(
                    f"{proxy_url}/v1/chat/completions",
                    json={
                        "stream": True,
                        "messages": [{"role": "user", "content": f"hello {index}"} for index in range(10)],
                    },
                ) as response:
                    body = await response.text()
                    assert "partial output" in body
            await asyncio.sleep(0.05)
            assert engine._history[0]["content"] == "partial output"
        finally:
            await proxy_runner.cleanup()
    finally:
        await upstream_runner.cleanup()


@pytest.mark.asyncio
async def test_proxy_streaming_reconstructs_anthropic_events() -> None:
    async def upstream_stream_handler(request: web.Request) -> web.StreamResponse:
        response = web.StreamResponse(status=200, headers={"Content-Type": "text/event-stream"})
        await response.prepare(request)
        await response.write(b'data: {"type":"content_block_delta","delta":{"text":"hello "}}\n\n')
        await response.write(b'data: {"type":"content_block_delta","delta":{"text":"anthropic"}}\n\n')
        await response.write_eof()
        return response

    upstream_app = web.Application()
    upstream_app.router.add_post("/v1/messages", upstream_stream_handler)
    upstream_runner, upstream_url = await _start_site(upstream_app)

    try:
        config = SessionSiftConfig(upstream_provider="anthropic", upstream_url=upstream_url)
        engine = SessionSiftEngine(config)
        proxy_runner, proxy_url = await _start_site(create_app(config, engine))
        try:
            async with ClientSession() as session:
                async with session.post(
                    f"{proxy_url}/v1/messages",
                    json={
                        "stream": True,
                        "messages": [{"role": "system", "content": "system prompt"}] + [{"role": "user", "content": f"hello {index}"} for index in range(10)],
                    },
                    headers={"X-Session-Sift-Upstream-Provider": "anthropic"},
                ) as response:
                    body = await response.text()
                    assert "anthropic" in body
            await asyncio.sleep(0.05)
            assert engine._history[0]["content"] == "hello anthropic"
        finally:
            await proxy_runner.cleanup()
    finally:
        await upstream_runner.cleanup()


@pytest.mark.asyncio
async def test_proxy_non_json_response_passthrough() -> None:
    async def upstream_handler(request: web.Request) -> web.Response:
        return web.Response(text="plain-text", content_type="text/plain")

    upstream_app = web.Application()
    upstream_app.router.add_post("/v1/chat/completions", upstream_handler)
    upstream_runner, upstream_url = await _start_site(upstream_app)

    try:
        config = SessionSiftConfig(upstream_provider="openai", upstream_url=upstream_url)
        proxy_runner, proxy_url = await _start_site(create_app(config, SessionSiftEngine(config)))
        try:
            async with ClientSession() as session:
                async with session.post(
                    f"{proxy_url}/v1/chat/completions",
                    json={"messages": [{"role": "user", "content": f"hello {i}"} for i in range(10)]},
                ) as response:
                    assert await response.text() == "plain-text"
        finally:
            await proxy_runner.cleanup()
    finally:
        await upstream_runner.cleanup()